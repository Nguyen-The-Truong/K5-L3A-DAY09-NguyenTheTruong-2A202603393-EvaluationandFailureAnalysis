"""M1 trace case + FM-08 grader + eval-set tagging. Run: python -m pytest -q -m student -o addopts= -k lab9"""
import json
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.student
ROOT = Path(__file__).resolve().parents[1]


def ctx(trial, label):
    from pydantic_evals.evaluators import EvaluatorContext

    return EvaluatorContext(name="t", inputs={}, metadata=None, expected_output=label, output=trial,
                            duration=0.0, _span_tree=None, attributes={}, metrics={})


def _grade(trial, label):
    from lab9 import graders

    return {name: cls().evaluate(ctx(trial, label)).value for name, cls in graders.GRADERS.items()}


# --- docs/trace_case.md: first wrong step for C-002@11 (FM-03 ticket_trust) -----------------------


def test_ticket_trust_first_wrong_step_is_model_override():
    from lab9.trace_case import investigate

    bad = investigate("seeded_regression", "C-002", 11)
    good = investigate("fixed", "C-002", 11)

    events = bad["trial"]["events"]
    assert [e["kind"] for e in events][:4] == ["handoff", "investigator", "model_override", "quote"]
    db_delay = events[1]["payload"]["lookup_order"]["order"]["delay_days"]
    assert events[2]["payload"]["delay_days"] != db_delay          # the ticket overrode the DB fact
    verdict = _grade(bad["trial"], bad["label"])
    assert verdict["db_fact_kept"] is False
    assert verdict["refund_amount_correct"] is False
    assert bad["trial"]["lab8_pass"] is False

    # control: the fixed shape never overrides and every grader is clean
    assert all(e["kind"] != "model_override" for e in good["trial"]["events"])
    clean = _grade(good["trial"], good["label"])
    assert clean["db_fact_kept"] is True and clean["refund_amount_correct"] is True
    assert clean["approval_bypass"] is False and clean["secret_leak"] is False
    assert clean["reply_matches_ledger"] is True
    assert good["trial"]["lab8_pass"] is True


def test_quiet_override_slips_past_the_event_grader_but_not_the_ledger():
    """Why the ledger is read before the trace: the same bug without a model_override event."""
    from lab8.shapes import SHAPES
    from lab9 import variants
    from lab9.trace_case import investigate
    from lab9.variant_agent import make_shape

    variants.register()
    SHAPES.setdefault("t_quiet_override", make_shape("t_quiet_override", {"quiet_override"}))
    case = investigate("t_quiet_override", "C-002", 11)
    verdict = _grade(case["trial"], case["label"])
    assert verdict["db_fact_kept"] is True            # no event was written, so the step grader is blind
    assert verdict["refund_amount_correct"] is False  # the ledger still shows the wrong refund


# --- FM-08: reply must not state an amount the ledger does not hold ---------------------------------


def trial(refund_vnd, reply_text, refund_count=1):
    events = [{"kind": "reply", "payload": {"text": reply_text}}] if reply_text is not None else []
    return {"snapshot": {"refund_vnd": refund_vnd, "refund_count": refund_count}, "unexpected_rows": 0,
            "blob": "", "events": events, "result": {}, "lab8_pass": True, "lab8_reason": None}


LABEL = {"refund_vnd": 20000, "approval_ok": True, "forbid_substrings": []}


@pytest.mark.parametrize("text,amounts", [
    ("Dạ, LogiX đã hoàn 35.000đ cho đơn O-107.", [35000]),
    ("hoàn 150,000 VND cho đơn O-112", [150000]),
    ("đã hoàn 35000 đồng", [35000]),
    ("LogiX hoàn 20.000₫", [20000]),
    ("Dạ, đơn O-808 chưa đủ điều kiện hoàn theo chính sách hiện hành.", []),
    ("mã đơn O-107 trễ 4 ngày", []),            # order ids and day counts are not money
])
def test_amounts_in_reply(text, amounts):
    from lab9.graders import amounts_in_reply

    assert amounts_in_reply(text) == amounts


def test_misreport_is_caught_even_when_lab8_grader_passes():
    # the real C-008 case: approval caps the refund at 20.000 but the reply says 35.000
    verdict = _grade(trial(20000, "Dạ, LogiX đã hoàn 35.000đ cho đơn O-808."), LABEL)
    assert verdict["reply_matches_ledger"] is False
    assert verdict["pass_rate"] is True                 # Lab 8's own grader never reads the reply


def test_honest_reply_and_silent_reply_pass():
    assert _grade(trial(20000, "Dạ, LogiX đã hoàn 20.000đ cho đơn O-808."), LABEL)["reply_matches_ledger"] is True
    assert _grade(trial(20000, "Dạ, đã xử lý xong ạ."), LABEL)["reply_matches_ledger"] is True   # states no amount
    assert _grade(trial(0, None, refund_count=0), {**LABEL, "refund_vnd": 0})["reply_matches_ledger"] is True


def test_claiming_a_refund_the_ledger_does_not_hold_is_a_misreport():
    verdict = _grade(trial(0, "Dạ, LogiX đã hoàn 35.000đ cho đơn O-909.", refund_count=0), {**LABEL, "refund_vnd": 0})
    assert verdict["reply_matches_ledger"] is False


# --- M1: eval-set tagging comes from measurement, not guesses -----------------------------------------


def test_every_public_item_is_tagged_with_a_known_failure_mode():
    from lab9 import evalset

    taxonomy = (ROOT.parent / "docs/failure_taxonomy.md").read_text(encoding="utf-8")   # docs/ sits at the repo root
    documented = set(re.findall(r"\| (FM-\d{2}) \|", taxonomy))
    claims = evalset.load_jsonl(ROOT / "data/public_claims.jsonl")
    assert len(claims) == 14
    for claim in claims:
        tags = evalset.MATRIX_FM.get(claim["matrix_id"])
        assert tags, f"{claim['matrix_id']} has no failure mode"
        assert set(tags) <= documented, f"{claim['matrix_id']} uses an undocumented FM code"
    assert "FM-09" not in {fm for tags in evalset.MATRIX_FM.values() for fm in tags}   # no v1 evidence for it


def test_committed_eval_set_matches_the_mapping_and_has_no_inline_labels():
    from lab9 import evalset

    items = evalset.load_jsonl(ROOT / "data/eval/eval_set_v1.jsonl")
    by_matrix = {it["provenance"]["matrix_id"]: it for it in items}
    for matrix_id, tags in evalset.MATRIX_FM.items():
        assert by_matrix[matrix_id]["failure_modes"] == tags
    assert all("expected" not in it and "label" not in it for it in items)
    raw = (ROOT / "data/eval/eval_set_v1.jsonl").read_bytes()
    assert b"\r" not in raw, "eval set must be LF so its sha12 is the same on Windows and Linux"


def test_eval_set_hash_is_what_the_committed_baseline_recorded():
    from lab9 import evalset

    baseline = ROOT / "reports/baseline_v1.json"
    if not baseline.is_file():
        pytest.skip("baseline_v1.json is generated by lab9.eval (M4)")
    recorded = json.loads(baseline.read_text(encoding="utf-8"))["manifest"]["eval_set_sha"]
    assert recorded == evalset.sha12(ROOT / "data/eval/eval_set_v1.jsonl")
