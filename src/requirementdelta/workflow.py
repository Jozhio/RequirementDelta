"""P0-4 workflow: read-only orchestration from snapshots to a stable report.

This module does not write files. The CLI owns path safety and file output.
P0-1/P0-2/P0-3/P0-3.2 behavior is reused through their public APIs.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import asdict

from .applicability import assess
from .changes import Change, analyze
from .ingest import DocumentSnapshot
from .policy_applicability import assess_policy_clause, assess_policy_section
from .policy_context import PolicyContext
from .policy_scope import find_policy_sections
from .task_context import UserTaskContext

REPORT_SCHEMA = "p0-4-report-v1"
TOOL_NAME = "requirementdelta"
TOOL_STAGE = "P0-4"

OVERALL_REVIEW = "REVIEW_REQUIRED"
OVERALL_NO_SUPPORTED = "NO_SUPPORTED_CHANGE_FOUND"
OVERALL_NO_TEXT = "NO_TEXT_DIFFERENCE"
OVERALL_UNVERIFIED = "UNVERIFIED"

STATUS_APPLIES = "APPLIES"
STATUS_NOT_APPLIES = "DOES_NOT_APPLY"
STATUS_NEEDS_CONFIRMATION = "NEEDS_CONFIRMATION"
STATUS_INSUFFICIENT = "INSUFFICIENT_CONTEXT"
STATUS_UNVERIFIED = "UNVERIFIED"

APPLICABILITY_STATUSES = (
    STATUS_APPLIES,
    STATUS_NOT_APPLIES,
    STATUS_NEEDS_CONFIRMATION,
    STATUS_INSUFFICIENT,
)
ACTION_STATUSES = ("ACTION_REVIEW_REQUIRED", "NO_CURRENT_ACTION", "NEEDS_REVIEW", "UNVERIFIED")
TASK_STATUSES = ("COMPLETED", "PENDING", "UNKNOWN", "NOT_APPLICABLE")


def _canonical(payload: dict) -> str:
    # P0-3/P0-3.2 use json.dumps defaults (including spaces) for change_id.
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def change_id_for(
    change: Change, old: DocumentSnapshot, new: DocumentSnapshot
) -> str:
    """Same deterministic formula as P0-3's clause result change_id."""
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
    return "C-" + hashlib.sha256(_canonical(refs).encode("utf-8")).hexdigest()[:24]


def _evidence(evidence) -> dict | None:
    return asdict(evidence) if evidence is not None else None


def _change_dict(change: Change, old: DocumentSnapshot, new: DocumentSnapshot) -> dict:
    return {
        "change_id": change_id_for(change, old, new),
        "relation": change.relation,
        "material_status": change.material_status,
        "review_status": change.review_status,
        "reason": change.reason,
        "score": change.score,
        "fields": [asdict(field) for field in change.fields],
        "old_evidence": _evidence(change.old_evidence),
        "new_evidence": _evidence(change.new_evidence),
        "old_context": list(change.old_context),
        "new_context": list(change.new_context),
    }


def _assessment_key(result: dict):
    refs = result.get("evidence_refs") or {}
    new = refs.get("new") or {}
    if new:
        return (
            "evidence",
            new.get("doc_sha256"),
            new.get("byte_start"),
            new.get("byte_end"),
            new.get("quote"),
        )
    return ("change", result.get("change_id"))


def _is_interesting(change: Change) -> bool:
    return change.relation != "UNCHANGED" or change.material_status != "UNCHANGED"


def _normalize_03(result: dict) -> dict:
    """Add the P0-4 task_status separation to a P0-3 0.3 result."""
    normalized = dict(result)
    normalized["source"] = "P0_3"
    if normalized.get("task_status"):
        return normalized
    status = normalized.get("applicability_status")
    actions = normalized.get("recommended_actions") or []
    if status == STATUS_NOT_APPLIES:
        normalized["task_status"] = "NOT_APPLICABLE"
    elif status == STATUS_APPLIES and actions:
        progress = actions[0].get("progress_status")
        normalized["task_status"] = {
            "COMPLETED_REVIEW": "COMPLETED",
            "PENDING_REVIEW": "PENDING",
            "ASK_PROGRESS": "UNKNOWN",
        }.get(progress, "UNKNOWN")
    else:
        normalized["task_status"] = "UNKNOWN"
    return normalized


