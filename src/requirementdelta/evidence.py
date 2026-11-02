"""Exact evidence location over readable document snapshots.

Evidence is always a slice of the original decoded content, never a normalised
or rewritten sentence. Line numbers are 1-based inclusive; character and byte
ranges are 0-based half-open. Byte ranges index the raw file bytes, which
round-trip exactly because ingestion only accepts strict UTF-8. CRLF, CR, LF,
BOMs, and CJK text are preserved.

A quote that occurs more than once is rejected as ambiguous: the module never
guesses which occurrence the caller meant. Empty, out-of-range, unreadable, and
invalid-role inputs are rejected.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .ingest import DocumentSnapshot, VALID_ROLES

_LINE_BREAK = re.compile(r"\r\n|\r|\n")


class EvidenceError(Exception):
    """Base class for evidence-location failures."""


class UnreadableSnapshotError(EvidenceError):
    """Raised when evidence is requested from a non-readable snapshot."""

    def __init__(self, snapshot: DocumentSnapshot) -> None:
        self.status = snapshot.status
        self.error_code = snapshot.error_code
        super().__init__(
            "snapshot is not readable "
            f"(status={snapshot.status}, error_code={snapshot.error_code})"
        )


class InvalidSpanError(EvidenceError, ValueError):
    """Raised for empty, reversed, negative, or out-of-range spans."""


class InvalidQuoteError(EvidenceError, ValueError):
    """Raised when a quote is not a non-empty string."""


class EmptyQuoteError(InvalidQuoteError):
    """Raised when an empty quote is supplied."""


class QuoteNotFoundError(EvidenceError):
    """Raised when a quote does not occur verbatim in the snapshot."""


class AmbiguousQuoteError(EvidenceError):
    """Raised when a quote occurs multiple times; no occurrence is guessed."""

    def __init__(self, quote: str, occurrences: int) -> None:
        self.quote = quote
        self.occurrences = occurrences
        super().__init__(
            f"quote occurs {occurrences} times; refusing to guess a location"
        )


@dataclass(frozen=True)
class Evidence:
    """A verified, exactly located slice of one document snapshot."""

    role: str
    path: str
    doc_sha256: str
    line_start: int
    line_end: int
    char_start: int
    char_end: int
    byte_start: int
    byte_end: int
    quote: str

    def __post_init__(self) -> None:
        offsets = (self.line_start, self.line_end, self.char_start, self.char_end,
                   self.byte_start, self.byte_end)
        if any(type(value) is not int for value in offsets):
            raise ValueError("evidence line numbers and offsets must be integers")
        if self.role not in VALID_ROLES:
            raise ValueError(f"role must be one of {sorted(VALID_ROLES)}, got {self.role!r}")
        if not isinstance(self.quote, str) or self.quote == "":
            raise ValueError("evidence quote must be a non-empty string")
        if self.line_start < 1 or self.line_end < self.line_start:
            raise ValueError("line numbers are 1-based inclusive; end must be >= start")
        if self.char_start < 0 or self.char_end <= self.char_start:
            raise ValueError("character range must be a non-empty 0-based half-open span")
        if self.byte_start < 0 or self.byte_end <= self.byte_start:
            raise ValueError("byte range must be a non-empty 0-based half-open span")
        if not self.path or not self.doc_sha256:
            raise ValueError("evidence requires the source path and document SHA-256")


def build_evidence(
    snapshot: DocumentSnapshot, char_start: int, char_end: int
) -> Evidence:
    """Build evidence from an explicit character span.

    The span is validated against the snapshot content, then line numbers and
    UTF-8 byte offsets are derived from the original text. The quote is the
    exact slice ``content[char_start:char_end]``.
    """
    content = _readable_content(snapshot)
    if (
        isinstance(char_start, bool)
        or isinstance(char_end, bool)
        or not isinstance(char_start, int)
        or not isinstance(char_end, int)
    ):
        raise InvalidSpanError("span offsets must be integers")
    if char_start < 0 or char_end <= char_start or char_end > len(content):
        raise InvalidSpanError(
            f"span [{char_start}, {char_end}) is outside content length {len(content)}"
        )

    quote = content[char_start:char_end]
    line_start = _line_number_at(content, char_start)
    line_end = _line_number_at(content, char_end - 1)
    byte_start = len(content[:char_start].encode("utf-8"))
    byte_end = len(content[:char_end].encode("utf-8"))

    return Evidence(
        role=snapshot.role,
        path=snapshot.path,
        doc_sha256=snapshot.sha256 or "",
        line_start=line_start,
        line_end=line_end,
        char_start=char_start,
        char_end=char_end,
        byte_start=byte_start,
        byte_end=byte_end,
        quote=quote,
    )


def locate_quote(snapshot: DocumentSnapshot, quote: str) -> Evidence:
    """Locate a quote that occurs exactly once, verbatim, in the snapshot.

    Duplicate quotes raise ``AmbiguousQuoteError`` rather than picking the first
    match. Missing quotes raise ``QuoteNotFoundError``. No normalisation of any
    kind is applied.
    """
    content = _readable_content(snapshot)
    if not isinstance(quote, str):
        raise InvalidQuoteError("quote must be a string")
    if quote == "":
        raise EmptyQuoteError("quote must be non-empty")

    positions = _occurrences(content, quote)
    if not positions:
        raise QuoteNotFoundError(f"quote not found verbatim: {quote!r}")
    if len(positions) > 1:
        raise AmbiguousQuoteError(quote, len(positions))
    return build_evidence(snapshot, positions[0], positions[0] + len(quote))


def verify_evidence(snapshot: DocumentSnapshot, evidence: Evidence) -> bool:
    """Return True only if the evidence still matches the snapshot exactly."""
    if not isinstance(snapshot, DocumentSnapshot) or not isinstance(evidence, Evidence):
        return False
    if not snapshot.is_readable or snapshot.content is None or snapshot.sha256 is None:
        return False
    if (evidence.role, evidence.path, evidence.doc_sha256) != (
        snapshot.role,
        snapshot.path,
        snapshot.sha256,
    ):
        return False
    content = snapshot.content
    if (
        evidence.char_start < 0
        or evidence.char_end > len(content)
        or evidence.char_end <= evidence.char_start
    ):
        return False
    if content[evidence.char_start:evidence.char_end] != evidence.quote:
        return False
    try:
        expected = build_evidence(snapshot, evidence.char_start, evidence.char_end)
    except (EvidenceError, ValueError):
        return False
    return (
        evidence.line_start,
        evidence.line_end,
        evidence.byte_start,
        evidence.byte_end,
    ) == (
        expected.line_start,
        expected.line_end,
        expected.byte_start,
        expected.byte_end,
    )


def _readable_content(snapshot: DocumentSnapshot) -> str:
    if not isinstance(snapshot, DocumentSnapshot):
        raise TypeError(f"expected DocumentSnapshot, got {type(snapshot).__name__}")
    if not snapshot.is_readable or snapshot.content is None:
        raise UnreadableSnapshotError(snapshot)
    return snapshot.content


def _occurrences(content: str, quote: str) -> list[int]:
    positions: list[int] = []
    start = content.find(quote)
    while start != -1:
        positions.append(start)
        start = content.find(quote, start + 1)
    return positions


def _line_number_at(content: str, index: int) -> int:
    """1-based line number of the character at ``index``.

    Only CRLF, CR, and LF are line breaks. A CRLF belongs to the line it
    terminates, so a quote ending with CRLF still ends on that line.
    """
    if index < 0 or index >= len(content):
        raise InvalidSpanError(f"character index {index} is outside content")
    prefix = content[:index]
    if prefix.endswith("\r") and content[index] == "\n":
        prefix = prefix[:-1]
    return 1 + len(_LINE_BREAK.findall(prefix))
