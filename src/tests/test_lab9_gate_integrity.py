"""M5-M7: gate integrity and slice checks against gaming attempts the public traps do not build.
Synthetic reports only (no agent run), so these are fast. Run: python -m pytest -q -m student -o addopts= -k lab9"""
import copy
import json
import math
from pathlib import Path

import pytest

pytestmark = pytest.mark.student
ROOT = Path(__file__).resolve().parents[1]
SEEDS = (1, 2, 3, 4, 5)


def make_report(fail=(), slices=None, metrics=None):
    """4 items x 5 seeds; `fail` = (item, seed) pairs that fail pass_rate. Items 0-1 carry the 'money' slice."""
    slices = {0: ["money"], 1: ["money"]} if slices is None else slices     # {} means "no item in any slice"
    rows = [{"item_id": f"E-{i}", "seed": s, "pass_rate": (i, s) not in set(fail), "slices": slices.get(i, [])}
            for i in range(4) for s in SEEDS]
    passed = sum(r["pass_rate"] for r in rows) / len(rows)
    return {"manifest": {"eval_set_sha": "x", "items": 4, "seeds": list(SEEDS)}, "rows": rows,
            "metrics": metrics or {"pass_rate": round(passed, 4)}, "evaluator_failures": []}


SPEC = {"eval_set_version": "v2", "metrics": [{"id": "pass_rate", "kind": "capability", "blocking": True,
                                               "threshold": {"min": 0.8, "no_significant_drop": True}}],
        "slices": [{"name": "money", "metric": "pass_rate", "min": 0.9, "no_significant_drop": True, "blocking": True}]}


@pytest.fixture(scope="module")
def gate():
    from lab9 import gate

    return gate


def test_clean_report_has_no_problems(gate):
    base = make_report()
    assert gate.integrity_check(base, base, SPEC, SPEC) == []


def test_nan_metric_alone_is_flagged(gate):
    base = make_report()
    pr = make_report(metrics={"pass_rate": float("nan")})
    assert any("NaN" in p for p in gate.integrity_check(pr, base, SPEC))
    assert any("inf" in p for p in gate.integrity_check(make_report(metrics={"pass_rate": math.inf}), base, SPEC))


def test_duplicate_rows_padding_the_count_are_flagged(gate):
    base = make_report(fail={(0, 1)})
    pr = copy.deepcopy(base)
    pr["rows"][0] = copy.deepcopy(pr["rows"][1])            # same row twice, total count unchanged
    problems = gate.integrity_check(pr, base, SPEC)
    assert any("duplicate" in p for p in problems)
    assert any("differs from baseline" in p for p in problems)


def test_dropped_rows_with_a_doctored_manifest_are_still_flagged(gate):
    base = make_report(fail={(0, 1), (0, 2)})
    pr = copy.deepcopy(base)
    pr["rows"] = [r for r in pr["rows"] if not (r["item_id"] == "E-0" and r["seed"] in (1, 2))]
    pr["manifest"]["items"] = 4                             # looks consistent only if seeds are shrunk too
    pr["manifest"]["seeds"] = [3, 4, 5]
    pr["rows"] = [r for r in pr["rows"] if r["seed"] in (3, 4, 5)]
    assert any("differs from baseline" in p for p in gate.integrity_check(pr, base, SPEC))


def test_hand_edited_summary_does_not_match_its_rows(gate):
    base = make_report()
    pr = make_report(fail={(0, 1), (1, 1), (2, 1), (3, 1)}, metrics={"pass_rate": 1.0})   # rows fail, summary says 1.0
    assert any("reported 1.0 but its rows give" in p for p in gate.integrity_check(pr, base, SPEC))


def test_evaluator_failure_on_a_green_run_is_flagged(gate):
    base = make_report()
    pr = make_report()
    pr["evaluator_failures"] = ["E-2@3:ApprovalBypass:boom"]
    assert any("evaluator failure" in p for p in gate.integrity_check(pr, base, SPEC))


def test_row_masked_to_none_is_flagged(gate):
    base = make_report()
    pr = make_report(fail={(0, 1)})
    pr["rows"][1]["pass_rate"] = None                       # the failing row is blanked instead of removed
    pr["metrics"]["pass_rate"] = 1.0
    assert any("no value for graded metric pass_rate" in p for p in gate.integrity_check(pr, base, SPEC))


