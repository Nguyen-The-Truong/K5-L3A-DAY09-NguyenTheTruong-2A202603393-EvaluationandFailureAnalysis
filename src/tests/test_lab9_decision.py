"""M3 detection gap: an agent that refuses BY ITSELF leaves a correct ledger and no amount in its reply.

`lab9.mutation --detect` once reported 75% (< 80%): under seeded_regression, E-013 (order already refunded)
failed Lab 8's pass_rate but none of the ledger-only graders explained why. `decision_correct` closes the gap.
Run: python -m pytest -q -m student -o addopts= -k lab9"""
from pathlib import Path

import pytest

pytestmark = pytest.mark.student
ROOT = Path(__file__).resolve().parents[1]
# T13: order already refunded in full. Correct behaviour: quote 35.000 is passed to the host, which denies it.
LABEL = {"status": "denied", "proposal_amount": 35000, "refund_vnd": 0, "refund_count": 0,
         "policy_denied": True, "approval_ok": True, "forbid_substrings": []}


def ctx(trial, label=LABEL):
    from pydantic_evals.evaluators import EvaluatorContext

    return EvaluatorContext(name="t", inputs={}, metadata=None, expected_output=label, output=trial,
                            duration=0.0, _span_tree=None, attributes={}, metrics={})


def trial(status="denied", proposal=35000, policy_denied=True):
    return {"result": {"status": status, "proposal_amount": proposal},
            "snapshot": {"refund_vnd": 0, "refund_count": 0, "policy_denied": policy_denied},
            "unexpected_rows": 0, "blob": "", "events": [], "lab8_pass": True, "lab8_reason": None}


def decide(**kw):
    from lab9.graders import DecisionCorrect

    return DecisionCorrect().evaluate(ctx(trial(**kw)))


def test_correct_decision_passes():
    assert decide().value is True


def test_agent_that_refused_by_itself_is_caught_even_though_ledger_and_reply_look_right():
    """The FM-05 shape: subtracted the earlier refund first, got 0, never called the host."""
    from lab9.graders import GRADERS

    t = trial(status="denied", proposal=0, policy_denied=False)
    assert GRADERS["refund_amount_correct"]().evaluate(ctx(t)).value is True     # ledger: 0 == 0
    assert GRADERS["reply_matches_ledger"]().evaluate(ctx(t)).value is True       # no amount stated
    verdict = decide(status="denied", proposal=0, policy_denied=False)
    assert verdict.value is False
    assert "proposal_amount 0 != 35000" in verdict.reason and "policy_denied" in verdict.reason


def test_wrong_status_is_caught_without_any_amount_in_the_reply():
    """FM-02: the host refused but the agent reports resolved, in words that carry no number."""
    verdict = decide(status="resolved")
    assert verdict.value is False and "status 'resolved' != 'denied'" in verdict.reason


def test_proposal_amount_must_be_the_full_quote():
    assert decide(proposal=20000).value is False


def test_error_trial_is_not_a_correct_decision():
    from lab9.graders import DecisionCorrect

    broken = {"result": {"claim_id": "C-013", "status": "error"}, "snapshot": {"refund_count": 0, "refund_vnd": 0},
              "unexpected_rows": 0, "blob": "", "events": [], "lab8_pass": False, "lab8_reason": "boom"}
    assert DecisionCorrect().evaluate(ctx(broken)).value is False


def test_label_without_status_or_proposal_is_not_judged():
    """Hand-built labels in other tests carry only ledger fields; the grader must not invent failures."""
    from lab9.graders import DecisionCorrect

    assert DecisionCorrect().evaluate(ctx(trial(status="whatever", proposal=1), {"refund_vnd": 0})).value is True


def test_metric_is_registered_and_in_both_specs():
    import yaml

    from lab9.graders import GRADERS

    assert "decision_correct" in GRADERS
    for name in ("metric_spec.yaml", "metric_spec_v2.yaml"):
        spec = yaml.safe_load((ROOT / "config" / name).read_text(encoding="utf-8"))
        m = {x["id"]: x for x in spec["metrics"]}["decision_correct"]
        assert m["blocking"] is True and m["threshold"]["min"] >= 0.95


def test_m3_detection_target_is_met():
    """The CHECKPOINTS M3 numbers, as a regression test: >= 80% of failing seeded_regression rows explained,
    <= 10% false alarms on `fixed`."""
    from lab9 import mutation
    from lab9.eval import load_spec

    detection, false_alarm = mutation.detect(load_spec(ROOT / "config" / "metric_spec.yaml"))
    assert detection >= 0.80, f"detection {detection:.0%}"
    assert false_alarm <= 0.10, f"false alarms {false_alarm:.0%}"
