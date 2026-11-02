"""P0-4 end-to-end: five fully synthetic workflows."""
from __future__ import annotations

import json
from pathlib import Path

from test_p0_4_cli import (
    AI_NEW,
    AI_OLD,
    ctx_03,
    ctx_04,
    load_report,
    run_cli,
    write_context,
    write_pair,
)
from test_p0_4_report import verify_report_evidence

from requirementdelta.changes import analyze
from requirementdelta.ingest import read_pair

P = Path(__file__).resolve().parents[1]


def test_five_synthetic_end_to_end_cases(tmp_path):
    # 1) ordinary text change, no context
    old, new = write_pair(
        tmp_path / "01",
        "项目“星辰”的参与者必须提交PDF。\n",
        "项目“星辰”的参与者必须提交ZIP。\n",
    )
    assert run_cli(tmp_path, old, new, output="out01") == 0
    report = load_report(tmp_path, "out01")
    assert report["summary"]["overall_status"] == "REVIEW_REQUIRED"
    assert report["summary"]["changes_total"] == 1
    assert report["summary"]["assessments_total"] == 0

    # 2) project-scoped applicability with 0.3 context
    context = write_context(tmp_path / "ctx03.json", ctx_03())
    assert run_cli(tmp_path, old, new, context=context, output="out02") == 0
    report = load_report(tmp_path, "out02")
    assert report["summary"]["assessments_total"] == 1
    assert report["assessments"][0]["applicability_status"] == "APPLIES"
    assert report["assessments"][0]["action_status"] == "ACTION_REVIEW_REQUIRED"
    verify_report_evidence(report, *read_pair(old, new, tmp_path / "01"))

    # 3) controlled AI policy with exact 0.4 context
    ai_old, ai_new = write_pair(tmp_path / "03", AI_OLD, AI_NEW)
    exact = write_context(tmp_path / "ctx04.json", ctx_04())
    assert run_cli(tmp_path, ai_old, ai_new, context=exact, output="out03") == 0
    report = load_report(tmp_path, "out03")
    policy = [a for a in report["assessments"] if a.get("source") == "P0_3_2"]
    assert any(a["applicability_status"] == "APPLIES" for a in policy)
    assert any(a["recommended_actions"] for a in policy)
    verify_report_evidence(report, *read_pair(ai_old, ai_new, tmp_path / "03"))

    # 4) alias requires confirmation and has no action
    alias = write_context(tmp_path / "ctx_alias.json", ctx_04(program="GSoC"))
    assert run_cli(tmp_path, ai_old, ai_new, context=alias, output="out04") == 0
    report = load_report(tmp_path, "out04")
    assert report["summary"]["recommended_actions_total"] == 0
    policy = [a for a in report["assessments"] if a.get("source") == "P0_3_2"]
    assert policy and all(a["applicability_status"] == "NEEDS_CONFIRMATION" for a in policy)

    # 5) missing input fails closed with an UNVERIFIED report
    missing = tmp_path / "05" / "missing.md"
    missing.parent.mkdir(parents=True)
    (tmp_path / "05" / "new.md").write_text("新文。\n", encoding="utf-8")
    assert run_cli(tmp_path, missing, tmp_path / "05" / "new.md", output="out05") == 2
    report = load_report(tmp_path, "out05")
    assert report["summary"]["overall_status"] == "UNVERIFIED"
    assert report["summary"]["changes_total"] == 0
    assert report["summary"]["assessments_total"] == 0
    assert report["inputs"]["old"]["error_code"] == "FILE_NOT_FOUND"




