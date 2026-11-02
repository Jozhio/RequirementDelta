"""P0-3.2 frozen P321 acceptance cases (expected values fixed before implementation).

Synthetic documents only; frozen personas/benchmarks are not modified.
"""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from requirementdelta.applicability import assess  # noqa: F401  (0.3 compatibility import)
from requirementdelta.changes import analyze
from requirementdelta.ingest import read_pair
from requirementdelta.policy_applicability import (
    assess_policy_clause,
    assess_policy_section,
)
from requirementdelta.policy_context import PolicyContext
from requirementdelta.policy_scope import (
    find_policy_sections,
    validate_local_section_addition,
)

MISSING = object()
PROGRAM = "Applying to Example Summer of Code"

OLD_MIN = (
    "# Student Guide\n\n"
    "## Applying to Example Summer of Code\n\n"
    "Background text with no obligations.\n"
)
NEW_MIN = OLD_MIN + (
    "\n### AI Policies\n\n"
    "Participants should follow these guidelines:\n\n"
    "1. Do not use AI generated comments in any issues or PRs, use your own voice.\n"
    "2. Always disclose if AI was used in the code.\n"
)
NEW_FULL = OLD_MIN + (
    "\n### AI Policies\n\n"
    "We understand that the use of LLMs for development is evolving fast.\n"
    "Participants should not make use of AI for large portions of their projects, code, or any interaction with mentors and members of the organization.\n\n"
    "In summary participants should follow these guidelines:\n\n"
    "1. Do not use AI generated comments in any issues or PRs, use your own voice.\n"
    "2. Always disclose if AI was used in the code.\n"
    "3. Be ready to explain the code and/or answer any questions about the prompt, agent, or configuration that generate the code.\n"
    "4. Note that some projects may reject any AI code due to copyright concerns.\n"
    "5. Some projects may have additional policies on AI usage. Be sure to check with your mentor what they are.\n"
)
NEW_APPLICANTS = OLD_MIN + (
    "\n### AI Policies\n\n"
    "Applicants should follow these guidelines:\n\n"
    "1. Always disclose if AI was used in the code.\n"
)


def context(
    *,
    program=PROGRAM,
    participating=True,
    code=True,
    comments=False,
    role=None,
    completed=(),
    pending=(),
    extra_facts=(),
):
    facts = []
    if participating is not MISSING:
        facts.append({"field": "participating", "value": participating})
    if code is not MISSING:
        facts.append({"field": "condition:uses_ai_for_code", "value": code})
    if comments is not MISSING:
        facts.append({"field": "condition:uses_ai_for_comments", "value": comments})
    facts.extend(extra_facts)
    return {
        "schema_version": "0.4",
        "confirmed_by_user": True,
        "program": program,
        "role": role,
        "facts": facts,
        "completed_tasks": list(completed),
        "pending_tasks": list(pending),
    }


def write_pair(tmp_path: Path, old: str, new: str):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "old.md").write_bytes(old.encode("utf-8"))
    (tmp_path / "new.md").write_bytes(new.encode("utf-8"))
    return read_pair("old.md", "new.md", tmp_path)


def write_pair_bytes(tmp_path: Path, old: bytes, new: bytes):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "old.md").write_bytes(old)
    (tmp_path / "new.md").write_bytes(new)
    return read_pair("old.md", "new.md", tmp_path)


def find_change(snaps, needle: str, *, added_only: bool = False):
    for change in analyze(*snaps).changes:
        if change.new_evidence and needle in change.new_evidence.quote:
            if added_only and change.relation != "ADDED":
                continue
            return change
    raise AssertionError(f"no change containing {needle!r}")


def text_of_unresolved(summary: dict) -> str:
    return " ".join(item["quote"] for item in summary["unresolved_clauses"])


# ---------------------------------------------------------------------------
# P321-01 .. P321-04: core DISCLOSE / PROHIBITION applicability
# ---------------------------------------------------------------------------

