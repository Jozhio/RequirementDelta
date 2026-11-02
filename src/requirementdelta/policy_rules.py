"""Controlled DISCLOSE / PROHIBITION policy rules and stable clause IDs.

Only the exact supported sentences are recognized. Everything else must be
reported as unsupported, never guessed from keywords.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from .conditions import Condition, evaluate_condition
from .evidence import Evidence
from .segment import match_text


def canonical_json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def make_clause_id(evidence: Evidence) -> str:
    payload = {
        "schema": "clause-id-1",
        "doc_sha256": evidence.doc_sha256,
        "role": evidence.role,
        "byte_start": evidence.byte_start,
        "byte_end": evidence.byte_end,
        "quote": evidence.quote,
    }
    return "CL-" + hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()[:24]


@dataclass(frozen=True)
class PolicyRule:
    kind: str
    trigger: Condition
    task_id: str
    requirement_text: str
    evidence: Evidence
    clause_id: str


# exact normalized sentence -> (kind, trigger fact, task id)
SUPPORTED_RULES = {
    "Always disclose if AI was used in the code.": (
        "DISCLOSE",
        "condition:uses_ai_for_code",
        "submit:ai_code_disclosure",
    ),
    "Do not use AI generated comments in any issues or PRs, use your own voice.": (
        "PROHIBITION",
        "condition:uses_ai_for_comments",
        "review:ai_comments",
    ),
}


def parse_policy_rule(text: str, evidence: Evidence) -> PolicyRule | None:
    """Return a controlled rule only for an exact supported sentence."""
    normalized = match_text(text)
    entry = SUPPORTED_RULES.get(normalized)
    if entry is None:
        return None
    kind, field, task_id = entry
    return PolicyRule(
        kind=kind,
        trigger=Condition("EQ", field, True),
        task_id=task_id,
        requirement_text=normalized,
        evidence=evidence,
        clause_id=make_clause_id(evidence),
    )


def evaluate_trigger(trigger: Condition, context) -> tuple[bool | None, list[dict], list[str]]:
    """Evaluate an atomic or AND/OR/NOT trigger with three-valued logic.

    ``context`` is a PolicyContext or a 0.3 UserTaskContext. Unknown values
    propagate exactly as in ``conditions.evaluate_condition``.
    """
    base = context.base_context() if hasattr(context, "base_context") else context
    return evaluate_condition(trigger, base)


def trigger_dict(trigger: Condition) -> dict:
    """JSON-native trigger. Atomic rules omit the empty children list."""
    if not trigger.children:
        return {"field": trigger.field, "operator": trigger.op, "value": trigger.value}
    return {
        "operator": trigger.op,
        "field": trigger.field,
        "value": trigger.value,
        "children": [trigger_dict(child) for child in trigger.children],
    }
