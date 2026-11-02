"""P0-3.2 clause-level policy applicability (schema 0.4, additive).

Only a locally verified added policy section can produce a bounded, clause-level
conclusion. Upstream P0-2 statuses are preserved. Uncertain or unsupported
inputs never produce recommended actions.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict

from .changes import Change, analyze
from .evidence import verify_evidence
from .ingest import DocumentSnapshot
from .policy_context import PolicyContext
from .policy_rules import (
    SUPPORTED_RULES,
    PolicyRule,
    evaluate_trigger,
    trigger_dict,
)
from .policy_scope import (
    PolicyClause,
    PolicySection,
    find_policy_sections,
    validate_local_section_addition,
)
from .segment import match_text

STATUS_APPLIES = "APPLIES"
STATUS_NOT_APPLIES = "DOES_NOT_APPLY"
STATUS_NEEDS_CONFIRMATION = "NEEDS_CONFIRMATION"
STATUS_INSUFFICIENT = "INSUFFICIENT_CONTEXT"

TASK_COMPLETED = "COMPLETED"
TASK_PENDING = "PENDING"
TASK_UNKNOWN = "UNKNOWN"
TASK_NOT_APPLICABLE = "NOT_APPLICABLE"

ACTION_REVIEW = "ACTION_REVIEW_REQUIRED"
ACTION_NONE = "NO_CURRENT_ACTION"
ACTION_NEEDS_REVIEW = "NEEDS_REVIEW"
ACTION_UNVERIFIED = "UNVERIFIED"


def _json_native(value):
    return json.loads(json.dumps(value, ensure_ascii=False))


def _change_id(change: Change | None, old: DocumentSnapshot, new: DocumentSnapshot) -> str | None:
    if change is None:
        return None
    absent = (
        "No aligned old clause; old snapshot hash records the compared version. "
        "No global novelty claim."
        if change.relation == "ADDED"
        else None
    )
    refs = {
        "old": asdict(change.old_evidence) if change.old_evidence else None,
        "new": asdict(change.new_evidence) if change.new_evidence else None,
        "old_snapshot_sha256": old.sha256,
        "new_snapshot_sha256": new.sha256,
        "scope": [],
        "absent_side_reason": absent,
    }
    payload = json.dumps(refs, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return "C-" + hashlib.sha256(payload).hexdigest()[:24]


def _evidence_refs(
    change: Change | None,
    old: DocumentSnapshot,
    new: DocumentSnapshot,
    section: PolicySection | None,
    clause_evidence=None,
) -> dict:
    old_ref = asdict(change.old_evidence) if change and change.old_evidence else None
    new_ref = asdict(change.new_evidence) if change and change.new_evidence else None
    if new_ref is None and clause_evidence is not None:
        new_ref = asdict(clause_evidence)
    scope = []
    if section is not None:
        scope = [asdict(section.heading_evidence), asdict(section.declaration_evidence)]
    return {
        "old": old_ref,
        "new": new_ref,
        "scope": scope,
        "old_snapshot_sha256": old.sha256,
        "new_snapshot_sha256": new.sha256,
        "absent_side_reason": (
            "No aligned old clause; old snapshot hash records the compared version. "
            "No global novelty claim."
            if change is not None and change.relation == "ADDED"
            else None
        ),
    }


def _base_result(
    assessment_unit: str,
    change: Change | None,
    old: DocumentSnapshot,
    new: DocumentSnapshot,
    section: PolicySection | None = None,
    clause_evidence=None,
) -> dict:
    return {
        "schema_version": "0.4",
        "assessment_unit": assessment_unit,
        "scope_id": section.scope_id if section else None,
        "clause_id": None,
        "change_id": _change_id(change, old, new),
        "policy_rule": None,
        "upstream_material_status": change.material_status if change else "UNKNOWN",
        "upstream_review_status": change.review_status if change else "UNVERIFIED",
        "local_validation": None,
        "local_validation_status": "NOT_ATTEMPTED",
        "local_validation_reason": None,
        "evidence_status": "UNVERIFIED",
        "applicability_status": STATUS_INSUFFICIENT,
        "task_status": TASK_UNKNOWN,
        "action_status": ACTION_NEEDS_REVIEW,
        "matched_conditions": [],
        "excluded_conditions": [],
        "missing_information": [],
        "reasoning": [],
        "questions": [],
        "uncertainty": [],
        "evidence_refs": _evidence_refs(change, old, new, section, clause_evidence),
        "recommended_actions": [],
        "confidence": "UNDETERMINED",
        "section_summary": None,
    }


def _apply_local(result: dict, local: dict | None) -> None:
    if local is None:
        result["local_validation"] = None
        result["local_validation_status"] = "NOT_ATTEMPTED"
        result["local_validation_reason"] = None
        result["evidence_status"] = "UNVERIFIED"
        return
    if local["status"] == "VERIFIED":
        result["local_validation"] = "LOCAL_SECTION_ADDITION"
        result["local_validation_status"] = "VERIFIED"
        result["local_validation_reason"] = None
        result["evidence_status"] = "VERIFIED"
        return
    result["local_validation"] = "LOCAL_SECTION_ADDITION"
    result["local_validation_status"] = "NOT_VERIFIED"
    result["local_validation_reason"] = local.get("reason")
    result["evidence_status"] = local.get("evidence_status", "UNVERIFIED")


def _uncertain(
    result: dict,
    reason: str,
    missing=(),
    *,
    unverified: bool = False,
    question: str | None = None,
) -> dict:
    result["applicability_status"] = (
        STATUS_NEEDS_CONFIRMATION if missing else STATUS_INSUFFICIENT
    )
    result["action_status"] = ACTION_UNVERIFIED if unverified else ACTION_NEEDS_REVIEW
    result["missing_information"] = sorted(set(missing))
    result["reasoning"].append(reason)
    result["uncertainty"].append(reason)
    result["recommended_actions"] = []
    result["confidence"] = "UNDETERMINED"
    if unverified:
        result["evidence_status"] = "UNVERIFIED"
    if question:
        result["questions"].append(question)
    elif result["missing_information"]:
        result["questions"] = [
            "请确认：" + key for key in result["missing_information"]
        ]
    else:
        result["questions"] = ["请提供可核验的原文范围或用户上下文。"]
    return result


def _does_not_apply(result: dict, reason: str, trace=()) -> dict:
    result["applicability_status"] = STATUS_NOT_APPLIES
    result["task_status"] = TASK_NOT_APPLICABLE
    result["action_status"] = ACTION_NONE
    result["matched_conditions"] = [x for x in trace if x.get("result") is True]
    result["excluded_conditions"] = [x for x in trace if x.get("result") is False]
    result["reasoning"].append(reason)
    result["recommended_actions"] = []
    result["confidence"] = "DETERMINISTIC_WITHIN_SUPPORTED_RULE"
    result["uncertainty"] = [
        "Clause-local assessment only; no overall eligibility, compliance or action execution conclusion."
    ]
    return result


def _program_state(context: PolicyContext, section: PolicySection) -> dict:
    if context.program is None:
        return {
            "ok": None,
            "missing": ["program"],
            "question": "请确认：该政策节所属的精确 program 名称。",
        }
    if context.program != section.program_text:
        return {
            "ok": None,
            "missing": ["program"],
            "question": (
                "请确认 program：文档范围是「"
                + section.program_text
                + "」，你提供的是「"
                + context.program
                + "」。未确认前不会视为别名等价。"
            ),
        }
    return {"ok": True, "missing": [], "question": None}


def _role_state(context: PolicyContext, section: PolicySection) -> dict:
    if section.role_token == "participant":
        values = context.values("participating")
        if values == frozenset({True}):
            return {"ok": True, "missing": [], "explicit_false": False}
        if values == frozenset({False}):
            return {"ok": False, "missing": [], "explicit_false": True}
        return {"ok": None, "missing": ["participating"], "explicit_false": False}
    if section.role_token == "applicant":
        if context.role is None:
            return {"ok": None, "missing": ["role"], "explicit_false": False}
        if context.role == "applicant":
            return {"ok": True, "missing": [], "explicit_false": False}
        return {"ok": False, "missing": [], "explicit_false": True}
    return {"ok": None, "missing": [], "explicit_false": False}


def _task_state(
    context: PolicyContext, task_id: str
) -> tuple[str, str | None, bool]:
    completed = task_id in context.completed_tasks
    pending = task_id in context.pending_tasks
    if completed and pending:
        return "CONFLICT", None, True
    if completed:
        return TASK_COMPLETED, "COMPLETED_REVIEW", False
    if pending:
        return TASK_PENDING, "PENDING_REVIEW", False
    return TASK_UNKNOWN, "ASK_PROGRESS", False


def _policy_rule_dict(rule: PolicyRule) -> dict:
    return {
        "kind": rule.kind,
        "trigger": trigger_dict(rule.trigger),
        "task_id": rule.task_id,
        "requirement_text": rule.requirement_text,
        "clause_id": rule.clause_id,
    }


def _action_message(rule: PolicyRule, progress: str) -> str:
    if rule.kind == "DISCLOSE":
        if progress == "COMPLETED_REVIEW":
            return "你已标记披露任务完成；请核对该披露是否符合新版要求，勿默认需要再次披露。"
        if progress == "PENDING_REVIEW":
            return "你已把披露任务标记为待办；请按新版要求复核并完成披露。"
        return "请确认并复核：新版要求在使用 AI 编写代码时进行披露。"
    if progress == "COMPLETED_REVIEW":
        return "你已标记评论复核完成；请核对该做法是否符合新版政策，勿默认需要重复处理。"
    if progress == "PENDING_REVIEW":
        return "你已把评论复核标记为待办；请按新版政策复核沟通做法。"
    return "请复核：新版禁止在 issue/PR 中使用 AI 生成评论；请确认你的沟通做法。"


def _assess_rule_core(
    rule: PolicyRule,
    section: PolicySection,
    context: PolicyContext,
    change: Change | None,
    old: DocumentSnapshot,
    new: DocumentSnapshot,
    local: dict,
) -> dict:
    result = _base_result("CLAUSE", change, old, new, section, rule.evidence)
    result["clause_id"] = rule.clause_id
    result["policy_rule"] = _policy_rule_dict(rule)
    _apply_local(result, local)

    if not context.confirmed_by_user:
        return _uncertain(
            result,
            "Task facts have not been explicitly confirmed by the user.",
            ["confirmed_by_user"],
        )

    program = _program_state(context, section)
    if program["ok"] is not True:
        return _uncertain(
            result,
            "The document program scope is not confirmed exactly.",
            program["missing"],
            question=program["question"],
        )

    role = _role_state(context, section)
    if role["explicit_false"]:
        return _does_not_apply(
            result,
            "The user explicitly does not match the supported scope role.",
        )
    if role["ok"] is not True:
        return _uncertain(
            result,
            "A required scope fact is missing or unknown.",
            role["missing"],
        )

    conflicts = context.conflicts()
    if conflicts:
        return _uncertain(
            result,
            "User assertions conflict; none was selected.",
            ["conflict:" + item for item in conflicts],
        )

    truth, trace, missing = evaluate_trigger(rule.trigger, context)
    result["matched_conditions"] = [x for x in trace if x.get("result") is True]
    result["excluded_conditions"] = [x for x in trace if x.get("result") is False]
    if truth is None:
        return _uncertain(
            result,
            "A required explicit user fact is missing.",
            missing,
        )
    if truth is False:
        return _does_not_apply(
            result,
            "The supported trigger evaluates False against user-confirmed facts.",
            trace,
        )

    task_status, progress, task_conflict = _task_state(context, rule.task_id)
    if task_conflict:
        return _uncertain(
            result,
            "The same task is both completed and pending.",
            ["conflict:task:" + rule.task_id],
        )

    result["applicability_status"] = STATUS_APPLIES
    result["task_status"] = task_status
    result["action_status"] = ACTION_REVIEW
    result["confidence"] = "DETERMINISTIC_WITHIN_SUPPORTED_RULE"
    result["reasoning"].append(
        "The complete supported policy clause evaluates True against user-confirmed facts "
        "inside a locally verified added section."
    )
    result["uncertainty"] = [
        "Clause-local assessment only; no overall eligibility, compliance or action conclusion.",
    ]
    if change is not None and change.review_status != "VERIFIED":
        result["uncertainty"].append(
            "Upstream review status remains "
            + change.review_status
            + "; LOCAL_SECTION_ADDITION does not establish a global obligation."
        )
    result["recommended_actions"] = [
        {
            "change_id": result["change_id"],
            "clause_id": rule.clause_id,
            "task_id": rule.task_id,
            "kind": "HUMAN_REVIEW_ONLY",
            "progress_status": progress,
            "message": _action_message(rule, progress),
            "requirement": rule.requirement_text,
            "field_changes": [],
            "evidence_ref": rule.clause_id,
            "executes_external_action": False,
        }
    ]
    return result


def _assess_unsupported_candidate(
    candidate: PolicyClause,
    section: PolicySection,
    old: DocumentSnapshot,
    new: DocumentSnapshot,
    local: dict,
    change: Change | None = None,
) -> dict:
    result = _base_result("CLAUSE", change, old, new, section, candidate.evidence)
    result["clause_id"] = candidate.clause_id
    _apply_local(result, local)
    reason = candidate.reason or candidate.kind
    return _uncertain(
        result,
        "Unsupported or unresolved policy clause: " + reason,
    )


def _duplicate_entries(new: DocumentSnapshot) -> list[dict]:
    sections = find_policy_sections(new)
    groups: dict[str, list[tuple[PolicySection, PolicyClause]]] = {}
    for section in sections:
        for clause in section.clauses:
            if clause.kind == "RULE":
                groups.setdefault(clause.normalized_text, []).append((section, clause))
    entries = []
    for text, items in groups.items():
        if len(items) > 1:
            for section, clause in items:
                entries.append(
                    {
                        "clause_id": clause.clause_id,
                        "scope_id": section.scope_id,
                        "program_text": section.program_text,
                        "quote": clause.evidence.quote,
                    }
                )
    return entries


def _sections_with_rule(new: DocumentSnapshot, normalized_text: str) -> list[PolicySection]:
    return [
        section
        for section in find_policy_sections(new)
        if any(c.kind == "RULE" and c.normalized_text == normalized_text for c in section.clauses)
    ]


def _find_change_for_candidate(
    comparison, candidate: PolicyClause
) -> Change | None:
    for change in comparison.changes:
        evidence = change.new_evidence
        if evidence is None:
            continue
        if (
            evidence.quote == candidate.evidence.quote
            and evidence.char_start == candidate.evidence.char_start
            and evidence.char_end == candidate.evidence.char_end
        ):
            return change
    return None


def _summarize_section(
    section: PolicySection,
    old: DocumentSnapshot,
    new: DocumentSnapshot,
    context: PolicyContext,
    local: dict,
    comparison,
) -> dict:
    clause_results = []
    unresolved = []
    for candidate in section.clauses:
        if candidate.kind == "NON_RULE":
            continue
        if candidate.kind == "RULE" and candidate.rule is not None:
            change = _find_change_for_candidate(comparison, candidate)
            clause_results.append(
                _assess_rule_core(
                    candidate.rule,
                    section,
                    context,
                    change,
                    old,
                    new,
                    local,
                )
            )
        else:
            change = _find_change_for_candidate(comparison, candidate)
            clause_results.append(
                _assess_unsupported_candidate(candidate, section, old, new, local, change)
            )
            unresolved.append(
                {
                    "clause_id": candidate.clause_id,
                    "kind": candidate.kind,
                    "quote": candidate.evidence.quote,
                    "reason": candidate.reason,
                }
            )

    duplicate_group = _duplicate_entries(new)
    statuses = [r["applicability_status"] for r in clause_results]
    evidence_bad = any(r["evidence_status"] == "UNVERIFIED" for r in clause_results)
    if evidence_bad:
        applicability, action = STATUS_INSUFFICIENT, ACTION_UNVERIFIED
    elif STATUS_APPLIES in statuses:
        applicability, action = STATUS_APPLIES, ACTION_REVIEW
    elif STATUS_NEEDS_CONFIRMATION in statuses:
        applicability, action = STATUS_NEEDS_CONFIRMATION, ACTION_NEEDS_REVIEW
    elif unresolved or STATUS_INSUFFICIENT in statuses:
        applicability, action = STATUS_INSUFFICIENT, ACTION_NEEDS_REVIEW
    elif statuses and all(s == STATUS_NOT_APPLIES for s in statuses):
        applicability, action = STATUS_NOT_APPLIES, ACTION_NONE
    else:
        applicability, action = STATUS_INSUFFICIENT, ACTION_NEEDS_REVIEW

    return {
        "applicability_status": applicability,
        "action_status": action,
        "clause_results": clause_results,
        "unresolved_clauses": unresolved,
        "duplicate_group": duplicate_group,
    }


def _selection_failure(
    change: Change | None,
    old: DocumentSnapshot,
    new: DocumentSnapshot,
    reason: str,
    *,
    local: dict | None = None,
    unverified: bool = True,
) -> dict:
    result = _base_result("CLAUSE", change, old, new, None)
    _apply_local(result, local)
    return _uncertain(result, reason, unverified=unverified)


def _trigger_fields(trigger) -> set[str]:
    fields = set()
    if trigger.field:
        fields.add(trigger.field)
    for child in trigger.children:
        fields |= _trigger_fields(child)
    return fields


def assess_policy_rule(
    rule: PolicyRule,
    section: PolicySection,
    old: DocumentSnapshot,
    new: DocumentSnapshot,
    context: PolicyContext,
    change: Change | None = None,
) -> dict:
    """Assess a directly supplied PolicyRule, including compound triggers.

    This is a controlled experimental API for AND/OR/NOT trigger tests. The
    requirement text, kind and task must match a supported source sentence, and
    the trigger must reference that sentence's supported fact. The evidence must
    belong to the section and the local addition must verify.
    """
    if not isinstance(context, PolicyContext):
        raise TypeError("context must be a validated PolicyContext")
    if not isinstance(rule, PolicyRule) or not isinstance(section, PolicySection):
        raise TypeError("rule/section types are invalid")
    if not (
        section.section_char_start
        <= rule.evidence.char_start
        < rule.evidence.char_end
        <= section.section_char_end
    ):
        raise ValueError("rule evidence is outside the supplied policy section")
    normalized = match_text(rule.evidence.quote)
    entry = SUPPORTED_RULES.get(normalized)
    if entry is None:
        raise ValueError("rule evidence is not a supported policy sentence")
    kind, supported_field, task_id = entry
    if (
        rule.kind != kind
        or rule.task_id != task_id
        or rule.requirement_text != normalized
    ):
        raise ValueError("rule metadata does not match the source sentence")
    if supported_field not in _trigger_fields(rule.trigger):
        raise ValueError("rule trigger does not reference the supported fact")
    if (
        not old.is_readable
        or not new.is_readable
        or old.role != "old"
        or new.role != "new"
    ):
        result = _base_result("CLAUSE", change, old, new, section, rule.evidence)
        result["clause_id"] = rule.clause_id
        return _json_native(
            _uncertain(
                result,
                "Input snapshots are not readable old/new versions.",
                unverified=True,
            )
        )
    if not verify_evidence(new, rule.evidence):
        result = _base_result("CLAUSE", change, old, new, section, rule.evidence)
        result["clause_id"] = rule.clause_id
        return _json_native(
            _uncertain(result, "Rule evidence failed the P0-1 verifier.", unverified=True)
        )
    local = validate_local_section_addition(section, old, new)
    if local["status"] != "VERIFIED":
        result = _base_result("CLAUSE", change, old, new, section, rule.evidence)
        result["clause_id"] = rule.clause_id
        _apply_local(result, local)
        return _json_native(
            _uncertain(
                result,
                "Local section addition is not verified: " + str(local.get("reason")),
                unverified=local.get("evidence_status") == "UNVERIFIED",
            )
        )
    result = _assess_rule_core(rule, section, context, change, old, new, local)
    comparison = analyze(old, new)
    result["section_summary"] = _summarize_section(
        section, old, new, context, local, comparison
    )
    return _json_native(result)


def assess_policy_clause(
    change: Change | None,
    old: DocumentSnapshot,
    new: DocumentSnapshot,
    context: PolicyContext,
    *,
    scope_id: str | None = None,
) -> dict:
    """Assess one changed policy clause at clause level (schema 0.4)."""
    if not isinstance(context, PolicyContext):
        raise TypeError("context must be a validated PolicyContext")
    if not isinstance(old, DocumentSnapshot) or not isinstance(new, DocumentSnapshot):
        raise TypeError("old/new must be DocumentSnapshot instances")

    if (
        not old.is_readable
        or not new.is_readable
        or old.role != "old"
        or new.role != "new"
        or old.content is None
        or new.content is None
    ):
        return _json_native(
            _selection_failure(
                change,
                old,
                new,
                "Input snapshots are not readable old/new versions.",
            )
        )
    if change is None:
        return _json_native(
            _selection_failure(
                change,
                old,
                new,
                "No change record was supplied for clause assessment.",
            )
        )

    comparison = analyze(old, new)
    if change not in comparison.changes:
        return _json_native(
            _selection_failure(
                change,
                old,
                new,
                "Change is not a member of the regenerated comparison.",
            )
        )
    if change.new_evidence is None:
        return _json_native(
            _selection_failure(
                change, old, new, "Required new evidence is missing."
            )
        )
    if not verify_evidence(new, change.new_evidence):
        return _json_native(
            _selection_failure(
                change, old, new, "New evidence failed the P0-1 verifier."
            )
        )
    if change.old_evidence is not None and not verify_evidence(old, change.old_evidence):
        return _json_native(
            _selection_failure(
                change, old, new, "Old evidence failed the P0-1 verifier."
            )
        )

    sections = find_policy_sections(new)
    if scope_id is not None:
        matched = [s for s in sections if s.scope_id == scope_id]
        if not matched:
            local = {
                "kind": "LOCAL_SECTION_ADDITION",
                "status": "NOT_VERIFIED",
                "reason": "SCOPE_ID_MISMATCH",
                "evidence_status": "UNVERIFIED",
            }
            return _json_native(
                _selection_failure(
                    change,
                    old,
                    new,
                    "The supplied scope_id does not match a parsed policy section.",
                    local=local,
                )
            )
        section = matched[0]
    else:
        containing = [
            s
            for s in sections
            if s.section_char_start <= change.new_evidence.char_start
            and change.new_evidence.char_end <= s.section_char_end
        ]
        if not containing:
            return _json_native(
                _selection_failure(
                    change,
                    old,
                    new,
                    "No supported document-level policy section contains this clause.",
                )
            )
        if len(containing) > 1:
            return _json_native(
                _selection_failure(
                    change,
                    old,
                    new,
                    "Multiple policy sections contain this clause; selection is ambiguous.",
                    unverified=False,
                )
            )
        section = containing[0]

    local = validate_local_section_addition(section, old, new)
    if local["status"] != "VERIFIED":
        result = _base_result("CLAUSE", change, old, new, section, change.new_evidence)
        _apply_local(result, local)
        return _json_native(
            _uncertain(
                result,
                "Local section addition is not verified: " + str(local.get("reason")),
                unverified=local.get("evidence_status") == "UNVERIFIED",
            )
        )

    normalized = match_text(change.new_evidence.quote)
    if scope_id is None:
        duplicate_sections = _sections_with_rule(new, normalized)
        if len(duplicate_sections) > 1:
            result = _base_result("CLAUSE", change, old, new, section, change.new_evidence)
            result["clause_id"] = _clause_id_for_quote(section, normalized)
            _apply_local(result, local)
            result["section_summary"] = {
                "applicability_status": STATUS_INSUFFICIENT,
                "action_status": ACTION_NEEDS_REVIEW,
                "clause_results": [],
                "unresolved_clauses": [],
                "duplicate_group": _duplicate_entries(new),
            }
            return _json_native(
                _uncertain(
                    result,
                    "DUPLICATE_ACROSS_SECTIONS: the same policy obligation occurs in multiple sections; scope selection is ambiguous.",
                )
            )

    candidates = [
        c
        for c in section.clauses
        if c.evidence.quote == change.new_evidence.quote
        and c.evidence.char_start == change.new_evidence.char_start
        and c.evidence.char_end == change.new_evidence.char_end
    ]
    if not candidates:
        candidates = [
            c
            for c in section.clauses
            if c.normalized_text == normalized and c.kind != "NON_RULE"
        ]
    if len(candidates) != 1:
        result = _base_result("CLAUSE", change, old, new, section, change.new_evidence)
        _apply_local(result, local)
        result["section_summary"] = _summarize_section(
            section, old, new, context, local, comparison
        )
        return _json_native(
            _uncertain(
                result,
                "The changed clause is ambiguous within the policy section.",
                unverified=False,
            )
        )
    candidate = candidates[0]
    if candidate.kind == "AMBIGUOUS_CLAUSE":
        result = _base_result("CLAUSE", change, old, new, section, change.new_evidence)
        result["clause_id"] = candidate.clause_id
        _apply_local(result, local)
        result["section_summary"] = _summarize_section(
            section, old, new, context, local, comparison
        )
        return _json_native(
            _uncertain(result, "Duplicate policy clause; no occurrence was selected.")
        )
    if candidate.kind != "RULE" or candidate.rule is None:
        result = _assess_unsupported_candidate(
            candidate, section, old, new, local, change
        )
        result["section_summary"] = _summarize_section(
            section, old, new, context, local, comparison
        )
        return _json_native(result)

    result = _assess_rule_core(
        candidate.rule, section, context, change, old, new, local
    )
    result["section_summary"] = _summarize_section(
        section, old, new, context, local, comparison
    )
    return _json_native(result)


def _clause_id_for_quote(section: PolicySection, normalized: str) -> str | None:
    matches = [c for c in section.clauses if c.normalized_text == normalized]
    return matches[0].clause_id if len(matches) == 1 else None


def _section_summary_failure(
    section: PolicySection | None,
    old: DocumentSnapshot,
    new: DocumentSnapshot,
    reason: str,
    *,
    applicability: str = STATUS_INSUFFICIENT,
    action: str = ACTION_NEEDS_REVIEW,
    evidence_status: str = "UNVERIFIED",
    local: dict | None = None,
    duplicate_group: list[dict] | None = None,
) -> dict:
    result = _base_result("SECTION", None, old, new, section)
    _apply_local(result, local)
    if local is None:
        result["evidence_status"] = evidence_status
    result["applicability_status"] = applicability
    result["action_status"] = action
    result["reasoning"].append(reason)
    result["uncertainty"].append(reason)
    result["recommended_actions"] = []
    result["section_summary"] = {
        "applicability_status": applicability,
        "action_status": action,
        "clause_results": [],
        "unresolved_clauses": [],
        "duplicate_group": duplicate_group or [],
    }
    return _json_native(result)


def assess_policy_section(
    section: PolicySection | str,
    old: DocumentSnapshot,
    new: DocumentSnapshot,
    context: PolicyContext,
) -> dict:
    """Assess a whole policy section conservatively, preserving clause detail."""
    if not isinstance(context, PolicyContext):
        raise TypeError("context must be a validated PolicyContext")
    if not isinstance(old, DocumentSnapshot) or not isinstance(new, DocumentSnapshot):
        raise TypeError("old/new must be DocumentSnapshot instances")

    if isinstance(section, str):
        matched = [s for s in find_policy_sections(new) if s.scope_id == section]
        if not matched:
            local = {
                "kind": "LOCAL_SECTION_ADDITION",
                "status": "NOT_VERIFIED",
                "reason": "SCOPE_ID_MISMATCH",
                "evidence_status": "UNVERIFIED",
            }
            return _section_summary_failure(
                None,
                old,
                new,
                "The supplied scope_id does not match a parsed policy section.",
                local=local,
            )
        section = matched[0]
    if not isinstance(section, PolicySection):
        raise TypeError("section must be a PolicySection or scope_id")

    if (
        not old.is_readable
        or not new.is_readable
        or old.role != "old"
        or new.role != "new"
    ):
        return _section_summary_failure(
            section, old, new, "Input snapshots are not readable old/new versions."
        )

    program = _program_state(context, section)
    if program["ok"] is not True:
        return _section_summary_failure(
            section,
            old,
            new,
            "The document program scope is not confirmed exactly.",
            applicability=STATUS_NEEDS_CONFIRMATION,
            action=ACTION_NEEDS_REVIEW,
            evidence_status="VERIFIED",
            duplicate_group=_duplicate_entries(new),
        )

    role = _role_state(context, section)
    if role["explicit_false"]:
        return _section_summary_failure(
            section,
            old,
            new,
            "The user explicitly does not match the supported scope role.",
            applicability=STATUS_NOT_APPLIES,
            action=ACTION_NONE,
            evidence_status="VERIFIED",
            duplicate_group=_duplicate_entries(new),
        )
    if role["ok"] is not True:
        return _section_summary_failure(
            section,
            old,
            new,
            "A required scope fact is missing or unknown.",
            applicability=STATUS_NEEDS_CONFIRMATION,
            action=ACTION_NEEDS_REVIEW,
            evidence_status="VERIFIED",
            duplicate_group=_duplicate_entries(new),
        )

    local = validate_local_section_addition(section, old, new)
    if local["status"] != "VERIFIED":
        return _section_summary_failure(
            section,
            old,
            new,
            "Local section addition is not verified: " + str(local.get("reason")),
            applicability=STATUS_INSUFFICIENT,
            action=ACTION_NEEDS_REVIEW,
            evidence_status=local.get("evidence_status", "UNVERIFIED"),
            local=local,
            duplicate_group=_duplicate_entries(new),
        )

    comparison = analyze(old, new)
    summary = _summarize_section(section, old, new, context, local, comparison)
    result = _base_result("SECTION", None, old, new, section)
    _apply_local(result, local)
    result["applicability_status"] = summary["applicability_status"]
    result["action_status"] = summary["action_status"]
    result["confidence"] = (
        "DETERMINISTIC_WITHIN_SUPPORTED_RULE"
        if summary["action_status"] in {ACTION_REVIEW, ACTION_NONE}
        else "UNDETERMINED"
    )
    result["reasoning"].append(
        "Section summary preserves clause-level results; unresolved clauses are not promoted."
    )
    result["uncertainty"].append(
        "Section-level summary is conservative and does not imply global compliance."
    )
    result["section_summary"] = summary
    return _json_native(result)
