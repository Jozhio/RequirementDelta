"""P0-3.2 independent variants, counterexamples and boundary checks."""
from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path

import pytest
from test_p0_3_2_acceptance import (
    MISSING,
    NEW_MIN,
    OLD_MIN,
    context,
    find_change,
    write_pair,
)

from requirementdelta.applicability import assess as assess_03
from requirementdelta.changes import analyze
from requirementdelta.conditions import Condition
from requirementdelta.ingest import read_pair
from requirementdelta.policy_applicability import (
    assess_policy_clause,
    assess_policy_rule,
)
from requirementdelta.policy_context import PolicyContext
from requirementdelta.policy_rules import evaluate_trigger, parse_policy_rule
from requirementdelta.policy_scope import find_policy_sections, validate_local_section_addition
from requirementdelta.task_context import UserTaskContext


def rule_for(section, needle: str):
    return next(
        clause.rule
        for clause in section.clauses
        if clause.rule is not None and needle in clause.evidence.quote
    )


def test_policy_context_rejects_unknown_keys_and_bad_types():
    bad = context()
    bad["unexpected"] = 1
    with pytest.raises(ValueError):
        PolicyContext.from_dict(bad)
    with pytest.raises(ValueError):
        PolicyContext.from_dict(context(program="  padded  "))
    with pytest.raises(ValueError):
        PolicyContext.from_dict(
            context(extra_facts=[{"field": "condition:uses_ai_for_code", "value": "true"}])
        )


def test_conflicting_role_assertions_block_certainty(tmp_path):
    snaps = write_pair(tmp_path, OLD_MIN, NEW_MIN)
    change = find_change(snaps, "Always disclose")
    ctx = PolicyContext.from_dict(
        context(role="participant", extra_facts=[{"field": "role", "value": "mentor"}])
    )
    result = assess_policy_clause(change, *snaps, ctx)
    assert result["applicability_status"] == "NEEDS_CONFIRMATION"
    assert any("conflict:role" in item for item in result["missing_information"])
    assert result["recommended_actions"] == []


def test_and_or_not_truth_table_and_unknown_propagation():
    ctx = PolicyContext.from_dict(context(code=True, comments=False))

    def eq(field, value):
        return Condition("EQ", field, value)

    def truth(node):
        return evaluate_trigger(node, ctx)[0]

    assert truth(Condition("AND", children=(eq("condition:uses_ai_for_code", True), eq("participating", True)))) is True
    assert truth(Condition("AND", children=(eq("condition:uses_ai_for_code", False), eq("condition:missing", True)))) is False
    assert truth(Condition("OR", children=(eq("condition:uses_ai_for_code", True), eq("condition:missing", True)))) is True
    assert truth(Condition("NOT", children=(eq("condition:uses_ai_for_code", False),))) is True
    unknown = truth(Condition("NOT", children=(eq("condition:missing", True),)))
    assert unknown is None
    _, _, missing = evaluate_trigger(Condition("NOT", children=(eq("condition:missing", True),)), ctx)
    assert "condition:missing" in missing


def test_compound_trigger_end_to_end(tmp_path):
    snaps = write_pair(tmp_path, OLD_MIN, NEW_MIN)
    section = find_policy_sections(snaps[1])[0]
    rule = rule_for(section, "Always disclose")
    ctx = PolicyContext.from_dict(context(code=True, comments=False))

    and_rule = replace(
        rule,
        trigger=Condition(
            "AND",
            children=(
                Condition("EQ", "condition:uses_ai_for_code", True),
                Condition("EQ", "participating", True),
            ),
        ),
    )
    result = assess_policy_rule(and_rule, section, *snaps, ctx)
    assert result["applicability_status"] == "APPLIES"
    assert result["task_status"] == "UNKNOWN"
    assert result["recommended_actions"][0]["task_id"] == "submit:ai_code_disclosure"

    or_rule = replace(
        rule,
        trigger=Condition(
            "OR",
            children=(
                Condition("EQ", "condition:uses_ai_for_code", True),
                Condition("EQ", "condition:uses_ai_for_comments", True),
            ),
        ),
    )
    ctx_false_code = PolicyContext.from_dict(context(code=False, comments=True))
    result = assess_policy_rule(or_rule, section, *snaps, ctx_false_code)
    assert result["applicability_status"] == "APPLIES"


def test_assess_policy_rule_rejects_unsupported_or_forged_metadata(tmp_path):
    snaps = write_pair(tmp_path, OLD_MIN, NEW_MIN)
    section = find_policy_sections(snaps[1])[0]
    rule = rule_for(section, "Always disclose")
    ctx = PolicyContext.from_dict(context())
    for forged in [
        replace(rule, requirement_text="伪造义务"),
        replace(rule, task_id="submit:other"),
        replace(rule, trigger=Condition("EQ", "participating", True)),
    ]:
        with pytest.raises(ValueError):
            assess_policy_rule(forged, section, *snaps, ctx)


