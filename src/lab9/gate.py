"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item
from lab9.graders import GRADERS


def _is_bad_number(v) -> bool:
    return isinstance(v, float) and (math.isnan(v) or math.isinf(v))


def _loosened(base_th: dict, th: dict, where: str) -> list[str]:
    """Ratchet for one threshold dict: `max` / `max_increase` may not rise, `min` may not fall,
    and a bound or `no_significant_drop` that existed may not disappear."""
    out = []
    for key in ("max", "max_increase"):
        if key in base_th:
            if key not in th:
                out.append(f"{where}: '{key}' bound was removed")
            elif th[key] > base_th[key]:
                out.append(f"{where}: {key} raised {base_th[key]} -> {th[key]} (looser)")
    if "min" in base_th:
        if "min" not in th:
            out.append(f"{where}: 'min' bound was removed")
        elif th["min"] < base_th["min"]:
            out.append(f"{where}: min lowered {base_th['min']} -> {th['min']} (looser)")
    if base_th.get("no_significant_drop") and not th.get("no_significant_drop"):
        out.append(f"{where}: no_significant_drop was dropped")
    return out


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    problems: list[str] = []
    rows = pr.get("rows") or []
    man = pr.get("manifest") or {}

    # 1. NaN / inf: `nan < min` is False, so a naive threshold comparison waves it through.
    problems += [f"metric {k} is {v} (NaN/inf cannot be compared)"
                 for k, v in (pr.get("metrics") or {}).items() if _is_bad_number(v)]

    # 2. Row count and duplicates: dropped rows hide failures, duplicated rows pad successes.
    want = int(man.get("items", 0)) * len(man.get("seeds") or [])
    if len(rows) != want:
        problems.append(f"{len(rows)} rows but manifest says {man.get('items')} items x "
                        f"{len(man.get('seeds') or [])} seeds = {want} (rows dropped or duplicated)")
    keys = [(r.get("item_id"), r.get("seed")) for r in rows]
    dup = sorted({k for k in keys if keys.count(k) > 1}, key=str)
    if dup:
        problems.append(f"duplicate (item, seed) rows: {dup[:3]}{' ...' if len(dup) > 3 else ''}")

    # 3. Same (item, seed) set as the baseline: no cherry-picked seeds or items.
    base_keys = {(r.get("item_id"), r.get("seed")) for r in base.get("rows") or []}
    if base_keys and set(keys) != base_keys:
        missing, extra = sorted(base_keys - set(keys), key=str), sorted(set(keys) - base_keys, key=str)
        problems.append(f"(item, seed) set differs from baseline: {len(missing)} missing {missing[:2]}, "
                        f"{len(extra)} extra {extra[:2]}")

    # 4. A grader that crashed is not a pass: evaluator failures, or a graded metric left None.
    if pr.get("evaluator_failures"):
        problems.append(f"{len(pr['evaluator_failures'])} evaluator failure(s): {pr['evaluator_failures'][0]}")
    graded = [m["id"] for m in spec.get("metrics", []) if m["id"] in GRADERS]
    for m in graded:
        n_none = sum(1 for r in rows if r.get(m) is None)
        if n_none:
            problems.append(f"{n_none} row(s) have no value for graded metric {m} (grader crashed / row masked)")

    # 5. Reported metrics must equal what the rows say (a hand-edited summary is not a measurement).
    for m in graded:
        reported = (pr.get("metrics") or {}).get(m)
        vals = [r[m] for r in rows if r.get(m) is not None]
        if reported is None or _is_bad_number(reported) or not vals:
            continue
        actual = sum(vals) if m in ("secret_leak", "approval_bypass") else sum(vals) / len(vals)
        if abs(float(reported) - actual) > 1e-3:
            problems.append(f"metric {m} reported {reported} but its rows give {round(actual, 4)}")

    # 6. Ratchet: on the same eval-set version thresholds may only get stricter.
    if base_spec is not None and spec.get("eval_set_version") == base_spec.get("eval_set_version"):
        now = {m["id"]: m for m in spec.get("metrics", [])}
        for bm in base_spec.get("metrics", []):
            m = now.get(bm["id"])
            if m is None:
                problems.append(f"metric {bm['id']} was removed from the spec")
                continue
            if bm.get("blocking") and not m.get("blocking"):
                problems.append(f"metric {bm['id']} is no longer blocking")
            problems += _loosened(bm.get("threshold") or {}, m.get("threshold") or {}, f"metric {bm['id']}")
        now_slices = {(x["name"], x["metric"]): x for x in spec.get("slices") or []}
        for bs in base_spec.get("slices") or []:
            x = now_slices.get((bs["name"], bs["metric"]))
            tag = f"slice {bs['name']}/{bs['metric']}"
            if x is None:
                problems.append(f"{tag} was removed from the spec")
                continue
            if bs.get("blocking") and not x.get("blocking"):
                problems.append(f"{tag} is no longer blocking")
            problems += _loosened({k: bs[k] for k in ("min", "no_significant_drop") if k in bs},
                                  {k: x[k] for k in ("min", "no_significant_drop") if k in x}, tag)

        bg = base_spec.get("regression_guard")
        if bg:
            ng = spec.get("regression_guard")
            if not ng:
                problems.append("regression_guard was removed from the spec")
            else:
                if int(ng.get("max_new_failures", 0)) > int(bg.get("max_new_failures", 0)):
                    problems.append(f"regression_guard: max_new_failures raised {bg.get('max_new_failures', 0)} -> {ng.get('max_new_failures', 0)} (looser)")
                dropped = sorted(set(bg.get("metrics") or []) - set(ng.get("metrics") or []))
                if dropped:
                    problems.append(f"regression_guard: metric(s) {dropped} no longer guarded")
                if bg.get("blocking", True) and not ng.get("blocking", True):
                    problems.append("regression_guard is no longer blocking")

    # 7. Slice tags are derived from labels: the same item must carry the same tags as on main.
    def tags(rep: dict) -> dict:
        return {r["item_id"]: sorted(r.get("slices") or []) for r in rep.get("rows") or []}
    pt, bt = tags(pr), tags(base)
    moved = sorted(i for i in pt.keys() & bt.keys() if pt[i] != bt[i])
    if moved:
        problems.append(f"slice tags changed vs baseline for {len(moved)} item(s), e.g. {moved[0]}: "
                        f"{bt[moved[0]]} -> {pt[moved[0]]} (relabelling hides a slice regression)")
    return problems


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked: list[str] = []
    lines: list[str] = []
    bs = spec.get("bootstrap", {})
    for sl in spec.get("slices") or []:
        name, metric = sl["name"], sl["metric"]
        sid = f"slice:{name}/{metric}"
        a = per_item(pr, metric, slice_name=name)
        b = per_item(base, metric, slice_name=name)
        fail, note = False, ""
        if not a:
            # No row of this slice at all: items were dropped or relabelled. Never a silent pass.
            fail, val, note = True, None, "no rows for this slice"
        else:
            val = sum(a.values()) / len(a)
            if "min" in sl and val < sl["min"]:
                fail = True
            if sl.get("no_significant_drop"):
                keys = sorted(set(a) & set(b))
                if keys:
                    d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                                       n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
                    note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                    if hi < 0:
                        fail = True
        if fail and sl.get("blocking"):
            blocked.append(sid)
        label = "ok" if not fail else ("BLOCK" if sl.get("blocking") else "warn")
        shown = "None" if val is None else f"{val:.4f}"
        th = {k: sl[k] for k in ("min", "no_significant_drop") if k in sl}
        lines.append(f"  {sid:<34} {shown:<8} {json.dumps(th):<40} {note:<28} {label}")
    return blocked, lines