def test_p321_01_disclosure_applies(tmp_path):
    snaps = write_pair(tmp_path, OLD_MIN, NEW_MIN)
    change = find_change(snaps, "Always disclose")
    result = assess_policy_clause(
        change, *snaps, PolicyContext.from_dict(context(code=True, comments=False))
    )
    assert result["applicability_status"] == "APPLIES"
    assert result["task_status"] == "UNKNOWN"
    assert result["action_status"] == "ACTION_REVIEW_REQUIRED"
    assert result["policy_rule"]["kind"] == "DISCLOSE"
    assert result["policy_rule"]["trigger"] == {
        "field": "condition:uses_ai_for_code",
        "operator": "EQ",
        "value": True,
    }
    assert result["local_validation"] == "LOCAL_SECTION_ADDITION"
    assert result["local_validation_status"] == "VERIFIED"
    assert result["evidence_status"] == "VERIFIED"
    assert result["upstream_material_status"] == "UNKNOWN"
    assert result["upstream_review_status"] == "NEEDS_REVIEW"
    assert len(result["recommended_actions"]) == 1
    action = result["recommended_actions"][0]
    assert action["task_id"] == "submit:ai_code_disclosure"
    assert action["progress_status"] == "ASK_PROGRESS"
    assert action["kind"] == "HUMAN_REVIEW_ONLY"
    assert action["executes_external_action"] is False


def test_p321_02_disclosure_not_applies(tmp_path):
    snaps = write_pair(tmp_path, OLD_MIN, NEW_MIN)
    change = find_change(snaps, "Always disclose")
    result = assess_policy_clause(
        change, *snaps, PolicyContext.from_dict(context(code=False))
    )
    assert result["applicability_status"] == "DOES_NOT_APPLY"
    assert result["task_status"] == "NOT_APPLICABLE"
    assert result["action_status"] == "NO_CURRENT_ACTION"
    assert result["recommended_actions"] == []
    assert result["local_validation_status"] == "VERIFIED"
    assert result["upstream_review_status"] == "NEEDS_REVIEW"


def test_p321_03_comment_prohibition_applies(tmp_path):
    snaps = write_pair(tmp_path, OLD_MIN, NEW_MIN)
    change = find_change(snaps, "Do not use AI generated comments")
    result = assess_policy_clause(
        change, *snaps, PolicyContext.from_dict(context(code=False, comments=True))
    )
    assert result["applicability_status"] == "APPLIES"
    assert result["task_status"] == "UNKNOWN"
    assert result["action_status"] == "ACTION_REVIEW_REQUIRED"
    assert result["policy_rule"]["kind"] == "PROHIBITION"
    assert result["recommended_actions"][0]["task_id"] == "review:ai_comments"
    assert result["recommended_actions"][0]["progress_status"] == "ASK_PROGRESS"


def test_p321_04_comment_prohibition_not_applies(tmp_path):
    snaps = write_pair(tmp_path, OLD_MIN, NEW_MIN)
    change = find_change(snaps, "Do not use AI generated comments")
    result = assess_policy_clause(
        change, *snaps, PolicyContext.from_dict(context(code=False, comments=False))
    )
    assert result["applicability_status"] == "DOES_NOT_APPLY"
    assert result["task_status"] == "NOT_APPLICABLE"
    assert result["action_status"] == "NO_CURRENT_ACTION"
    assert result["recommended_actions"] == []


# ---------------------------------------------------------------------------
# P321-05 .. P321-06: missing facts / exact program / alias rejection
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("needle", "missing_field", "kwargs"),
    [
        ("Always disclose", "condition:uses_ai_for_code", {"code": MISSING}),
        ("Do not use AI generated comments", "condition:uses_ai_for_comments", {"comments": MISSING}),
    ],
)
def test_p321_05_missing_behavior_fact(tmp_path, needle, missing_field, kwargs):
    snaps = write_pair(tmp_path, OLD_MIN, NEW_MIN)
    change = find_change(snaps, needle)
    result = assess_policy_clause(
        change, *snaps, PolicyContext.from_dict(context(**kwargs))
    )
    assert result["applicability_status"] == "NEEDS_CONFIRMATION"
    assert missing_field in result["missing_information"]
    assert result["task_status"] == "UNKNOWN"
    assert result["action_status"] == "NEEDS_REVIEW"
    assert result["recommended_actions"] == []
    assert result["questions"]