def test_compound_trigger_unknown_never_actions(tmp_path):
    snaps = write_pair(tmp_path, OLD_MIN, NEW_MIN)
    section = find_policy_sections(snaps[1])[0]
    rule = rule_for(section, "Always disclose")
    not_rule = replace(
        rule,
        trigger=Condition(
            "NOT",
            children=(Condition("EQ", "condition:uses_ai_for_code", True),),
        ),
    )
    ctx = PolicyContext.from_dict(context(code=MISSING))
    result = assess_policy_rule(not_rule, section, *snaps, ctx)
    assert result["applicability_status"] == "NEEDS_CONFIRMATION"
    assert result["action_status"] == "NEEDS_REVIEW"
    assert result["recommended_actions"] == []


def test_rule_parser_rejects_paraphrases(tmp_path):
    snaps = write_pair(tmp_path, OLD_MIN, NEW_MIN)
    section = find_policy_sections(snaps[1])[0]
    evidence = section.heading_evidence
    assert parse_policy_rule("Must disclose AI use.", evidence) is None
    assert parse_policy_rule("Always disclose if AI was used in the code.", evidence) is not None


def test_policy_section_without_declaration_abstains(tmp_path):
    new = OLD_MIN + (
        "\n### AI Policies\n\n"
        "1. Always disclose if AI was used in the code.\n"
    )
    snaps = write_pair(tmp_path, OLD_MIN, new)
    assert find_policy_sections(snaps[1]) == ()
    change = find_change(snaps, "Always disclose")
    result = assess_policy_clause(
        change, *snaps, PolicyContext.from_dict(context())
    )
    assert result["applicability_status"] == "INSUFFICIENT_CONTEXT"
    assert result["local_validation_status"] == "NOT_ATTEMPTED"
    assert result["recommended_actions"] == []


def test_ids_are_stable_and_do_not_embed_persona_or_paths(tmp_path):
    snaps = write_pair(tmp_path, OLD_MIN, NEW_MIN)
    section = find_policy_sections(snaps[1])[0]
    rule = rule_for(section, "Always disclose")
    assert re.fullmatch(r"SC-[0-9a-f]{24}", section.scope_id)
    assert re.fullmatch(r"CL-[0-9a-f]{24}", rule.clause_id)
    assert section.scope_id == find_policy_sections(snaps[1])[0].scope_id
    assert rule.clause_id == rule_for(find_policy_sections(snaps[1])[0], "Always disclose").clause_id
    blob = section.scope_id + rule.clause_id
    for forbidden in ("PERSONA-", "T02", "T03", "T04", str(tmp_path)):
        assert forbidden not in blob


def test_local_validation_is_read_only(tmp_path):
    snaps = write_pair(tmp_path, OLD_MIN, NEW_MIN)
    before = {
        "old": (tmp_path / "old.md").read_bytes(),
        "new": (tmp_path / "new.md").read_bytes(),
    }
    section = find_policy_sections(snaps[1])[0]
    local = validate_local_section_addition(section, *snaps)
    assert local["status"] == "VERIFIED"
    assert (tmp_path / "old.md").read_bytes() == before["old"]
    assert (tmp_path / "new.md").read_bytes() == before["new"]


def test_03_api_still_works(tmp_path):
    old = "项目“星辰”的参与者必须提交PDF。"
    new = "项目“星辰”的参与者必须提交ZIP。"
    (tmp_path / "old.md").write_bytes(old.encode("utf-8"))
    (tmp_path / "new.md").write_bytes(new.encode("utf-8"))
    snaps = read_pair("old.md", "new.md", tmp_path)
    ctx = UserTaskContext.from_dict(
        {
            "schema_version": "0.3",
            "confirmed_by_user": True,
            "facts": [
                {"field": "project", "value": "星辰"},
                {"field": "participating", "value": True},
            ],
            "completed_tasks": [],
            "pending_tasks": [],
        }
    )
    results = assess_03(*snaps, ctx)
    assert len(results) == 1
    assert results[0]["applicability_status"] == "APPLIES"
    assert results[0]["action_status"] == "ACTION_REVIEW_REQUIRED"


def test_uncertain_results_never_have_actions(tmp_path):
    snaps = write_pair(tmp_path, OLD_MIN, NEW_MIN)
    change = find_change(snaps, "Always disclose")
    cases = [
        context(code=MISSING),
        context(program="GSoC"),
        context(participating=None),
        context(program=None),
    ]
    for ctx_json in cases:
        result = assess_policy_clause(
            change, *snaps, PolicyContext.from_dict(ctx_json)
        )
        assert result["applicability_status"] in {
            "NEEDS_CONFIRMATION",
            "INSUFFICIENT_CONTEXT",
        }
        assert result["recommended_actions"] == []
        assert result["action_status"] in {"NEEDS_REVIEW", "UNVERIFIED"}
        assert json.loads(json.dumps(result, ensure_ascii=False)) == result