def _context_info(context) -> dict:
    if context is None:
        return {"provided": False, "schema_version": None}
    info = {
        "provided": True,
        "schema_version": context.schema_version,
        "confirmed_by_user": context.confirmed_by_user,
        "facts": [{"field": fact.field, "value": fact.value} for fact in context.facts],
        "completed_tasks": list(context.completed_tasks),
        "pending_tasks": list(context.pending_tasks),
    }
    if isinstance(context, PolicyContext):
        info["program"] = context.program
        info["role"] = context.role
    return info


def _policy_sections_for(
    old: DocumentSnapshot,
    new: DocumentSnapshot,
    comparison,
    context: PolicyContext,
) -> tuple[list[dict], list[dict]]:
    """Return (0.4 clause results, section summaries) for changed policy sections."""
    clause_results = []
    section_rows = []
    changed_evidence = [c.new_evidence for c in comparison.changes if c.new_evidence]
    for section in find_policy_sections(new):
        contained = [
            ev
            for ev in changed_evidence
            if section.section_char_start <= ev.char_start and ev.char_end <= section.section_char_end
        ]
        if not contained:
            continue
        section_result = assess_policy_section(section.scope_id, old, new, context)
        summary = section_result.get("section_summary") or {}
        section_rows.append(
            {
                "scope_id": section.scope_id,
                "program_text": section.program_text,
                "role_text": section.role_text,
                "role_token": section.role_token,
                "heading_path": list(section.heading_path),
                "section_byte_start": section.section_byte_start,
                "section_byte_end": section.section_byte_end,
                "applicability_status": summary.get("applicability_status"),
                "action_status": summary.get("action_status"),
                "unresolved_clauses": summary.get("unresolved_clauses", []),
                "duplicate_group": summary.get("duplicate_group", []),
                "local_validation_status": section_result.get("local_validation_status"),
            }
        )
        for clause in section.clauses:
            if clause.kind != "RULE" or clause.rule is None:
                continue
            change = next(
                (
                    c
                    for c in comparison.changes
                    if c.new_evidence is not None
                    and c.new_evidence.quote == clause.evidence.quote
                    and c.new_evidence.char_start == clause.evidence.char_start
                    and c.new_evidence.char_end == clause.evidence.char_end
                ),
                None,
            )
            if change is None:
                continue
            result = assess_policy_clause(
                change, old, new, context, scope_id=section.scope_id
            )
            result["source"] = "P0_3_2"
            clause_results.append(result)
    return clause_results, section_rows


