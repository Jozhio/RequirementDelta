"""P0-1 ingestion contract: roles, raw-byte SHA-256, strict UTF-8, read-only snapshots."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from requirementdelta.ingest import (
    FILE_NOT_FOUND,
    INVALID_UTF8,
    NOT_A_FILE,
    PERMISSION_DENIED,
    READ_ERROR,
    READABLE,
    UNSUPPORTED_FORMAT,
    DocumentSnapshot,
    read_document,
    read_pair,
)

RAW_MIXED = "﻿第一行\r\n第二行\n第三行\r第四行 café é".encode("utf-8")


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    allowed = tmp_path / "root"
    allowed.mkdir()
    return allowed


def write(root: Path, name: str, data: bytes) -> Path:
    target = root / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return target


def test_reads_txt_and_preserves_raw_bytes(root: Path) -> None:
    target = write(root, "notice.txt", RAW_MIXED)

    snapshot = read_document("notice.txt", "old", root)

    assert snapshot.status == READABLE
    assert snapshot.role == "old"
    assert Path(snapshot.path).resolve() == target.resolve()
    assert snapshot.sha256 == hashlib.sha256(RAW_MIXED).hexdigest()
    assert snapshot.content == RAW_MIXED.decode("utf-8")
    assert snapshot.is_readable is True
    assert snapshot.is_unverified is False
    assert snapshot.verification_status == "READABLE"
    assert snapshot.error_code is None
    assert snapshot.error_message is None


def test_markdown_and_uppercase_suffix_are_supported(root: Path) -> None:
    write(root, "GUIDE.MD", "# 标题\n正文\n".encode("utf-8"))

    snapshot = read_document("GUIDE.MD", "new", root)

    assert snapshot.status == READABLE


def test_empty_file_is_readable_with_empty_content(root: Path) -> None:
    write(root, "empty.txt", b"")

    snapshot = read_document("empty.txt", "new", root)

    assert snapshot.status == READABLE
    assert snapshot.content == ""
    assert snapshot.sha256 == hashlib.sha256(b"").hexdigest()


def test_missing_file_is_read_error_unverified(root: Path) -> None:
    snapshot = read_document("missing.txt", "new", root)

    assert snapshot.status == READ_ERROR
    assert snapshot.error_code == FILE_NOT_FOUND
    assert snapshot.verification_status == "UNVERIFIED"
    assert snapshot.is_readable is False
    assert snapshot.is_unverified is True
    assert snapshot.content is None
    assert snapshot.sha256 is None
    assert snapshot.error_message


def test_directory_is_read_error(root: Path) -> None:
    (root / "folder.txt").mkdir()

    snapshot = read_document("folder.txt", "old", root)

    assert snapshot.status == READ_ERROR
    assert snapshot.error_code == NOT_A_FILE
    assert snapshot.verification_status == "UNVERIFIED"


def test_invalid_utf8_is_read_error(root: Path) -> None:
    write(root, "bad.txt", b"valid start\n\xff\xfe invalid tail")

    snapshot = read_document("bad.txt", "new", root)

    assert snapshot.status == READ_ERROR
    assert snapshot.error_code == INVALID_UTF8
    assert snapshot.verification_status == "UNVERIFIED"
    assert snapshot.content is None
    assert snapshot.sha256 is None


def test_pdf_is_unsupported_format_and_never_read(root: Path) -> None:
    write(root, "scan.pdf", b"%PDF-1.4\n% fake scan\n")

    snapshot = read_document("scan.pdf", "new", root)

    assert snapshot.status == UNSUPPORTED_FORMAT
    assert snapshot.error_code == UNSUPPORTED_FORMAT
    assert snapshot.verification_status == "UNVERIFIED"
    assert snapshot.content is None
    assert snapshot.sha256 is None


def test_permission_denied_is_read_error(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write(root, "secret.txt", b"secret")

    def deny(self: Path) -> bytes:
        raise PermissionError(13, "denied by simulated ACL")

    monkeypatch.setattr(Path, "read_bytes", deny)

    snapshot = read_document("secret.txt", "old", root)

    assert snapshot.status == READ_ERROR
    assert snapshot.error_code == PERMISSION_DENIED
    assert snapshot.verification_status == "UNVERIFIED"
    assert snapshot.content is None


def test_invalid_role_is_rejected(root: Path) -> None:
    write(root, "a.txt", b"a")

    with pytest.raises(ValueError):
        read_document("a.txt", "current", root)


def test_missing_allowed_root_is_a_configuration_error(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        read_document("a.txt", "old", tmp_path / "does-not-exist")


def test_absolute_path_inside_root_is_allowed(root: Path) -> None:
    target = write(root, "inside.md", b"# ok\n")

    snapshot = read_document(target.resolve(), "old", root)

    assert snapshot.status == READABLE
    assert Path(snapshot.path).resolve() == target.resolve()


def test_read_pair_assigns_old_and_new_roles(root: Path) -> None:
    write(root, "old.md", "旧版\n".encode("utf-8"))
    write(root, "new.md", "新版\n".encode("utf-8"))

    old, new = read_pair("old.md", "new.md", root)

    assert (old.role, new.role) == ("old", "new")
    assert old.status == READABLE and new.status == READABLE


def test_reading_does_not_modify_source_bytes(root: Path) -> None:
    target = write(root, "source.md", RAW_MIXED)
    before = target.read_bytes()

    first = read_document("source.md", "old", root)
    second = read_document("source.md", "new", root)

    assert target.read_bytes() == before
    assert first.sha256 == second.sha256 == hashlib.sha256(before).hexdigest()


def test_snapshot_rejects_inconsistent_states() -> None:
    with pytest.raises(ValueError):
        DocumentSnapshot(
            role="old",
            path="x.txt",
            status=READ_ERROR,
            sha256=None,
            content=None,
            error_code=None,
        )
    with pytest.raises(ValueError):
        DocumentSnapshot(
            role="old",
            path="x.txt",
            status=READABLE,
            sha256=None,
            content="x",
            error_code=None,
        )
