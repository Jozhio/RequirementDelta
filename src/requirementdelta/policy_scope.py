"""Document-level policy section parsing and strict LOCAL_SECTION_ADDITION.

Only an exact H3 ``AI Policies`` section under an H2 program heading with one
supported participant declaration is recognized. Unsupported structures are
not guessed. The local addition proof requires that removing the added block
from the new document reproduces the old document exactly.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, replace

from .evidence import Evidence, build_evidence, verify_evidence
from .ingest import DocumentSnapshot
from .policy_rules import (
    PolicyRule,
    canonical_json,
    make_clause_id,
    parse_policy_rule,
)
from .segment import match_text

POLICY_HEADING = "AI Policies"
ROLE_TOKENS = {"Participants": "participant", "Applicants": "applicant"}
LEADIN_TEXTS = {
    "Participants should follow these guidelines:",
    "Applicants should follow these guidelines:",
    "In summary participants should follow these guidelines:",
}
_LINE_RE = re.compile(r"[^\r\n]+")
_HEADING_RE = re.compile(r"^[ \t﻿]*(#{1,6})[ \t]+(.+?)\s*$")
_DECL_RE = re.compile(r"^(Participants|Applicants)\s+(should|must|are)\b")
_NUMBERED_RE = re.compile(r"^\s*\d+[.)]\s+(.*)$")
_OBLIGATION_RE = re.compile(
    r"\b(?:should|must|do not|required|be sure)\b|禁止|必须|不得|应|须", re.I
)


@dataclass(frozen=True)
class _Heading:
    level: int
    text: str
    start: int
    end: int


@dataclass(frozen=True)
class PolicyClause:
    kind: str
    evidence: Evidence
    normalized_text: str
    rule: PolicyRule | None
    reason: str | None
    clause_id: str


@dataclass(frozen=True)
class PolicySection:
    scope_id: str
    program_text: str
    role_text: str
    role_token: str
    policy_heading: str
    heading_path: tuple[str, ...]
    heading_evidence: Evidence
    declaration_evidence: Evidence
    section_char_start: int
    section_char_end: int
    section_byte_start: int
    section_byte_end: int
    section_sha256: str
    clauses: tuple[PolicyClause, ...]
    supported: bool
    reason: str | None


def _headings(content: str) -> list[_Heading]:
    result = []
    for match in _LINE_RE.finditer(content):
        line = match.group()
        heading = _HEADING_RE.match(line)
        if heading:
            result.append(
                _Heading(
                    level=len(heading.group(1)),
                    text=heading.group(2).strip(),
                    start=match.start(),
                    end=match.end(),
                )
            )
    return result


def _stack_for(headings: list[_Heading], index: int) -> list[_Heading]:
    stack: list[_Heading] = []
    for heading in headings[: index + 1]:
        while stack and stack[-1].level >= heading.level:
            stack.pop()
        stack.append(heading)
    return stack


def _section_end(headings: list[_Heading], index: int, content_len: int) -> int:
    level = headings[index].level
    for heading in headings[index + 1 :]:
        if heading.level <= level:
            return heading.start
    return content_len


def _find_declaration(
    content: str,
    section_start: int,
    section_end: int,
    heading_starts: set[int],
) -> tuple[str | None, int | None, int | None]:
    found: list[tuple[str, int, int]] = []
    for match in _LINE_RE.finditer(content):
        if match.start() <= section_start or match.start() >= section_end:
            continue
        if match.start() in heading_starts:
            continue
        line = match.group().strip()
        if _NUMBERED_RE.match(line):
            continue
        declaration = _DECL_RE.match(line)
        if declaration:
            found.append((declaration.group(1), match.start(), match.end()))
    if len(found) != 1:
        return None, None, None
    return found[0]


def _scope_id(
    snapshot: DocumentSnapshot,
    heading_path: tuple[str, ...],
    program_text: str,
    role_token: str,
    section_byte_start: int,
    section_byte_end: int,
) -> str:
    payload = {
        "schema": "scope-id-1",
        "doc_sha256": snapshot.sha256,
        "heading_path": list(heading_path),
        "policy_heading": POLICY_HEADING,
        "section_byte_start": section_byte_start,
        "section_byte_end": section_byte_end,
        "program_text": program_text,
        "role_token": role_token,
    }
    return "SC-" + hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()[:24]


def _classify_clauses(
    snapshot: DocumentSnapshot,
    content: str,
    section_start: int,
    section_end: int,
    heading_starts: set[int],
    declaration_start: int,
) -> tuple[PolicyClause, ...]:
    clauses: list[PolicyClause] = []
    for match in _LINE_RE.finditer(content):
        if match.start() <= section_start or match.start() >= section_end:
            continue
        if match.start() in heading_starts:
            continue
        text = match.group()
        stripped = text.strip()
        if not stripped:
            continue
        evidence = build_evidence(snapshot, match.start(), match.end())
        if not verify_evidence(snapshot, evidence):
            raise ValueError("clause evidence failed verification")
        clause_id = make_clause_id(evidence)
        numbered = _NUMBERED_RE.match(text)
        if numbered:
            normalized = match_text(text)
            rule = parse_policy_rule(text, evidence)
            if rule is None:
                clauses.append(
                    PolicyClause(
                        "UNSUPPORTED_RULE", evidence, normalized, None,
                        "UNSUPPORTED_RULE", clause_id,
                    )
                )
            else:
                clauses.append(
                    PolicyClause("RULE", evidence, normalized, rule, None, clause_id)
                )
            continue
        if match.start() == declaration_start:
            if stripped in LEADIN_TEXTS:
                clauses.append(
                    PolicyClause("NON_RULE", evidence, stripped, None, None, clause_id)
                )
            else:
                clauses.append(
                    PolicyClause(
                        "UNPARSED_OBLIGATION", evidence, stripped, None,
                        "UNPARSED_OBLIGATION", clause_id,
                    )
                )
            continue
        if stripped in LEADIN_TEXTS:
            clauses.append(
                PolicyClause("NON_RULE", evidence, stripped, None, None, clause_id)
            )
        elif _OBLIGATION_RE.search(stripped):
            clauses.append(
                PolicyClause(
                    "UNPARSED_OBLIGATION", evidence, stripped, None,
                    "UNPARSED_OBLIGATION", clause_id,
                )
            )
        else:
            clauses.append(
                PolicyClause("NON_RULE", evidence, stripped, None, None, clause_id)
            )

    counts: dict[str, int] = {}
    for clause in clauses:
        if clause.kind in {"RULE", "UNSUPPORTED_RULE"}:
            counts[clause.normalized_text] = counts.get(clause.normalized_text, 0) + 1
    result = []
    for clause in clauses:
        if clause.kind in {"RULE", "UNSUPPORTED_RULE"} and counts[clause.normalized_text] > 1:
            result.append(
                replace(
                    clause,
                    kind="AMBIGUOUS_CLAUSE",
                    rule=None,
                    reason="AMBIGUOUS_CLAUSE",
                )
            )
        else:
            result.append(clause)
    return tuple(result)


def _build_section(
    snapshot: DocumentSnapshot,
    headings: list[_Heading],
    index: int,
    content: str,
) -> PolicySection | None:
    heading = headings[index]
    stack = _stack_for(headings, index)
    parent = next((h for h in reversed(stack[:-1]) if h.level == 2), None)
    if parent is None:
        return None
    heading_path = tuple(h.text for h in stack)
    section_end = _section_end(headings, index, len(content))
    heading_starts = {h.start for h in headings}
    role_text, declaration_start, declaration_end = _find_declaration(
        content, heading.start, section_end, heading_starts
    )
    if role_text is None or declaration_start is None or declaration_end is None:
        return None
    role_token = ROLE_TOKENS.get(role_text)
    if role_token is None:
        return None
    heading_evidence = build_evidence(snapshot, heading.start, heading.end)
    declaration_evidence = build_evidence(snapshot, declaration_start, declaration_end)
    if not verify_evidence(snapshot, heading_evidence):
        return None
    if not verify_evidence(snapshot, declaration_evidence):
        return None
    clauses = _classify_clauses(
        snapshot, content, heading.start, section_end, heading_starts, declaration_start
    )
    section_byte_start = len(content[: heading.start].encode("utf-8"))
    section_byte_end = len(content[:section_end].encode("utf-8"))
    return PolicySection(
        scope_id=_scope_id(
            snapshot,
            heading_path,
            parent.text,
            role_token,
            section_byte_start,
            section_byte_end,
        ),
        program_text=parent.text,
        role_text=role_text,
        role_token=role_token,
        policy_heading=POLICY_HEADING,
        heading_path=heading_path,
        heading_evidence=heading_evidence,
        declaration_evidence=declaration_evidence,
        section_char_start=heading.start,
        section_char_end=section_end,
        section_byte_start=section_byte_start,
        section_byte_end=section_byte_end,
        section_sha256=hashlib.sha256(content[heading.start:section_end].encode("utf-8")).hexdigest(),
        clauses=clauses,
        supported=True,
        reason=None,
    )


def find_policy_sections(
    snapshot: DocumentSnapshot, new: DocumentSnapshot | None = None
) -> tuple[PolicySection, ...]:
    """Find supported document-level policy sections.

    ``find_policy_sections(new)`` and ``find_policy_sections(old, new)`` are
    both accepted; the latter uses ``new`` as the target.
    """
    target = new if new is not None else snapshot
    if not target.is_readable or target.content is None:
        return ()
    content = target.content
    headings = _headings(content)
    sections = []
    for index, heading in enumerate(headings):
        if heading.text != POLICY_HEADING:
            continue
        section = _build_section(target, headings, index, content)
        if section is not None:
            sections.append(section)
    return tuple(sections)


def _start_candidates(content: str, heading_start: int):
    yield heading_start
    index = heading_start
    while index > 0 and content[index - 1] in " \t\r\n":
        index -= 1
        if index == 0 or content[index - 1] in "\r\n":
            yield index


def _lv(
    status: str,
    reason: str | None,
    evidence_status: str,
    section: PolicySection | None = None,
    *,
    remainder_sha256: str | None = None,
    block_char_start: int | None = None,
    block_char_end: int | None = None,
    old: DocumentSnapshot | None = None,
    new: DocumentSnapshot | None = None,
) -> dict:
    return {
        "kind": "LOCAL_SECTION_ADDITION",
        "status": status,
        "reason": reason,
        "evidence_status": evidence_status,
        "scope_id": section.scope_id if section else None,
        "section_sha256": section.section_sha256 if section else None,
        "old_sha256": old.sha256 if old else None,
        "new_sha256": new.sha256 if new else None,
        "remainder_sha256": remainder_sha256,
        "block_char_start": block_char_start,
        "block_char_end": block_char_end,
        "block_byte_start": (
            len(new.content[:block_char_start].encode("utf-8"))
            if new is not None and new.content is not None and block_char_start is not None
            else None
        ),
        "block_byte_end": (
            len(new.content[:block_char_end].encode("utf-8"))
            if new is not None and new.content is not None and block_char_end is not None
            else None
        ),
    }


def validate_local_section_addition(
    section: PolicySection,
    old: DocumentSnapshot,
    new: DocumentSnapshot,
) -> dict:
    """Strict proof that ``section`` is a contiguous local addition.

    Returns a JSON-native dict with status VERIFIED / NOT_VERIFIED. Any failure
    means no deterministic applicability/action may be produced.
    """
    if (
        not old.is_readable
        or not new.is_readable
        or old.role != "old"
        or new.role != "new"
        or old.content is None
        or new.content is None
    ):
        return _lv("NOT_VERIFIED", "UNREADABLE", "UNVERIFIED", section, old=old, new=new)
    if not section.supported:
        return _lv("NOT_VERIFIED", "SECTION_UNSUPPORTED", "UNVERIFIED", section, old=old, new=new)

    sections = find_policy_sections(new)
    same_path = [s for s in sections if s.heading_path == section.heading_path]
    if len(same_path) > 1:
        return _lv("NOT_VERIFIED", "DUPLICATE_SECTION", "VERIFIED", section, old=old, new=new)

    try:
        for evidence in (section.heading_evidence, section.declaration_evidence):
            if not verify_evidence(new, evidence):
                raise ValueError("scope evidence invalid")
        for clause in section.clauses:
            if not verify_evidence(new, clause.evidence):
                raise ValueError("clause evidence invalid")
    except (ValueError, TypeError):
        return _lv("NOT_VERIFIED", "EVIDENCE_INVALID", "UNVERIFIED", section, old=old, new=new)

    old_sections = find_policy_sections(old)
    if old.content == new.content and any(
        s.heading_path == section.heading_path
        and s.section_char_start == section.section_char_start
        and s.section_char_end == section.section_char_end
        for s in old_sections
    ):
        return _lv("NOT_VERIFIED", "OLD_CONTAINS_SECTION", "VERIFIED", section, old=old, new=new)

    end = section.section_char_end
    for start in _start_candidates(new.content, section.section_char_start):
        block = new.content[start:end]
        if section.heading_evidence.quote not in block:
            continue
        remainder = new.content[:start] + new.content[end:]
        if remainder == old.content:
            return _lv(
                "VERIFIED",
                None,
                "VERIFIED",
                section,
                remainder_sha256=hashlib.sha256(remainder.encode("utf-8")).hexdigest(),
                block_char_start=start,
                block_char_end=end,
                old=old,
                new=new,
            )
    return _lv("NOT_VERIFIED", "REMAINDER_CHANGED", "VERIFIED", section, old=old, new=new)