def build_report(
    old: DocumentSnapshot,
    new: DocumentSnapshot,
    context: UserTaskContext | PolicyContext | None,
) -> dict:
    """Build the stable P0-4 report dict. Pure; no file writes."""
    if not old.is_readable or not new.is_readable:
        return build_error_report(
            old,
            new,
            "Input snapshots are not readable; no change judgment is possible.",
        )

    comparison = analyze(old, new)
    changes = [_change_dict(change, old, new) for change in comparison.changes if _is_interesting(change)]

    assessments = []
    policy_sections = []
    if context is not None:
        base = context.base_context() if isinstance(context, PolicyContext) else context
        assessments = [
            _normalize_03(result)
            for result in assess(old, new, base)
        ]
    if isinstance(context, PolicyContext):
        policy_results, policy_sections = _policy_sections_for(
            old, new, comparison, context
        )
        merged = {_assessment_key(result): result for result in assessments}
        for result in policy_results:
            merged[_assessment_key(result)] = result
        assessments = list(merged.values())
    assessments.sort(
        key=lambda result: (
            str(result.get("change_id") or ""),
            str(result.get("clause_id") or ""),
            str(result.get("source") or ""),
        )
    )

    status_counts = Counter(
        result.get("applicability_status") for result in assessments
    )
    action_counts = Counter(result.get("action_status") for result in assessments)
    task_counts = Counter(result.get("task_status") for result in assessments)
    action_total = sum(len(result.get("recommended_actions") or []) for result in assessments)
    unassessed = [
        change
        for change in changes
        if change["change_id"] not in {result.get("change_id") for result in assessments}
    ]

    review_items = _review_items(assessments, changes, policy_sections)
    unverified_items = _unverified_items(comparison, assessments)
    unsafe = sum(
        1
        for result in assessments
        if result.get("applicability_status")
        in {STATUS_NEEDS_CONFIRMATION, STATUS_INSUFFICIENT, STATUS_UNVERIFIED}
        and (result.get("recommended_actions") or [])
    )

    if comparison.review_status == "UNVERIFIED" or any(
        result.get("evidence_status") == "UNVERIFIED" for result in assessments
    ):
        overall = OVERALL_UNVERIFIED
    elif (
        any(
            result.get("applicability_status")
            in {STATUS_NEEDS_CONFIRMATION, STATUS_INSUFFICIENT}
            for result in assessments
        )
        or changes
        or review_items
    ):
        overall = OVERALL_REVIEW
    elif old.content == new.content:
        overall = OVERALL_NO_TEXT
    else:
        overall = OVERALL_NO_SUPPORTED

    warnings = []
    if context is None:
        warnings.append(
            "No user context was provided: applicability was not assessed; only changes and evidence are reported."
        )
    elif isinstance(context, UserTaskContext) and not isinstance(context, PolicyContext):
        warnings.append(
            "A 0.3 context was provided. Document-level AI policy clauses require a 0.4 PolicyContext with an exact program anchor."
        )
    if overall == OVERALL_NO_TEXT:
        warnings.append(
            "Old and new text are byte-identical. This is not a global 'confirmed no change' conclusion for unsupported formats or semantics."
        )
    if overall == OVERALL_NO_SUPPORTED:
        warnings.append(
            "No supported change was found. This is not a global 'confirmed no change' conclusion; unsupported formats and semantics remain unverified."
        )

    report = {
        "schema_version": REPORT_SCHEMA,
        "tool": {"name": TOOL_NAME, "stage": TOOL_STAGE},
        "run": {
            "mode": "TEXT_COMPARISON",
            "context_provided": context is not None,
            "context_schema": getattr(context, "schema_version", None),
        },
        "inputs": {
            "old": _input_row(old),
            "new": _input_row(new),
        },
        "context": _context_info(context),
        "comparison": {
            "schema_version": comparison.schema_version,
            "text_status": comparison.text_status,
            "material_status": comparison.material_status,
            "review_status": comparison.review_status,
            "old_sha256": comparison.old_sha256,
            "new_sha256": comparison.new_sha256,
            "limitations": list(comparison.limitations),
        },
        "summary": {
            "overall_status": overall,
            "changes_total": len(changes),
            "changes_changed": sum(1 for c in changes if c["material_status"] == "CHANGED"),
            "changes_unknown": sum(1 for c in changes if c["material_status"] == "UNKNOWN"),
            "changes_review": sum(1 for c in changes if c["review_status"] == "NEEDS_REVIEW"),
            "assessments_total": len(assessments),
            "assessment_source_counts": dict(Counter(result.get("source") for result in assessments)),
            "applicability_counts": {
                status: status_counts.get(status, 0) for status in APPLICABILITY_STATUSES
            },
            "action_counts": {
                status: action_counts.get(status, 0) for status in ACTION_STATUSES
            },
            "task_counts": {
                status: task_counts.get(status, 0) for status in TASK_STATUSES
            },
            "recommended_actions_total": action_total,
            "review_items_total": len(review_items),
            "unverified_items_total": len(unverified_items),
            "unassessed_changes_total": len(unassessed),
            "unsafe_deterministic_actions": unsafe,
        },
        "changes": changes,
        "correspondences": [
            {
                "relation": link.relation,
                "review_status": link.review_status,
                "reason": link.reason,
                "old_evidence": _evidence(link.old_evidence),
                "new_evidence": _evidence(link.new_evidence),
            }
            for link in comparison.correspondences
        ],
        "assessments": assessments,
        "policy_sections": policy_sections,
        "review_items": review_items,
        "unverified_items": unverified_items,
        "warnings": warnings,
        "coverage": _coverage(),
        "read_only": {"inputs_unchanged": None, "checked": False},
        "errors": [],
    }
    return json.loads(json.dumps(report, ensure_ascii=False))