def regression_guard(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """Per-trial regression guard. Thresholds and slice means compare AGGREGATES, so a PR that fails exactly as
    many trials as main, just on other (item, seed) pairs, looks identical. A trial that passed on main and fails
    in the PR is a regression no matter what the average says.

    spec["regression_guard"] = {"metrics": [...], "max_new_failures": 0, "blocking": true}
    Counts (item, seed) pairs where the baseline value is True and the PR value is False, per metric.
    Return (blocked ids like "regression:pass_rate", report lines).

    Honest limit: this is only meaningful when reruns are deterministic (MockLLM, A/A delta = 0). With a real
    LLM, trial-level flips are noise and `max_new_failures` must be derived from the A/A flip rate instead."""
    cfg = spec.get("regression_guard")
    if not cfg:
        return [], []
    blocked: list[str] = []
    lines: list[str] = []
    allowed = int(cfg.get("max_new_failures", 0))
    base_rows = {(r["item_id"], r["seed"]): r for r in base.get("rows") or []}
    for metric in cfg.get("metrics") or []:
        new = sorted((r["item_id"], r["seed"]) for r in pr.get("rows") or []
                     if r.get(metric) is False and (base_rows.get((r["item_id"], r["seed"])) or {}).get(metric) is True)
        fail = len(new) > allowed
        if fail and cfg.get("blocking", True):
            blocked.append(f"regression:{metric}")
        shown = ", ".join(f"{i}@{sd}" for i, sd in new[:3]) + (" ..." if len(new) > 3 else "")
        label = "ok" if not fail else ("BLOCK" if cfg.get("blocking", True) else "warn")
        lines.append(f"  {'regression:' + metric:<34} {len(new):<8} {json.dumps({'max_new_failures': allowed}):<40} {shown:<28} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    if spec.get("regression_guard"):
        gb, gl = regression_guard(pr, base, spec)
        blocked += gb
        lines += gl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
