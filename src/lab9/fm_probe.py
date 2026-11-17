"""M1 evidence: which eval items does each failure mode actually break?

    python -m lab9.fm_probe                 # table: FM -> items it breaks, plus a `fixed` control
    python -m lab9.fm_probe --out /tmp/p.json

For each failure mode we switch on exactly ONE bug on top of `fixed` (lab9.variant_agent),
replay all items x seeds through the real graders, and record which (item, seed) trials fail.
`fixed` runs as a control and must be clean: a grader that fails the control is a bad grader.

This is how `failure_modes` in the eval set are justified: an item is tagged with an FM only if
that FM's bug makes the item fail. Nothing here edits lab8/ or writes to reports/.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from lab8.console import utf8_stdio
from lab8.shapes import SHAPES
from lab9 import variants
from lab9.eval import SPEC, load_spec, run_eval
from lab9.variant_agent import make_shape

# FM code -> bug switches (on top of `no_override`). FM-04 has two faces: summing and rounding.
PROBES: dict[str, tuple[str, ...]] = {
    "FM-01": ("leaky_trace",),
    "FM-02": ("ignore_denied",),
    "FM-03": ("ticket_trust",),
    "FM-04": ("sum_parts", "round_down"),
    "FM-05": ("pre_deducted",),
    "FM-06": ("stale_clause",),
    "FM-07": ("sibling_refund",),
    "FM-08": ("misreport",),
}
# metric id -> the value that means "this trial failed that metric"
FAIL_VALUE = {"pass_rate": False, "secret_leak": True, "approval_bypass": True,
              "refund_amount_correct": False, "db_fact_kept": False, "reply_matches_ledger": False}


def failing_trials(rep: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for r in rep["rows"]:
        graders = [m for m, bad in FAIL_VALUE.items() if r.get(m) is bad]
        if graders:
            out.append({"item": r["item_id"], "seed": r["seed"], "graders": graders})
    return out


def probe(spec_path: Path = SPEC) -> dict[str, Any]:
    variants.register()
    spec = load_spec(spec_path)
    result: dict[str, Any] = {}
    for fm, bugs in PROBES.items():
        fails: list[dict[str, Any]] = []
        for bug in bugs:
            name = f"probe_{bug}"
            SHAPES.setdefault(name, make_shape(name, {"no_override", bug}))
            rep = run_eval(name, spec)
            fails += [{**f, "bug": bug} for f in failing_trials(rep)]
        result[fm] = {"bugs": list(bugs), "n_failing_trials": len(fails),
                      "items": sorted({f["item"] for f in fails}),
                      "graders": sorted({g for f in fails for g in f["graders"]}),
                      "first": fails[:1]}
    control = run_eval("fixed", spec)
    result["control_fixed"] = {"failing_trials": len(failing_trials(control)), "metrics": control["metrics"]}
    return result


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.fm_probe")
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--out", help="optional JSON dump (never under reports/)")
    args = ap.parse_args(argv)
    res = probe(Path(args.spec))
    print(f"{'FM':<6} {'bugs':<26} {'fails':>5}  items / graders that caught it")
    for fm, v in res.items():
        if fm == "control_fixed":
            continue
        print(f"{fm:<6} {','.join(v['bugs']):<26} {v['n_failing_trials']:>5}  {' '.join(v['items'])}  <- {','.join(v['graders'])}")
    c = res["control_fixed"]
    print(f"control `fixed`: {c['failing_trials']} failing trial(s)  {c['metrics']}")
    if args.out:
        Path(args.out).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0 if c["failing_trials"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
