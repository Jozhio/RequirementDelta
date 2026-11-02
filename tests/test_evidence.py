"""P0-1 evidence contract: exact source slices, 1-based lines, 0-based half-open spans."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from requirementdelta.evidence import (
    AmbiguousQuoteError,
    EmptyQuoteError,
    InvalidSpanError,
    QuoteNotFoundError,
    UnreadableSnapshotError,
    build_evidence,
    locate_quote,
    verify_evidence,
)
from requirementdelta.ingest import read_document

CONTENT = "﻿第一行\r\n第二行：申请截止 2026-12-08\r第三行\n第四行 café"


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    allowed = tmp_path / "root"
    allowed.mkdir()
    return allowed


def snapshot_for(root: Path, name: str, text: str):
    target = root / name
    target.write_bytes(text.encode("utf-8"))
    return read_document(name, "old", root)


def test_locate_quote_records_exact_source_spans(root: Path) -> None:
    snapshot = snapshot_for(root, "doc.md", CONTENT)
    quote = "申请截止 2026-12-08"
    start = CONTENT.index(quote)

    evidence = locate_quote(snapshot, quote)

    assert evidence.role == "old"
    assert Path(evidence.path).resolve() == Path(snapshot.path).resolve()
    assert evidence.doc_sha256 == snapshot.sha256
    assert evidence.line_start == 2
    assert evidence.line_end == 2
    assert evidence.char_start == start
    assert evidence.char_end == start + len(quote)
    assert evidence.byte_start == len(CONTENT[:start].encode("utf-8"))
    assert evidence.byte_end == len(CONTENT[: start + len(quote)].encode("utf-8"))
    assert evidence.quote == CONTENT[evidence.char_start : evidence.char_end]
    raw = (root / "doc.md").read_bytes()
    assert raw[evidence.byte_start : evidence.byte_end] == quote.encode("utf-8")


def test_bom_is_preserved_in_byte_offsets(root: Path) -> None:
    snapshot = snapshot_for(root, "bom.md", CONTENT)
    raw = (root / "bom.md").read_bytes()

    evidence = locate_quote(snapshot, "﻿第一行")

    assert evidence.byte_start == 0
    assert evidence.byte_end == len("﻿第一行".encode("utf-8"))
    assert raw[0:3] == b"\xef\xbb\xbf"
    assert raw[evidence.byte_start : evidence.byte_end] == "﻿第一行".encode("utf-8")
    assert evidence.line_start == evidence.line_end == 1


def test_crlf_span_maps_to_inclusive_lines_and_raw_bytes(root: Path) -> None:
    snapshot = snapshot_for(root, "crlf.md", CONTENT)
    quote = "第一行\r\n第二行"
    raw = (root / "crlf.md").read_bytes()

    evidence = locate_quote(snapshot, quote)

    assert (evidence.line_start, evidence.line_end) == (1, 2)
    assert raw[evidence.byte_start : evidence.byte_end] == quote.encode("utf-8")
    assert evidence.byte_end - evidence.byte_start == len(quote.encode("utf-8"))


def test_cr_only_and_lf_line_breaks(root: Path) -> None:
    snapshot = snapshot_for(root, "mixed.md", CONTENT)

    cr_quote = locate_quote(snapshot, "2026-12-08\r第三行")
    lf_quote = locate_quote(snapshot, "第三行\n第四行")

    assert (cr_quote.line_start, cr_quote.line_end) == (2, 3)
    assert (lf_quote.line_start, lf_quote.line_end) == (3, 4)


def test_quote_ending_with_crlf_stays_on_first_line(root: Path) -> None:
    snapshot = snapshot_for(root, "trailing.md", CONTENT)

    evidence = locate_quote(snapshot, "第一行\r\n")

    assert (evidence.line_start, evidence.line_end) == (1, 1)


@pytest.mark.parametrize(
    ("quote", "line"),
    [("第一行", 1), ("第二行", 2), ("第三行", 3), ("第四行", 4)],
)
def test_line_numbers_are_one_based(root: Path, quote: str, line: int) -> None:
    snapshot = snapshot_for(root, "lines.md", CONTENT)

    evidence = locate_quote(snapshot, quote)

    assert evidence.line_start == evidence.line_end == line


def test_empty_file_is_readable_but_yields_no_evidence(root: Path) -> None:
    snapshot = snapshot_for(root, "empty.txt", "")

    with pytest.raises(EmptyQuoteError):
        locate_quote(snapshot, "")
    with pytest.raises(QuoteNotFoundError):
        locate_quote(snapshot, "anything")
    with pytest.raises(InvalidSpanError):
        build_evidence(snapshot, 0, 0)
    with pytest.raises(InvalidSpanError):
        build_evidence(snapshot, 0, 1)


def test_out_of_bounds_and_reversed_spans_are_rejected(root: Path) -> None:
    snapshot = snapshot_for(root, "spans.txt", "abc")

    for start, end in [(-1, 1), (0, 4), (2, 2), (3, 2), (0, 0)]:
        with pytest.raises(InvalidSpanError):
            build_evidence(snapshot, start, end)


def test_unreadable_snapshot_is_rejected_by_evidence(root: Path) -> None:
    snapshot = read_document("missing.txt", "new", root)

    with pytest.raises(UnreadableSnapshotError) as locate_error:
        locate_quote(snapshot, "x")
    with pytest.raises(UnreadableSnapshotError) as build_error:
        build_evidence(snapshot, 0, 1)

    assert locate_error.value.error_code == "FILE_NOT_FOUND"
    assert build_error.value.error_code == "FILE_NOT_FOUND"


def test_repeated_quote_is_ambiguous_and_never_guessed(root: Path) -> None:
    snapshot = snapshot_for(root, "repeat.md", "重复\n重复\n唯一\n")

    with pytest.raises(AmbiguousQuoteError) as excinfo:
        locate_quote(snapshot, "重复")

    assert excinfo.value.occurrences == 2
    unique = locate_quote(snapshot, "唯一")
    assert (unique.line_start, unique.line_end) == (3, 3)


def test_no_unicode_or_whitespace_normalisation(root: Path) -> None:
    snapshot = snapshot_for(root, "normalise.md", "café  and  spaced")

    decomposed = locate_quote(snapshot, "é")
    assert decomposed.quote == "é"

    with pytest.raises(QuoteNotFoundError):
        locate_quote(snapshot, "é")
    with pytest.raises(QuoteNotFoundError):
        locate_quote(snapshot, "and spaced")


def test_verify_evidence_detects_tampering(root: Path) -> None:
    snapshot = snapshot_for(root, "verify.md", CONTENT)
    evidence = locate_quote(snapshot, "第四行")

    assert verify_evidence(snapshot, evidence) is True
    assert verify_evidence(snapshot, replace(evidence, quote="篡改")) is False
    assert verify_evidence(snapshot, replace(evidence, char_start=0)) is False
    assert verify_evidence(read_document("absent.md", "old", root), evidence) is False


def test_invalid_evidence_role_is_rejected(root: Path) -> None:
    snapshot = snapshot_for(root, "role.md", CONTENT)
    evidence = locate_quote(snapshot, "第四行")

    with pytest.raises(ValueError):
        replace(evidence, role="third")
