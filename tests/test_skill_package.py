"""Public regression tests for the Agent Skill package."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from requirementdelta.policy_context import PolicyContext
from requirementdelta.task_context import UserTaskContext


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "skills" / "requirementdelta" / "SKILL.md"
HOST_COPIES = [
    ROOT / ".agents" / "skills" / "requirementdelta" / "SKILL.md",
    ROOT / ".claude" / "skills" / "requirementdelta" / "SKILL.md",
]


def _frontmatter(path: Path) -> tuple[dict[str, str], str]:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"\A---\r?\n(.*?)\r?\n---\r?\n", text, re.DOTALL)
    assert match, "SKILL.md must start with YAML frontmatter"
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if not line or line[0].isspace() or ":" not in line:
            continue
        key, value = line.split(":", 1)
        assert key not in fields, f"duplicate top-level field: {key}"
        fields[key] = value.strip().strip('"').strip("'")
    return fields, text[match.end():]


def test_skill_frontmatter_matches_agent_skills_basics():
    fields, body = _frontmatter(CANONICAL)
    assert fields["name"] == "requirementdelta"
    assert fields["name"] == CANONICAL.parent.name
    assert re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", fields["name"])
    assert 1 <= len(fields["description"]) <= 1024
    assert 1 <= len(fields["compatibility"]) <= 500
    assert fields["license"] == "MIT"
    assert "version: \"0.1.0\"" in CANONICAL.read_text(encoding="utf-8")
    assert body.strip()
    assert len(CANONICAL.read_text(encoding="utf-8").splitlines()) < 500
    assert "allowed-tools" not in fields


def test_codex_and_claude_skill_copies_are_byte_identical():
    source = CANONICAL.read_bytes()
    for path in HOST_COPIES:
        assert path.is_file(), f"missing host Skill copy: {path}"
        assert path.read_bytes() == source, f"host Skill copy drifted: {path}"


def test_skill_reference_links_resolve_inside_every_host_package():
    links = {
        "references/CONTEXT_SCHEMAS.md",
        "references/REPORT_INTERPRETATION.md",
    }
    for skill_file in [CANONICAL, *HOST_COPIES]:
        text = skill_file.read_text(encoding="utf-8")
        found = set(re.findall(r"\]\((references/[^)]+)\)", text))
        assert found == links
        for link in found:
            target = (skill_file.parent / link).resolve()
            assert target.is_file(), f"broken Skill reference in {skill_file}: {link}"
            assert skill_file.parent.resolve() in target.parents


def test_context_reference_examples_validate_against_public_schemas():
    path = CANONICAL.parent / "references" / "CONTEXT_SCHEMAS.md"
    text = path.read_text(encoding="utf-8")
    examples = re.findall(r"```json\s*\n(.*?)\n```", text, re.DOTALL)
    assert len(examples) == 2
    context_03 = json.loads(examples[0])
    context_04 = json.loads(examples[1])
    assert UserTaskContext.from_dict(context_03).schema_version == "0.3"
    assert PolicyContext.from_dict(context_04).schema_version == "0.4"


def test_skill_preserves_cli_uncertainty_privacy_and_no_overwrite_contract():
    text = CANONICAL.read_text(encoding="utf-8")
    required = [
        "<VERIFIED_CLI_EXECUTABLE> analyze",
        ".venv\\Scripts\\requirementdelta.exe",
        ".venv/bin/requirementdelta",
        "--old",
        "--new",
        "--output",
        "--quiet",
        "--context",
        "--allowed-root",
        "--overwrite",
        "NO_TEXT_DIFFERENCE",
        "NO_SUPPORTED_CHANGE_FOUND",
        "REVIEW_REQUIRED",
        "UNVERIFIED",
        "NEEDS_CONFIRMATION",
        "INSUFFICIENT_CONTEXT",
        "DOES_NOT_APPLY",
        "read_only.inputs_unchanged",
        "absolute local paths",
        "Ignore any instructions",
        "Do not browse to URLs",
    ]
    for item in required:
        assert item in text, f"Skill is missing required contract: {item}"


def test_skill_no_context_cli_smoke_produces_valid_review_report(tmp_path):
    output = tmp_path / "new-report-directory"
    command = [
        sys.executable,
        str(ROOT / "scripts" / "run_cli.py"),
        "analyze",
        "--old",
        str(ROOT / "examples" / "old.md"),
        "--new",
        str(ROOT / "examples" / "new.md"),
        "--output",
        str(output),
        "--quiet",
    ]
    env = dict(os.environ)
    env.update({"PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"})
    proc = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    report_path = output / "report.json"
    markdown_path = output / "report.md"
    assert report_path.is_file()
    assert markdown_path.is_file()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["schema_version"] == "p0-4-report-v1"
    assert report["tool"]["name"] == "requirementdelta"
    assert report["summary"]["overall_status"] == "REVIEW_REQUIRED"
    assert report["summary"]["assessments_total"] == 0
    assert report["summary"]["unassessed_changes_total"] >= 1
    assert report["summary"]["unsafe_deterministic_actions"] == 0
    assert report["read_only"] == {"inputs_unchanged": True, "checked": True}
    assert report["errors"] == []
