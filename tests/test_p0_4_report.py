"""P0-4 report schema, Markdown traceability and evidence verification."""
from __future__ import annotations

import json

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

from requirementdelta.evidence import Evidence, verify_evidence
from requirementdelta.ingest import read_pair


def _verify_ref(snapshot, ref):
    assert ref, "missing evidence reference"
    assert verify_evidence(snapshot, Evidence(**ref)), ref


def verify_report_evidence(report, old, new):
    count = 0
    for change in report["changes"]:
        if change.get("old_evidence"):
            _verify_ref(old, change["old_evidence"])
            count += 1
        if change.get("new_evidence"):
            _verify_ref(new, change["new_evidence"])
            count += 1
    for assessment in report["assessments"]:
        refs = assessment.get("evidence_refs") or {}
        if refs.get("old"):
            _verify_ref(old, refs["old"])
            count += 1
        if refs.get("new"):
            _verify_ref(new, refs["new"])
            count += 1
        for scope in refs.get("scope") or []:
            _verify_ref(old if scope.get("role") == "old" else new, scope)
            count += 1
        for action in assessment.get("recommended_actions") or []:
            assert action["executes_external_action"] is False
    return count


def test_report_schema_and_03_evidence(tmp_path):
    old, new = write_pair(
        tmp_path / "in",
        "项目“星辰”的参与者必须提交PDF。\n",
        "项目“星辰”的参与者必须提交ZIP。\n",
    )
    context = write_context(tmp_path / "ctx.json", ctx_03())
    assert run_cli(tmp_path, old, new, context=context) == 0
    report = load_report(tmp_path)
    required = {
        "schema_version",
        "tool",
        "run",
        "inputs",
        "context",
        "comparison",
        "summary",
        "changes",
        "assessments",
        "review_items",
        "unverified_items",
        "coverage",
        "read_only",
        "errors",
    }
    assert required <= report.keys()
    assert report["changes"][0]["change_id"] == report["assessments"][0]["change_id"]
    assert report["summary"]["unassessed_changes_total"] == 0
    assert report["summary"]["unsafe_deterministic_actions"] == 0
    snaps = read_pair(old, new, tmp_path / "in")
    assert verify_report_evidence(report, *snaps) > 0
    assert report["assessments"][0]["task_status"] == "UNKNOWN"
    assert report["assessments"][0]["action_status"] == "ACTION_REVIEW_REQUIRED"


def test_report_schema_and_04_policy_evidence(tmp_path):
    old, new = write_pair(tmp_path / "in", AI_OLD, AI_NEW)
    context = write_context(tmp_path / "ctx.json", ctx_04())
    assert run_cli(tmp_path, old, new, context=context) == 0
    report = load_report(tmp_path)
    policy = [a for a in report["assessments"] if a.get("source") == "P0_3_2"]
    assert policy
    assert all(a.get("local_validation_status") == "VERIFIED" for a in policy)
    assert report["policy_sections"]
    assert report["summary"]["unsafe_deterministic_actions"] == 0
    snaps = read_pair(old, new, tmp_path / "in")
    assert verify_report_evidence(report, *snaps) > 0
    md = (tmp_path / "out/report.md").read_text(encoding="utf-8")
    assert "P0_3_2" in md
    assert "UNRESOLVED_POLICY_CLAUSE" in md or "未决" in md


def test_report_markdown_traceability(tmp_path):
    old, new = write_pair(tmp_path / "in", AI_OLD, AI_NEW)
    context = write_context(tmp_path / "ctx.json", ctx_04())
    assert run_cli(tmp_path, old, new, context=context) == 0
    report = load_report(tmp_path)
    md = (tmp_path / "out/report.md").read_text(encoding="utf-8")
    for change in report["changes"]:
        assert change["change_id"] in md
    for assessment in report["assessments"]:
        if assessment.get("recommended_actions"):
            for action in assessment["recommended_actions"]:
                assert action["evidence_ref"] in md
                assert action["task_id"] in md
    assert "人工复核" in md


def test_alias_report_lists_review_without_action(tmp_path):
    old, new = write_pair(tmp_path / "in", AI_OLD, AI_NEW)
    context = write_context(tmp_path / "ctx.json", ctx_04(program="GSoC"))
    assert run_cli(tmp_path, old, new, context=context) == 0
    report = load_report(tmp_path)
    assert report["summary"]["recommended_actions_total"] == 0
    assert report["review_items"]
    assert all(
        not item.get("executes_external_action")
        for item in report["review_items"]
    )
    md = (tmp_path / "out/report.md").read_text(encoding="utf-8")
    assert "NEEDS_CONFIRMATION" in md


def test_report_json_is_stable_and_utf8(tmp_path):
    old, new = write_pair(
        tmp_path / "通知",
        "旧版：申请截止 2026-12-08。\n",
        "新版：申请截止 2026-12-03。\n",
    )
    assert run_cli(tmp_path, old, new, output="输出") == 0
    path = tmp_path / "输出/report.json"
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    data = json.loads(text)
    assert data["schema_version"] == "p0-4-report-v1"
    assert json.dumps(data, ensure_ascii=False, sort_keys=True) == json.dumps(
        json.loads(text), ensure_ascii=False, sort_keys=True
    )
    assert "申请截止" in text
    md = (tmp_path / "输出/report.md").read_text(encoding="utf-8")
    assert "line" in md
    assert "bytes" in md
