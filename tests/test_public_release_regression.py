"""Public regressions replacing official-source dependent internal tests.

All documents are synthetic and no external source snapshots are bundled.
"""
from __future__ import annotations
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from requirementdelta.applicability import assess_change
from requirementdelta.changes import analyze
from requirementdelta.ingest import read_pair
from requirementdelta.evidence import verify_evidence
from requirementdelta.task_context import UserTaskContext


def snapshots(tmp_path: Path, old: str, new: str):
    (tmp_path / "old.md").write_text(old, encoding="utf-8")
    (tmp_path / "new.md").write_text(new, encoding="utf-8")
    return read_pair("old.md", "new.md", tmp_path)


def run_cli(tmp_path: Path, old: Path, new: Path, *, context=None):
    output = tmp_path / "output"
    cmd = [sys.executable, "-m", "requirementdelta", "analyze", "--old",
           str(old), "--new", str(new), "--output", str(output)]
    if context is not None:
        p = tmp_path / "context.json"
        p.write_text(json.dumps(context), encoding="utf-8")
        cmd += ["--context", str(p)]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=25)
    assert (output / "report.json").exists()
    assert (output / "report.md").exists()
    return proc, json.loads((output / "report.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("project,expected", [
    ("Project Aster", "APPLIES"),
    ("Project Cobalt", "DOES_NOT_APPLY"),
    (None, "NEEDS_CONFIRMATION"),
])
def test_synthetic_table_project_scope_replaces_official_row(tmp_path, project, expected):
    old, new = snapshots(
        tmp_path,
        "| **Project Title** | **Project Idea Link** | **Description** | **Hours** |\n"
        "| --- | --- | --- | --- |\n"
        "| Project Aster | https://example.invalid/plan | Original synthetic project | 350 hours |\n",
        "| **Project Title** | **Project Idea Link** | **Description** | **Hours** |\n"
        "| --- | --- | --- | --- |\n"
        "| Project Aster | https://example.invalid/plan | Original synthetic project | 175 hours |\n",
    )
    change = next(c for c in analyze(old, new).changes if c.material_status == "CHANGED")
    assert verify_evidence(old, change.old_evidence)
    assert verify_evidence(new, change.new_evidence)
    facts = [{"field": "participating", "value": True}]
    if project is not None:
        facts.append({"field": "project", "value": project})
    context = UserTaskContext.from_dict({
        "schema_version": "0.3", "confirmed_by_user": True,
        "facts": facts, "completed_tasks": [], "pending_tasks": []
    })
    result = assess_change(change, old, new, context)
    assert result["applicability_status"] == expected
    assert len(result["evidence_refs"]["scope"]) == 2
    if expected != "APPLIES":
        assert not result["recommended_actions"]


def test_synthetic_end_to_end_evidence_and_readonly(tmp_path):
    old = tmp_path / "old.md"
    new = tmp_path / "new.md"
    old.write_text("Applicants must submit a signed PDF before 2027-02-15 18:00.\n", encoding="utf-8")
    new.write_text("Applicants must submit a signed ZIP before 2027-02-10 18:00.\n", encoding="utf-8")
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (old, new)}
    proc, report = run_cli(tmp_path, old, new)
    assert proc.returncode == 0, proc.stderr
    assert report["summary"]["overall_status"] == "REVIEW_REQUIRED"
    assert report["summary"]["changes_total"] >= 1
    assert report["summary"]["unsafe_deterministic_actions"] == 0
    assert report["read_only"]["inputs_unchanged"] is True
    for change in report["changes"]:
        for side, p in [("old", old), ("new", new)]:
            e = change.get(f"{side}_evidence")
            if e:
                assert e["quote"] in p.read_text(encoding="utf-8")
                assert e["doc_sha256"] == before[p.name]
    assert before == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (old, new)}


@pytest.mark.parametrize("uses_ai_code,expected", [
    (True, "APPLIES"),
    (False, "DOES_NOT_APPLY"),
])
def test_synthetic_policy_applicability_without_official_snapshot(tmp_path, uses_ai_code, expected):
    old = tmp_path / "old.md"
    new = tmp_path / "new.md"
    old.write_text(
        "# Example handbook\n\n## Applying to Example Summer of Code\n\nWelcome.\n",
        encoding="utf-8",
    )
    new.write_text(
        "# Example handbook\n\n## Applying to Example Summer of Code\n\nWelcome.\n"
        "\n### AI Policies\nParticipants should follow these guidelines:\n"
        "1. Always disclose if AI was used in the code.\n",
        encoding="utf-8",
    )
    context = {
        "schema_version": "0.4", "confirmed_by_user": True,
        "program": "Applying to Example Summer of Code", "role": None,
        "facts": [{"field": "participating", "value": True},
                  {"field": "condition:uses_ai_for_code", "value": uses_ai_code},
                  {"field": "condition:uses_ai_for_comments", "value": False}],
        "completed_tasks": [], "pending_tasks": [],
    }
    proc, report = run_cli(tmp_path, old, new, context=context)
    assert proc.returncode == 0, proc.stderr
    decisions = [x for x in report["assessments"] if x.get("source") == "P0_3_2"]
    assert any(x["applicability_status"] == expected for x in decisions)
    if expected == "DOES_NOT_APPLY":
        assert report["summary"]["recommended_actions_total"] == 0
    assert report["summary"]["unsafe_deterministic_actions"] == 0


def test_missing_document_fails_closed_without_official_fixture(tmp_path):
    new = tmp_path / "new.md"
    new.write_text("Example rule\n", encoding="utf-8")
    proc, report = run_cli(tmp_path, tmp_path / "not-there.md", new)
    assert proc.returncode == 2
    assert report["summary"]["overall_status"] == "UNVERIFIED"
    assert report["summary"]["changes_total"] == 0
    assert report["summary"]["recommended_actions_total"] == 0


def test_public_suite_does_not_require_internal_official_snapshot_or_metrics():
    here = Path(__file__).resolve().parents[1]
    assert not (here / "fixtures" / "official_p0_2").exists()
    assert not (here / "reports" / "p0_2" / "metrics.json").exists()
    assert not (here / "data").exists()