def _input_row(snapshot: DocumentSnapshot) -> dict:
    return {
        "role": snapshot.role,
        "path": snapshot.path,
        "status": snapshot.status,
        "sha256": snapshot.sha256,
        "error_code": snapshot.error_code,
        "error_message": snapshot.error_message,
    }


def _review_items(assessments, changes, policy_sections) -> list[dict]:
    items = []
    seen = set()

    def add(item: dict) -> None:
        key = (
            item.get("kind"),
            item.get("change_id"),
            item.get("clause_id"),
            item.get("scope_id"),
            item.get("quote"),
            item.get("task_id"),
        )
        if key in seen:
            return
        seen.add(key)
        items.append(item)

    for change in changes:
        if change["review_status"] == "NEEDS_REVIEW":
            add(
                {
                    "kind": "CHANGE_REVIEW",
                    "change_id": change["change_id"],
                    "relation": change["relation"],
                    "material_status": change["material_status"],
                    "review_status": change["review_status"],
                    "reason": change["reason"],
                }
            )
    for result in assessments:
        status = result.get("applicability_status")
        if status in {STATUS_NEEDS_CONFIRMATION, STATUS_INSUFFICIENT} or result.get(
            "action_status"
        ) in {"NEEDS_REVIEW", "UNVERIFIED"}:
            add(
                {
                    "kind": "ASSESSMENT_REVIEW",
                    "source": result.get("source"),
                    "change_id": result.get("change_id"),
                    "clause_id": result.get("clause_id"),
                    "applicability_status": status,
                    "action_status": result.get("action_status"),
                    "evidence_status": result.get("evidence_status"),
                    "local_validation_status": result.get("local_validation_status"),
                    "questions": result.get("questions", []),
                    "reasoning": result.get("reasoning", []),
                }
            )
        for action in result.get("recommended_actions") or []:
            add(
                {
                    "kind": "HUMAN_ACTION",
                    "source": result.get("source"),
                    "change_id": result.get("change_id"),
                    "clause_id": result.get("clause_id"),
                    "task_id": action.get("task_id"),
                    "progress_status": action.get("progress_status"),
                    "message": action.get("message"),
                    "requirement": action.get("requirement"),
                    "executes_external_action": action.get("executes_external_action"),
                }
            )
    for section in policy_sections:
        for unresolved in section.get("unresolved_clauses", []):
            add(
                {
                    "kind": "UNRESOLVED_POLICY_CLAUSE",
                    "scope_id": section.get("scope_id"),
                    "clause_id": unresolved.get("clause_id"),
                    "clause_kind": unresolved.get("kind"),
                    "quote": unresolved.get("quote"),
                    "reason": unresolved.get("reason"),
                    "message": "Unresolved policy obligation; manual review required.",
                }
            )
    return json.loads(json.dumps(items, ensure_ascii=False))


def _unverified_items(comparison, assessments) -> list[dict]:
    items = []
    if comparison.review_status == "UNVERIFIED":
        items.append(
            {
                "kind": "COMPARISON",
                "review_status": comparison.review_status,
                "limitations": list(comparison.limitations),
            }
        )
    for result in assessments:
        if result.get("evidence_status") == "UNVERIFIED":
            items.append(
                {
                    "kind": "ASSESSMENT_EVIDENCE",
                    "source": result.get("source"),
                    "change_id": result.get("change_id"),
                    "clause_id": result.get("clause_id"),
                    "applicability_status": result.get("applicability_status"),
                    "action_status": result.get("action_status"),
                }
            )
    return json.loads(json.dumps(items, ensure_ascii=False))