def test_relabelling_a_failing_item_out_of_its_slice_is_flagged(gate):
    base = make_report()
    pr = make_report(fail={(0, 1), (0, 2), (0, 3)}, slices={1: ["money"]})   # E-0 quietly leaves the slice
    problems = gate.integrity_check(pr, base, SPEC)
    assert any("slice tags changed" in p and "E-0" in p for p in problems)


@pytest.mark.parametrize("edit,needle", [
    (lambda s: s["metrics"][0]["threshold"].__setitem__("min", 0.5), "min lowered"),
    (lambda s: s["metrics"][0]["threshold"].pop("no_significant_drop"), "no_significant_drop was dropped"),
    (lambda s: s["metrics"][0].__setitem__("blocking", False), "no longer blocking"),
    (lambda s: s["metrics"].clear(), "was removed from the spec"),
    (lambda s: s["slices"].clear(), "slice money/pass_rate was removed"),
    (lambda s: s["slices"][0].__setitem__("min", 0.5), "min lowered"),
    (lambda s: s["slices"][0].__setitem__("blocking", False), "no longer blocking"),
    (lambda s: s["slices"][0].pop("no_significant_drop"), "no_significant_drop was dropped"),
])
def test_every_way_of_loosening_the_spec_is_flagged(gate, edit, needle):
    base = make_report()
    loose = copy.deepcopy(SPEC)
    edit(loose)
    assert any(needle in p for p in gate.integrity_check(base, base, loose, SPEC)), needle


def test_stricter_spec_and_a_new_eval_set_version_are_allowed(gate):
    base = make_report()
    stricter = copy.deepcopy(SPEC)
    stricter["metrics"][0]["threshold"]["min"] = 0.95
    stricter["slices"][0]["min"] = 0.99
    assert gate.integrity_check(base, base, stricter, SPEC) == []
    new_version = copy.deepcopy(SPEC)
    new_version["eval_set_version"] = "v3"
    new_version["metrics"][0]["threshold"]["min"] = 0.1           # a new eval set legitimately restarts the ratchet
    assert gate.integrity_check(base, base, new_version, SPEC) == []


# --- slice_check ----------------------------------------------------------------------------------------


def test_slice_regression_hidden_by_a_good_average_is_blocked(gate):
    base = make_report()
    pr = make_report(fail={(0, 1), (0, 2), (1, 3)})          # 3 of 10 money trials fail, overall 17/20 = 0.85
    blocked, lines = gate.slice_check(pr, base, SPEC)
    assert blocked == ["slice:money/pass_rate"]
    assert "BLOCK" in lines[0]


def test_slice_that_lost_all_its_rows_is_blocked_not_skipped(gate):
    base = make_report()
    pr = make_report(slices={})                              # every item relabelled out of the slice
    blocked, lines = gate.slice_check(pr, base, SPEC)
    assert blocked == ["slice:money/pass_rate"]
    assert "no rows for this slice" in lines[0]


def test_non_blocking_slice_only_warns(gate):
    base = make_report()
    spec = copy.deepcopy(SPEC)
    spec["slices"][0]["blocking"] = False
    blocked, lines = gate.slice_check(make_report(fail={(0, 1), (0, 2), (1, 3)}), base, spec)
    assert blocked == [] and "warn" in lines[0]


def test_clean_slice_passes(gate):
    base = make_report()
    assert gate.slice_check(base, base, SPEC)[0] == []


# --- the committed v2 artefacts ----------------------------------------------------------------------------


def test_committed_v2_baseline_is_trustworthy_and_merges_against_itself(gate):
    path = ROOT / "reports/baseline_v2.json"
    spec_path = ROOT / "config/metric_spec_v2.yaml"
    if not path.is_file():
        pytest.skip("baseline_v2.json is generated by lab9.eval (M5)")
    import yaml

    base = json.loads(path.read_text(encoding="utf-8"))
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    assert gate.integrity_check(base, base, spec, spec) == []
    blocked, _ = gate.check(base, base, spec, spec)
    assert blocked == [], "the baseline must merge against itself or every PR is blocked"
    assert spec["metrics"][[m["id"] for m in spec["metrics"]].index("pass_hat_5")]["threshold"]["min"] >= 0.8