@pytest.mark.parametrize(
    ("program", "expected"),
    [
        (PROGRAM, "APPLIES"),
        ("GSoC", "NEEDS_CONFIRMATION"),
        ("applying to example summer of code", "NEEDS_CONFIRMATION"),
        (None, "NEEDS_CONFIRMATION"),
    ],
)
def test_p321_06_program_exact_and_alias(tmp_path, program, expected):
    snaps = write_pair(tmp_path, OLD_MIN, NEW_MIN)
    change = find_change(snaps, "Always disclose")
    result = assess_policy_clause(
        change,
        *snaps,
        PolicyContext.from_dict(context(program=program, code=True)),
    )
    assert result["applicability_status"] == expected
    if expected != "APPLIES":
        assert result["recommended_actions"] == []
    if program == "GSoC":
        assert any(
            PROGRAM in question and "GSoC" in question
            for question in result["questions"]
        )
    if program is None:
        assert "program" in result["missing_information"]


# ---------------------------------------------------------------------------
# P321-07: clause vs whole section
# ---------------------------------------------------------------------------

def test_p321_07_clause_vs_section(tmp_path):
    snaps = write_pair(tmp_path, OLD_MIN, NEW_FULL)
    change = find_change(snaps, "Always disclose")
    result = assess_policy_clause(
        change, *snaps, PolicyContext.from_dict(context(code=False, comments=False))
    )
    assert result["applicability_status"] == "DOES_NOT_APPLY"
    assert result["task_status"] == "NOT_APPLICABLE"
    assert result["action_status"] == "NO_CURRENT_ACTION"
    assert result["recommended_actions"] == []

    summary = result["section_summary"]
    assert summary["applicability_status"] == "INSUFFICIENT_CONTEXT"
    assert summary["action_status"] == "NEEDS_REVIEW"
    unresolved = text_of_unresolved(summary)
    assert "Participants should not make use" in unresolved
    assert "Be ready to explain" in unresolved
    assert "Note that some projects may reject" in unresolved
    assert "Some projects may have additional policies" in unresolved
    assert summary["action_status"] != "NO_CURRENT_ACTION"


# ---------------------------------------------------------------------------
# P321-08 .. P321-09: evidence and scope tampering
# ---------------------------------------------------------------------------

def test_p321_08_clause_evidence_missing_or_tampered(tmp_path):
    snaps = write_pair(tmp_path, OLD_MIN, NEW_MIN)
    good = find_change(snaps, "Always disclose")
    variants = [
        replace(good, new_evidence=None),
        replace(good, new_evidence=replace(good.new_evidence, quote="伪造内容")),
        replace(good, new_evidence=replace(good.new_evidence, byte_start=good.new_evidence.byte_start + 1)),
        replace(good, score=good.score + 0.5),
    ]
    for change in variants:
        result = assess_policy_clause(
            change, *snaps, PolicyContext.from_dict(context())
        )
        assert result["evidence_status"] == "UNVERIFIED"
        assert result["applicability_status"] == "INSUFFICIENT_CONTEXT"
        assert result["action_status"] == "UNVERIFIED"
        assert result["recommended_actions"] == []
        assert result["local_validation_status"] != "VERIFIED"


