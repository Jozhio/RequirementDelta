"""P0-4 CLI, report files, exit codes, Unicode paths and safety tests."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from requirementdelta import cli
from requirementdelta.workflow import build_error_report

P = Path(__file__).resolve().parents[1]


def write_pair(root: Path, old: str, new: str):
    root.mkdir(parents=True, exist_ok=True)
    (root / "old.md").write_bytes(old.encode("utf-8"))
    (root / "new.md").write_bytes(new.encode("utf-8"))
    return root / "old.md", root / "new.md"


def write_context(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def ctx_03(project="星辰", participating=True):
    return {
        "schema_version": "0.3",
        "confirmed_by_user": True,
        "facts": [
            {"field": "project", "value": project},
            {"field": "participating", "value": participating},
        ],
        "completed_tasks": [],
        "pending_tasks": [],
    }


def ctx_04(program="Applying to Example Summer of Code", code=True, comments=False):
    return {
        "schema_version": "0.4",
        "confirmed_by_user": True,
        "program": program,
        "role": None,
        "facts": [
            {"field": "participating", "value": True},
            {"field": "condition:uses_ai_for_code", "value": code},
            {"field": "condition:uses_ai_for_comments", "value": comments},
        ],
        "completed_tasks": [],
        "pending_tasks": [],
    }


AI_OLD = (
    "# Student Guide\n\n"
    "## Applying to Example Summer of Code\n\n"
    "Background text with no obligations.\n"
)
AI_NEW = AI_OLD + (
    "\n### AI Policies\n\n"
    "Participants should follow these guidelines:\n\n"
    "1. Do not use AI generated comments in any issues or PRs, use your own voice.\n"
    "2. Always disclose if AI was used in the code.\n"
)


def run_cli(tmp_path, old, new, *, context=None, output="out", allowed_root=None, extra=()):
    args = [
        "analyze",
        "--old",
        str(old),
        "--new",
        str(new),
        "--output",
        str(tmp_path / output),
        "--quiet",
        *extra,
    ]
    if context is not None:
        args += ["--context", str(context)]
    if allowed_root is not None:
        args += ["--allowed-root", str(allowed_root)]
    return cli.main(args)


def load_report(tmp_path, output="out"):
    return json.loads((tmp_path / output / "report.json").read_text(encoding="utf-8"))


def test_cli_no_context_creates_stable_report(tmp_path):
    old, new = write_pair(
        tmp_path / "in",
        "项目“星辰”的参与者必须提交PDF。\n",
        "项目“星辰”的参与者必须提交ZIP。\n",
    )
    code = run_cli(tmp_path, old, new)
    assert code == 0
    report = load_report(tmp_path)
    assert report["schema_version"] == "p0-4-report-v1"
    assert report["summary"]["overall_status"] == "REVIEW_REQUIRED"
    assert report["summary"]["changes_total"] == 1
    assert report["summary"]["assessments_total"] == 0
    assert report["summary"]["unassessed_changes_total"] == 1
    assert report["inputs"]["old"]["status"] == "READABLE"
    assert report["read_only"]["inputs_unchanged"] is True
    assert (tmp_path / "out/report.md").is_file()
    md = (tmp_path / "out/report.md").read_text(encoding="utf-8")
    assert "未进行适用性判断" in md
    assert "已确认不存在变化" not in md


def test_cli_03_context_applicability_action(tmp_path):
    old, new = write_pair(
        tmp_path / "in",
        "项目“星辰”的参与者必须提交PDF。\n",
        "项目“星辰”的参与者必须提交ZIP。\n",
    )
    context = write_context(tmp_path / "ctx.json", ctx_03())
    code = run_cli(tmp_path, old, new, context=context)
    assert code == 0
    report = load_report(tmp_path)
    assert report["summary"]["assessments_total"] == 1
    assessment = report["assessments"][0]
    assert assessment["source"] == "P0_3"
    assert assessment["applicability_status"] == "APPLIES"
    assert assessment["action_status"] == "ACTION_REVIEW_REQUIRED"
    assert assessment["task_status"] == "UNKNOWN"
    assert assessment["recommended_actions"][0]["task_id"] == "submit:ZIP"
    assert assessment["recommended_actions"][0]["executes_external_action"] is False


def test_cli_04_policy_context_and_alias(tmp_path):
    old, new = write_pair(tmp_path / "in", AI_OLD, AI_NEW)
    exact = write_context(tmp_path / "ctx_exact.json", ctx_04())
    code = run_cli(tmp_path, old, new, context=exact, output="out_exact")
    assert code == 0
    report = load_report(tmp_path, "out_exact")
    policy = [
        item for item in report["assessments"] if item.get("source") == "P0_3_2"
    ]
    assert policy
    assert any(item["applicability_status"] == "APPLIES" for item in policy)
    assert any(item["recommended_actions"] for item in policy)
    assert report["policy_sections"]
    assert report["summary"]["unassessed_changes_total"] == 0

    alias = write_context(tmp_path / "ctx_alias.json", ctx_04(program="GSoC"))
    code = run_cli(tmp_path, old, new, context=alias, output="out_alias")
    assert code == 0
    report = load_report(tmp_path, "out_alias")
    policy = [
        item for item in report["assessments"] if item.get("source") == "P0_3_2"
    ]
    assert policy
    assert all(item["applicability_status"] == "NEEDS_CONFIRMATION" for item in policy)
    assert all(not item["recommended_actions"] for item in policy)


def test_cli_04_missing_fact_needs_confirmation(tmp_path):
    old, new = write_pair(tmp_path / "in", AI_OLD, AI_NEW)
    data = ctx_04()
    data["facts"] = [
        fact for fact in data["facts"] if fact["field"] != "condition:uses_ai_for_code"
    ]
    context = write_context(tmp_path / "ctx.json", data)
    code = run_cli(tmp_path, old, new, context=context)
    assert code == 0
    report = load_report(tmp_path)
    disclosure = [
        item
        for item in report["assessments"]
        if item.get("source") == "P0_3_2"
        and "Always disclose" in (item.get("policy_rule") or {}).get("requirement_text", "")
    ]
    assert disclosure
    assert disclosure[0]["applicability_status"] == "NEEDS_CONFIRMATION"
    assert "condition:uses_ai_for_code" in disclosure[0]["missing_information"]
    assert disclosure[0]["recommended_actions"] == []


def test_cli_error_inputs_fail_closed(tmp_path):
    good_old, _ = write_pair(tmp_path / "in", "旧文。\n", "新文。\n")
    missing_old = tmp_path / "in" / "missing.md"
    good_new = tmp_path / "in" / "new.md"

    code = run_cli(tmp_path, missing_old, good_new, output="out_missing")
    assert code == 2
    report = load_report(tmp_path, "out_missing")
    assert report["summary"]["overall_status"] == "UNVERIFIED"
    assert report["inputs"]["old"]["error_code"] == "FILE_NOT_FOUND"
    assert report["changes"] == []
    assert report["summary"]["assessments_total"] == 0
    md = (tmp_path / "out_missing/report.md").read_text(encoding="utf-8")
    assert "UNVERIFIED" in md
    assert "未发现可确认变化" not in md

    bad_new = tmp_path / "in" / "bad.md"
    bad_new.write_bytes(b"\xff\xfe invalid")
    code = run_cli(tmp_path, good_old, bad_new, output="out_bad_utf8")
    assert code == 2
    report = load_report(tmp_path, "out_bad_utf8")
    assert report["inputs"]["new"]["error_code"] == "INVALID_UTF8"

    pdf = tmp_path / "in" / "scan.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    code = run_cli(tmp_path, good_old, pdf, output="out_pdf")
    assert code == 2
    report = load_report(tmp_path, "out_pdf")
    assert report["inputs"]["new"]["status"] == "UNSUPPORTED_FORMAT"


def test_cli_invalid_context_exit2(tmp_path):
    old, new = write_pair(tmp_path / "in", AI_OLD, AI_NEW)
    context = tmp_path / "ctx.json"
    context.write_text('{"schema_version":"9.9"}', encoding="utf-8")
    code = run_cli(tmp_path, old, new, context=context)
    assert code == 2
    report = load_report(tmp_path)
    assert report["summary"]["overall_status"] == "UNVERIFIED"
    assert any("context" in error.lower() for error in report["errors"])
    assert report["assessments"] == []


def test_cli_overwrite_refusal_and_flag(tmp_path):
    old, new = write_pair(tmp_path / "in", "旧文。\n", "新文。\n")
    assert run_cli(tmp_path, old, new) == 0
    assert run_cli(tmp_path, old, new) == 2
    assert run_cli(tmp_path, old, new, extra=("--overwrite",)) == 0


def test_cli_output_path_conflicts(tmp_path):
    old, new = write_pair(tmp_path / "in", "旧文。\n", "新文。\n")
    code = cli.main(
        [
            "analyze",
            "--old",
            str(old),
            "--new",
            str(new),
            "--output",
            str(old),
            "--quiet",
        ]
    )
    assert code == 2

    report_input = tmp_path / "same" / "report.json"
    report_input.parent.mkdir()
    report_input.write_text("旧文。\n", encoding="utf-8")
    new2 = tmp_path / "same" / "new.md"
    new2.write_text("新文。\n", encoding="utf-8")
    code = cli.main(
        [
            "analyze",
            "--old",
            str(report_input),
            "--new",
            str(new2),
            "--output",
            str(report_input.parent),
            "--quiet",
        ]
    )
    assert code == 2


def test_cli_unicode_paths_and_read_only(tmp_path):
    base = tmp_path / "通知 2026" / "中文目录"
    old, new = write_pair(base, "项目“星辰”的参与者必须提交PDF。\n", "项目“星辰”的参与者必须提交ZIP。\n")
    old_bytes = old.read_bytes()
    new_bytes = new.read_bytes()
    code = run_cli(tmp_path, old, new, output="中文输出")
    assert code == 0
    report = load_report(tmp_path, "中文输出")
    assert report["inputs"]["old"]["path"] == str(old.resolve())
    assert old.read_bytes() == old_bytes
    assert new.read_bytes() == new_bytes


def test_cli_quiet_and_summary(tmp_path, capsys):
    old, new = write_pair(tmp_path / "in", "旧文。\n", "新文。\n")
    assert run_cli(tmp_path, old, new, output="out_quiet") == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert cli.main(
        [
            "analyze",
            "--old",
            str(old),
            "--new",
            str(new),
            "--output",
            str(tmp_path / "out_loud"),
        ]
    ) == 0
    captured = capsys.readouterr()
    assert "RequirementDelta 0.1.0" in captured.out


def test_cli_no_text_difference_and_no_supported_change_wording(tmp_path):
    old, new = write_pair(tmp_path / "same", "同一文本。\n", "同一文本。\n")
    assert run_cli(tmp_path, old, new, output="out_same") == 0
    report = load_report(tmp_path, "out_same")
    assert report["summary"]["overall_status"] == "NO_TEXT_DIFFERENCE"
    md = (tmp_path / "out_same/report.md").read_text(encoding="utf-8")
    assert "不等于已确认不存在变化" in md

    old2, new2 = write_pair(
        tmp_path / "blank",
        "# Guide\n\nText.\n",
        "# Guide\n\n\nText.\n",
    )
    assert run_cli(tmp_path, old2, new2, output="out_blank") == 0
    report = load_report(tmp_path, "out_blank")
    assert report["summary"]["overall_status"] == "NO_SUPPORTED_CHANGE_FOUND"
    md = (tmp_path / "out_blank/report.md").read_text(encoding="utf-8")
    assert "不等于已确认不存在变化" in md


def test_cli_internal_error_exit3(tmp_path, monkeypatch):
    old, new = write_pair(tmp_path / "in", "旧文。\n", "新文。\n")

    def fail(*args, **kwargs):
        return build_error_report(args[0], args[1], "evidence validation failed")

    monkeypatch.setattr(cli, "build_report", fail)
    code = run_cli(tmp_path, old, new)
    assert code == 3
    report = load_report(tmp_path)
    assert report["summary"]["overall_status"] == "UNVERIFIED"


def test_cli_default_allowed_root_and_context_outside_root(tmp_path):
    old, new = write_pair(tmp_path / "in", AI_OLD, AI_NEW)
    context = write_context(tmp_path / "outside" / "ctx.json", ctx_04())
    code = run_cli(tmp_path, old, new, context=context, allowed_root=tmp_path / "in")
    assert code == 0
    assert load_report(tmp_path)["summary"]["assessments_total"] > 0


def test_cli_module_entrypoint(tmp_path):
    old, new = write_pair(tmp_path / "in", "旧文。\n", "新文。\n")
    env = {
        **os.environ,
        "PYTHONPATH": str(P / "src"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONIOENCODING": "utf-8",
    }
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "requirementdelta",
            "analyze",
            "--old",
            str(old),
            "--new",
            str(new),
            "--output",
            str(tmp_path / "out_module"),
            "--quiet",
        ],
        cwd=P,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "out_module/report.json").is_file()