# --- regression_guard: same score as main, different failing trials ---------------------------------------

GUARD_SPEC = {**SPEC, "regression_guard": {"metrics": ["pass_rate"], "max_new_failures": 0, "blocking": True}}


def test_same_failure_count_on_other_trials_is_invisible_to_thresholds_but_not_to_the_guard(gate):
    base = make_report(fail={(0, 1)})                        # main already fails one trial
    pr = make_report(fail={(0, 2)})                          # the PR fails one too, a DIFFERENT trial
    assert pr["metrics"] == base["metrics"]                  # every average is identical
    blocked, _ = gate.check(pr, base, SPEC, None)
    assert blocked == [], "without the guard the gate cannot tell them apart"
    blocked, lines = gate.check(pr, base, GUARD_SPEC, None)
    assert blocked == ["regression:pass_rate"]
    assert "E-0@2" in lines[-1] and "BLOCK" in lines[-1]


def test_guard_does_not_flag_fixes_or_an_identical_run(gate):
    base = make_report(fail={(0, 1), (1, 2)})
    assert gate.regression_guard(base, base, GUARD_SPEC) == ([], [gate.regression_guard(base, base, GUARD_SPEC)[1][0]])
    assert gate.regression_guard(make_report(), base, GUARD_SPEC)[0] == []            # fewer failures than main: fine
    assert gate.regression_guard(make_report(fail={(0, 1)}), base, GUARD_SPEC)[0] == []   # a strict subset of main's failures


def test_guard_allowance_and_non_blocking_mode(gate):
    base = make_report()
    pr = make_report(fail={(2, 3)})
    assert gate.regression_guard(pr, base, GUARD_SPEC)[0] == ["regression:pass_rate"]
    lenient = {**SPEC, "regression_guard": {"metrics": ["pass_rate"], "max_new_failures": 1, "blocking": True}}
    assert gate.regression_guard(pr, base, lenient)[0] == []
    advisory = {**SPEC, "regression_guard": {"metrics": ["pass_rate"], "max_new_failures": 0, "blocking": False}}
    blocked, lines = gate.regression_guard(pr, base, advisory)
    assert blocked == [] and "warn" in lines[0]


def test_guard_ignores_trials_with_no_value_and_spec_without_a_guard(gate):
    base = make_report()
    assert gate.regression_guard(base, base, SPEC) == ([], [])                         # no guard configured
    pr = make_report(fail={(2, 3)})
    row = next(r for r in pr["rows"] if (r["item_id"], r["seed"]) == ("E-2", 3))         # the failing trial itself
    row["pass_rate"] = None                                                             # masked: integrity_check's job, not the guard's
    assert gate.regression_guard(pr, base, GUARD_SPEC)[0] == []


@pytest.mark.parametrize("edit,needle", [
    (lambda s: s.pop("regression_guard"), "regression_guard was removed"),
    (lambda s: s["regression_guard"].__setitem__("max_new_failures", 3), "max_new_failures raised"),
    (lambda s: s["regression_guard"].__setitem__("metrics", []), "no longer guarded"),
    (lambda s: s["regression_guard"].__setitem__("blocking", False), "no longer blocking"),
])
def test_the_guard_cannot_be_loosened_or_removed_on_the_same_eval_set(gate, edit, needle):
    base = make_report()
    loose = copy.deepcopy(GUARD_SPEC)
    edit(loose)
    assert any(needle in p for p in gate.integrity_check(base, base, loose, GUARD_SPEC)), needle
    assert gate.integrity_check(base, base, GUARD_SPEC, GUARD_SPEC) == []


def test_committed_v2_spec_turns_the_guard_on():
    import yaml

    spec = yaml.safe_load((ROOT / "config/metric_spec_v2.yaml").read_text(encoding="utf-8"))
    g = spec["regression_guard"]
    assert g["blocking"] is True and g["max_new_failures"] == 0 and "pass_rate" in g["metrics"]