def test_p321_09_scope_or_scope_id_tampered(tmp_path):
    snaps = write_pair(tmp_path, OLD_MIN, NEW_MIN)
    section = find_policy_sections(snaps[1])[0]
    tampered = replace(
        section,
        heading_evidence=replace(section.heading_evidence, quote="伪造标题"),
    )
    result = assess_policy_section(
        tampered, *snaps, PolicyContext.from_dict(context())
    )
    assert result["local_validation_status"] == "NOT_VERIFIED"
    assert result["local_validation_reason"] in {"EVIDENCE_INVALID", "SCOPE_ID_MISMATCH"}
    assert result["evidence_status"] == "UNVERIFIED"
    assert result["applicability_status"] == "INSUFFICIENT_CONTEXT"
    assert result["action_status"] == "NEEDS_REVIEW"
    assert result["recommended_actions"] == []

    forged = analyze(*snaps).changes[0]
    result = assess_policy_clause(
        forged,
        *snaps,
        PolicyContext.from_dict(context()),
        scope_id="SC-" + "0" * 24,
    )
    assert result["local_validation_status"] == "NOT_VERIFIED"
    assert result["local_validation_reason"] == "SCOPE_ID_MISMATCH"
    assert result["evidence_status"] == "UNVERIFIED"
    assert result["recommended_actions"] == []


# ---------------------------------------------------------------------------
# P321-10: duplicate obligation across sections
# ---------------------------------------------------------------------------

OLD_TWO = (
    "# Student Guide\n\n"
    "## Applying to Example Summer of Code\n\n"
    "Background text.\n\n"
    "## Another Program\n\n"
    "Background text.\n\n"
    "### AI Policies\n\n"
    "Participants should follow these guidelines:\n\n"
    "1. Always disclose if AI was used in the code.\n"
)
NEW_TWO = (
    "# Student Guide\n\n"
    "## Applying to Example Summer of Code\n\n"
    "Background text.\n\n"
    "### AI Policies\n\n"
    "Participants should follow these guidelines:\n\n"
    "1. Always disclose if AI was used in the code.\n\n"
    "## Another Program\n\n"
    "Background text.\n\n"
    "### AI Policies\n\n"
    "Participants should follow these guidelines:\n\n"
    "1. Always disclose if AI was used in the code.\n"
)


def test_p321_10_duplicate_across_sections(tmp_path):
    snaps = write_pair(tmp_path, OLD_TWO, NEW_TWO)
    sections = find_policy_sections(snaps[1])
    assert len(sections) == 2
    change = find_change(snaps, "Always disclose", added_only=True)
    ctx = PolicyContext.from_dict(context(program=PROGRAM, code=True))

    ambiguous = assess_policy_clause(change, *snaps, ctx)
    assert ambiguous["applicability_status"] == "INSUFFICIENT_CONTEXT"
    assert ambiguous["action_status"] == "NEEDS_REVIEW"
    assert ambiguous["recommended_actions"] == []
    assert any(
        entry["scope_id"] == sections[0].scope_id
        for entry in ambiguous["section_summary"]["duplicate_group"]
    )
    assert any(
        entry["scope_id"] == sections[1].scope_id
        for entry in ambiguous["section_summary"]["duplicate_group"]
    )

    first = assess_policy_section(sections[0].scope_id, *snaps, ctx)
    assert first["section_summary"]["applicability_status"] == "APPLIES"
    assert first["section_summary"]["action_status"] == "ACTION_REVIEW_REQUIRED"
    assert len(first["section_summary"]["duplicate_group"]) == 2

    second = assess_policy_section(sections[1].scope_id, *snaps, ctx)
    assert second["section_summary"]["applicability_status"] == "NEEDS_CONFIRMATION"
    assert second["section_summary"]["action_status"] == "NEEDS_REVIEW"
    assert len(second["section_summary"]["duplicate_group"]) == 2
    assert second["recommended_actions"] == []


# ---------------------------------------------------------------------------
# P321-11: negation semantics
# ---------------------------------------------------------------------------

NEW_NOT_REQUIRED = OLD_MIN + (
    "\n### AI Policies\n\n"
    "Participants should follow these guidelines:\n\n"
    "1. AI disclosure is not required.\n"
)