def _coverage() -> dict:
    return {
        "formats": ["txt", "md"],
        "encoding": "strict UTF-8",
        "change_rules": "P0-2 finite literal rules; no general semantic diff",
        "applicability_rules": "P0-3 controlled Chinese participant clauses and project-hours table",
        "policy_rules": [
            "Always disclose if AI was used in the code.",
            "Do not use AI generated comments in any issues or PRs, use your own voice.",
        ],
        "limitations": [
            "Only UTF-8 .txt/.md input; PDF/DOCX/scanned files are unsupported.",
            "No OCR, web monitoring, paid API, LLM, or external upload.",
            "P0-2 detects only a bounded literal subset; it is not general semantic understanding.",
            "P0-3 supports a controlled Chinese grammar; P0-3.2 supports two exact AI policy sentences.",
            "No user context means no applicability assessment.",
            "Evidence is local and versioned by SHA-256; it is not proof of official authenticity.",
            "This report is a human-review aid, not legal, compliance, or eligibility advice.",
            "Windows file symlinks remain unverified in this environment (2 pytest skips).",
        ],
        "no_change_meaning": (
            "NO_TEXT_DIFFERENCE means the two decoded texts are identical. "
            "NO_SUPPORTED_CHANGE_FOUND means no change was found within the supported rules. "
            "Neither is a global 'confirmed no change' conclusion."
        ),
    }


def build_error_report(
    old: DocumentSnapshot | None,
    new: DocumentSnapshot | None,
    message: str,
    *,
    context_error: str | None = None,
) -> dict:
    """Fail-closed report for unreadable input, invalid context, or internal errors."""
    def row(snapshot, role):
        if snapshot is None:
            return {
                "role": role,
                "path": None,
                "status": "ERROR",
                "sha256": None,
                "error_code": "NOT_READ",
                "error_message": message,
            }
        return _input_row(snapshot)

    errors = [message]
    if context_error:
        errors.append(context_error)
    report = {
        "schema_version": REPORT_SCHEMA,
        "tool": {"name": TOOL_NAME, "stage": TOOL_STAGE},
        "run": {
            "mode": "TEXT_COMPARISON",
            "context_provided": context_error is None and False,
            "context_schema": None,
        },
        "inputs": {"old": row(old, "old"), "new": row(new, "new")},
        "context": {"provided": False, "schema_version": None},
        "comparison": {
            "schema_version": "0.2",
            "text_status": "UNVERIFIED",
            "material_status": "UNKNOWN",
            "review_status": "UNVERIFIED",
            "old_sha256": old.sha256 if old else None,
            "new_sha256": new.sha256 if new else None,
            "limitations": ["Input or context is not verified; no change judgment is possible."],
        },
        "summary": {
            "overall_status": OVERALL_UNVERIFIED,
            "changes_total": 0,
            "changes_changed": 0,
            "changes_unknown": 0,
            "changes_review": 0,
            "assessments_total": 0,
            "assessment_source_counts": {},
            "applicability_counts": {status: 0 for status in APPLICABILITY_STATUSES},
            "action_counts": {status: 0 for status in ACTION_STATUSES},
            "task_counts": {status: 0 for status in TASK_STATUSES},
            "recommended_actions_total": 0,
            "review_items_total": 0,
            "unverified_items_total": len(errors),
            "unassessed_changes_total": 0,
            "unsafe_deterministic_actions": 0,
        },
        "changes": [],
        "correspondences": [],
        "assessments": [],
        "policy_sections": [],
        "review_items": [],
        "unverified_items": [{"kind": "ERROR", "message": error} for error in errors],
        "warnings": ["Fail-closed report: do not read this as 'no change'."],
        "coverage": _coverage(),
        "read_only": {"inputs_unchanged": None, "checked": False},
        "errors": errors,
    }
    return json.loads(json.dumps(report, ensure_ascii=False))