def test_p321_11_negation_semantics(tmp_path):
    snaps = write_pair(tmp_path, OLD_MIN, NEW_MIN)
    comments_change = find_change(snaps, "Do not use AI generated comments")

    applies = assess_policy_clause(
        comments_change, *snaps, PolicyContext.from_dict(context(comments=True))
    )
    assert applies["applicability_status"] == "APPLIES"
    assert applies["policy_rule"]["kind"] == "PROHIBITION"
    assert applies["policy_rule"]["trigger"]["value"] is True
    assert applies["policy_rule"]["trigger"]["operator"] == "EQ"

    not_applies = assess_policy_clause(
        comments_change, *snaps, PolicyContext.from_dict(context(comments=False))
    )
    assert not_applies["applicability_status"] == "DOES_NOT_APPLY"
    assert not_applies["action_status"] == "NO_CURRENT_ACTION"

    # Use a separate directory because write_pair writes old.md/new.md.
    unsupported_dir = tmp_path / "unsupported"
    snaps2 = write_pair(unsupported_dir, OLD_MIN, NEW_NOT_REQUIRED)
    unsupported_change = find_change(snaps2, "AI disclosure is not required")
    unsupported = assess_policy_clause(
        unsupported_change, *snaps2, PolicyContext.from_dict(context())
    )
    assert unsupported["applicability_status"] == "INSUFFICIENT_CONTEXT"
    assert unsupported["recommended_actions"] == []
    assert "AI disclosure is not required" in text_of_unresolved(
        unsupported["section_summary"]
    )

    missing = assess_policy_clause(
        comments_change, *snaps, PolicyContext.from_dict(context(comments=None))
    )
    assert missing["applicability_status"] == "NEEDS_CONFIRMATION"
    assert "condition:uses_ai_for_comments" in missing["missing_information"]


# ---------------------------------------------------------------------------
# P321-12 .. P321-14: upstream, completed disclosure, determinism
# ---------------------------------------------------------------------------

def test_p321_12_upstream_needs_review_preserved(tmp_path):
    snaps = write_pair(tmp_path, OLD_MIN, NEW_MIN)
    change = find_change(snaps, "Always disclose")
    result = assess_policy_clause(
        change, *snaps, PolicyContext.from_dict(context())
    )
    assert result["upstream_material_status"] == "UNKNOWN"
    assert result["upstream_review_status"] == "NEEDS_REVIEW"
    assert result["local_validation"] == "LOCAL_SECTION_ADDITION"
    assert result["local_validation_status"] == "VERIFIED"
    assert result["evidence_status"] == "VERIFIED"
    assert result["recommended_actions"][0]["kind"] == "HUMAN_REVIEW_ONLY"
    assert any("NEEDS_REVIEW" in item for item in result["uncertainty"])


def test_p321_13_completed_and_progress_separation(tmp_path):
    snaps = write_pair(tmp_path, OLD_MIN, NEW_MIN)
    change = find_change(snaps, "Always disclose")

    completed = assess_policy_clause(
        change,
        *snaps,
        PolicyContext.from_dict(
            context(completed=["submit:ai_code_disclosure"])
        ),
    )
    assert completed["applicability_status"] == "APPLIES"
    assert completed["task_status"] == "COMPLETED"
    assert completed["action_status"] == "ACTION_REVIEW_REQUIRED"
    assert completed["recommended_actions"][0]["progress_status"] == "COMPLETED_REVIEW"
    message = completed["recommended_actions"][0]["message"]
    assert "尚未完成" not in message
    assert "必须重新提交" not in message

    pending = assess_policy_clause(
        change,
        *snaps,
        PolicyContext.from_dict(context(pending=["submit:ai_code_disclosure"])),
    )
    assert pending["task_status"] == "PENDING"
    assert pending["recommended_actions"][0]["progress_status"] == "PENDING_REVIEW"

    generic = assess_policy_clause(
        change,
        *snaps,
        PolicyContext.from_dict(
            context(extra_facts=[{"field": "progress", "value": "completed"}])
        ),
    )
    assert generic["task_status"] == "UNKNOWN"
    assert generic["recommended_actions"][0]["progress_status"] == "ASK_PROGRESS"

    conflict = assess_policy_clause(
        change,
        *snaps,
        PolicyContext.from_dict(
            context(
                completed=["submit:ai_code_disclosure"],
                pending=["submit:ai_code_disclosure"],
            )
        ),
    )
    assert conflict["applicability_status"] == "NEEDS_CONFIRMATION"
    assert conflict["recommended_actions"] == []


def test_p321_14_repeatable_and_read_only(tmp_path):
    snaps = write_pair(tmp_path, OLD_MIN, NEW_MIN)
    old_before = (tmp_path / "old.md").read_bytes()
    new_before = (tmp_path / "new.md").read_bytes()
    change = find_change(snaps, "Always disclose")
    ctx = PolicyContext.from_dict(context())
    first = assess_policy_clause(change, *snaps, ctx)
    second = assess_policy_clause(change, *snaps, ctx)
    assert json.dumps(first, sort_keys=True, ensure_ascii=False) == json.dumps(
        second, sort_keys=True, ensure_ascii=False
    )
    assert first["clause_id"] == second["clause_id"]
    assert first["scope_id"] == second["scope_id"]
    assert (tmp_path / "old.md").read_bytes() == old_before
    assert (tmp_path / "new.md").read_bytes() == new_before


# ---------------------------------------------------------------------------
# P321-15: strict LOCAL_SECTION_ADDITION
# ---------------------------------------------------------------------------

def test_p321_15_local_section_addition_strictness(tmp_path):
    # 15a: an edit outside the policy section
    old = OLD_MIN
    new_extra = NEW_MIN.replace(
        "Background text with no obligations.",
        "Background text with one edit.",
    )
    snaps = write_pair(tmp_path / "a", old, new_extra)
    section = find_policy_sections(snaps[1])[0]
    local = validate_local_section_addition(section, *snaps)
    assert local["status"] == "NOT_VERIFIED"
    assert local["reason"] == "REMAINDER_CHANGED"

    # 15b: duplicate AI Policies sections
    duplicate_new = OLD_MIN + (
        "\n### AI Policies\n\nParticipants should follow these guidelines:\n\n"
        "1. Always disclose if AI was used in the code.\n\n"
        "### AI Policies\n\nParticipants should follow these guidelines:\n\n"
        "1. Always disclose if AI was used in the code.\n"
    )
    snaps = write_pair(tmp_path / "b", OLD_MIN, duplicate_new)
    sections = find_policy_sections(snaps[1])
    assert len(sections) == 2
    local = validate_local_section_addition(sections[0], *snaps)
    assert local["status"] == "NOT_VERIFIED"
    assert local["reason"] == "DUPLICATE_SECTION"

    # 15c: old already contains the section
    snaps = write_pair(tmp_path / "c", NEW_MIN, NEW_MIN)
    section = find_policy_sections(snaps[1])[0]
    local = validate_local_section_addition(section, *snaps)
    assert local["status"] == "NOT_VERIFIED"
    assert local["reason"] == "OLD_CONTAINS_SECTION"

    # 15d: section moved from the end to the top
    old_moved = OLD_MIN + (
        "\n### AI Policies\n\nParticipants should follow these guidelines:\n\n"
        "1. Always disclose if AI was used in the code.\n"
    )
    new_moved = (
        "# Student Guide\n\n"
        "## Applying to Example Summer of Code\n\n"
        "### AI Policies\n\n"
        "Participants should follow these guidelines:\n\n"
        "1. Always disclose if AI was used in the code.\n\n"
        "Background text with no obligations.\n"
    )
    snaps = write_pair(tmp_path / "d", old_moved, new_moved)
    section = find_policy_sections(snaps[1])[0]
    local = validate_local_section_addition(section, *snaps)
    assert local["status"] == "NOT_VERIFIED"
    assert local["reason"] == "REMAINDER_CHANGED"

    # 15e: CRLF + BOM, only the policy section appended
    old_text = (
        "﻿# Student Guide\r\n\r\n"
        "## Applying to Example Summer of Code\r\n\r\n"
        "Background text.\r\n"
    )
    new_text = old_text + (
        "\r\n### AI Policies\r\n\r\n"
        "Participants should follow these guidelines:\r\n\r\n"
        "1. Always disclose if AI was used in the code.\r\n"
    )
    snaps = write_pair_bytes(
        tmp_path / "e", old_text.encode("utf-8"), new_text.encode("utf-8")
    )
    section = find_policy_sections(snaps[1])[0]
    local = validate_local_section_addition(section, *snaps)
    assert local["status"] == "VERIFIED"
    assert snaps[1].content.startswith("﻿")
    assert "\r\n" in snaps[1].content
    assert section.heading_evidence.quote == "### AI Policies"
    assert section.heading_evidence.line_start == 7


# ---------------------------------------------------------------------------
# P321-16 .. P321-20
# ---------------------------------------------------------------------------

def test_p321_16_duplicate_quote_not_guessed(tmp_path):
    new_dup = OLD_MIN + (
        "\n### AI Policies\n\nParticipants should follow these guidelines:\n\n"
        "1. Always disclose if AI was used in the code.\n"
        "2. Always disclose if AI was used in the code.\n"
    )
    snaps = write_pair(tmp_path, OLD_MIN, new_dup)
    change = find_change(snaps, "Always disclose")
    result = assess_policy_clause(
        change, *snaps, PolicyContext.from_dict(context())
    )
    assert result["applicability_status"] == "INSUFFICIENT_CONTEXT"
    assert result["recommended_actions"] == []
    assert result["section_summary"]["action_status"] == "NEEDS_REVIEW"


def test_p321_17_task_status_separation(tmp_path):
    snaps = write_pair(tmp_path, OLD_MIN, NEW_MIN)
    change = find_change(snaps, "Always disclose")
    cases = [
        (context(), "UNKNOWN", "ASK_PROGRESS"),
        (context(pending=["submit:ai_code_disclosure"]), "PENDING", "PENDING_REVIEW"),
        (context(completed=["submit:ai_code_disclosure"]), "COMPLETED", "COMPLETED_REVIEW"),
    ]
    for ctx_json, expected_task, expected_progress in cases:
        result = assess_policy_clause(
            change, *snaps, PolicyContext.from_dict(ctx_json)
        )
        assert result["applicability_status"] == "APPLIES"
        assert result["task_status"] == expected_task
        assert result["action_status"] == "ACTION_REVIEW_REQUIRED"
        assert result["recommended_actions"][0]["progress_status"] == expected_progress
        assert result["recommended_actions"][0]["task_id"] == "submit:ai_code_disclosure"


def test_p321_18_no_hardcoding_and_independent_variant(tmp_path):
    old_alt = (
        "# Handbook\n\n"
        "## Applying to Another Program\n\n"
        "Background.\n"
    )
    new_alt = old_alt + (
        "\n### AI Policies\n\nParticipants should follow these guidelines:\n\n"
        "1. Always disclose if AI was used in the code.\n"
    )
    snaps = write_pair(tmp_path / "alt", old_alt, new_alt)
    change = find_change(snaps, "Always disclose")
    result = assess_policy_clause(
        change,
        *snaps,
        PolicyContext.from_dict(context(program="Applying to Another Program")),
    )
    assert result["applicability_status"] == "APPLIES"
    assert result["recommended_actions"][0]["task_id"] == "submit:ai_code_disclosure"

    new_unsupported_heading = old_alt + (
        "\n### AI Usage\n\nParticipants should follow these guidelines:\n\n"
        "1. Always disclose if AI was used in the code.\n"
    )
    snaps = write_pair(tmp_path / "heading", old_alt, new_unsupported_heading)
    change = find_change(snaps, "Always disclose")
    result = assess_policy_clause(
        change,
        *snaps,
        PolicyContext.from_dict(context(program="Applying to Another Program")),
    )
    assert result["applicability_status"] == "INSUFFICIENT_CONTEXT"
    assert result["recommended_actions"] == []

    new_unsupported_rule = old_alt + (
        "\n### AI Policies\n\nParticipants should follow these guidelines:\n\n"
        "1. Must use AI responsibly.\n"
    )
    snaps = write_pair(tmp_path / "rule", old_alt, new_unsupported_rule)
    change = find_change(snaps, "Must use AI responsibly")
    result = assess_policy_clause(
        change,
        *snaps,
        PolicyContext.from_dict(context(program="Applying to Another Program")),
    )
    assert result["applicability_status"] == "INSUFFICIENT_CONTEXT"
    assert result["recommended_actions"] == []

    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (Path(__file__).resolve().parents[1] / "src/requirementdelta").glob("policy_*.py")
    )
    for forbidden in ("PERSONA-T02", "PERSONA-T03", "PERSONA-T04"):
        assert forbidden not in source


def test_p321_19_program_and_role_missing(tmp_path):
    snaps = write_pair(tmp_path / "min", OLD_MIN, NEW_MIN)
    change = find_change(snaps, "Always disclose")

    result = assess_policy_clause(
        change,
        *snaps,
        PolicyContext.from_dict(context(program=None, code=True)),
    )
    assert result["applicability_status"] == "NEEDS_CONFIRMATION"
    assert "program" in result["missing_information"]
    assert result["recommended_actions"] == []

    result = assess_policy_clause(
        change,
        *snaps,
        PolicyContext.from_dict(context(participating=None, code=True)),
    )
    assert result["applicability_status"] == "NEEDS_CONFIRMATION"
    assert "participating" in result["missing_information"]
    assert result["recommended_actions"] == []

    snaps = write_pair(tmp_path / "applicants", OLD_MIN, NEW_APPLICANTS)
    change = find_change(snaps, "Always disclose")
    result = assess_policy_clause(
        change,
        *snaps,
        PolicyContext.from_dict(context(role=None, code=True)),
    )
    assert result["applicability_status"] == "NEEDS_CONFIRMATION"
    assert "role" in result["missing_information"]

    result = assess_policy_clause(
        change,
        *snaps,
        PolicyContext.from_dict(context(role="mentor", code=True)),
    )
    assert result["applicability_status"] == "DOES_NOT_APPLY"
    assert result["task_status"] == "NOT_APPLICABLE"
    assert result["action_status"] == "NO_CURRENT_ACTION"
    assert result["recommended_actions"] == []

    result = assess_policy_clause(
        change,
        *snaps,
        PolicyContext.from_dict(context(role="applicant", code=True)),
    )
    assert result["applicability_status"] == "APPLIES"
    assert result["recommended_actions"][0]["task_id"] == "submit:ai_code_disclosure"


def test_p321_20_unreadable_snapshots(tmp_path):
    ctx = PolicyContext.from_dict(context())

    missing_old = read_pair("missing.md", "new.md", tmp_path)
    (tmp_path / "new.md").write_bytes(NEW_MIN.encode("utf-8"))
    result = assess_policy_clause(None, *missing_old, ctx)
    assert result["evidence_status"] == "UNVERIFIED"
    assert result["applicability_status"] == "INSUFFICIENT_CONTEXT"
    assert result["action_status"] == "UNVERIFIED"
    assert result["local_validation_status"] == "NOT_ATTEMPTED"
    assert result["recommended_actions"] == []

    (tmp_path / "old.md").write_bytes(OLD_MIN.encode("utf-8"))
    (tmp_path / "new.md").write_bytes(b"\xff\xfe invalid")
    bad_new = read_pair("old.md", "new.md", tmp_path)
    result = assess_policy_clause(None, *bad_new, ctx)
    assert result["evidence_status"] == "UNVERIFIED"
    assert result["action_status"] == "UNVERIFIED"
    assert result["recommended_actions"] == []

    (tmp_path / "old.md").unlink()
    (tmp_path / "old.md").mkdir()
    (tmp_path / "new.md").write_bytes(NEW_MIN.encode("utf-8"))
    directory_old = read_pair("old.md", "new.md", tmp_path)
    result = assess_policy_clause(None, *directory_old, ctx)
    assert result["evidence_status"] == "UNVERIFIED"
    assert result["action_status"] == "UNVERIFIED"
    assert result["recommended_actions"] == []
