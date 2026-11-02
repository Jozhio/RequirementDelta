"""Read-only ingestion of local TXT/Markdown requirement documents.

P0-1 stops at snapshots. It never compares documents, never executes document
text, and never touches the network. A snapshot is either ``READABLE`` (strict
UTF-8 content plus the SHA-256 of the raw bytes) or a fail-closed error state
with a machine-readable code. An error state is ``UNVERIFIED`` and must never
be reported as "no change".

All reads are confined to an explicit ``allowed_root``. Relative paths are
resolved against that root; after ``resolve()`` the result must stay inside it.
Parent traversal and symlink escapes are refused. This is a cooperative local
boundary, not an OS sandbox against concurrent path replacement.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from os import PathLike
from pathlib import Path

StrPath = str | PathLike[str]

# Snapshot statuses (read-in only; not a change or action verdict).
READABLE = "READABLE"
UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
READ_ERROR = "READ_ERROR"

# Machine-readable error codes.
FILE_NOT_FOUND = "FILE_NOT_FOUND"
NOT_A_FILE = "NOT_A_FILE"
INVALID_UTF8 = "INVALID_UTF8"
PERMISSION_DENIED = "PERMISSION_DENIED"
IO_ERROR = "IO_ERROR"
PATH_OUTSIDE_ROOT = "PATH_OUTSIDE_ROOT"
SYMLINK_ESCAPE = "SYMLINK_ESCAPE"

SUPPORTED_SUFFIXES = frozenset({".txt", ".md"})
VALID_ROLES = frozenset({"old", "new"})

ERROR_STATUSES = frozenset({UNSUPPORTED_FORMAT, READ_ERROR})


@dataclass(frozen=True)
class DocumentSnapshot:
    """Immutable record of one read attempt.

    ``path`` is the resolved absolute path for auditing. ``sha256`` covers the
    raw bytes exactly as read; ``content`` is the decoded text with no newline,
    BOM, or Unicode normalisation. Only ``READABLE`` snapshots expose content.
    """

    role: str
    path: str
    status: str
    sha256: str | None
    content: str | None
    error_code: str | None = None
    error_message: str | None = None

    def __post_init__(self) -> None:
        if self.role not in VALID_ROLES:
            raise ValueError(f"role must be one of {sorted(VALID_ROLES)}, got {self.role!r}")
        if self.status == READABLE:
            if self.sha256 is None or self.content is None:
                raise ValueError("READABLE snapshot requires sha256 and content")
            if self.error_code is not None or self.error_message is not None:
                raise ValueError("READABLE snapshot cannot carry an error")
            if not isinstance(self.content, str):
                raise ValueError("READABLE content must be UTF-8 text")
            try:
                actual_hash = hashlib.sha256(self.content.encode("utf-8")).hexdigest()
            except UnicodeEncodeError as exc:
                raise ValueError("READABLE content must be valid UTF-8") from exc
            if actual_hash != self.sha256:
                raise ValueError("snapshot SHA-256 does not match content bytes")
        elif self.status in ERROR_STATUSES:
            if self.error_code is None:
                raise ValueError("non-readable snapshot requires a machine error code")
            if self.content is not None or self.sha256 is not None:
                raise ValueError("non-readable snapshot must not expose content or hash")
        else:
            raise ValueError(f"unknown snapshot status {self.status!r}")

    @property
    def is_readable(self) -> bool:
        return self.status == READABLE

    @property
    def is_unverified(self) -> bool:
        return self.status != READABLE

    @property
    def verification_status(self) -> str:
        """``UNVERIFIED`` for every error state; ``READABLE`` claims read-in only."""
        return "UNVERIFIED" if self.is_unverified else READABLE


def read_document(path: StrPath, role: str, allowed_root: StrPath) -> DocumentSnapshot:
    """Read one local document as a snapshot, confined to ``allowed_root``.

    ``role`` must be ``"old"`` or ``"new"``. Invalid roles and invalid roots are
    caller errors and raise ``ValueError``. Document problems are returned as
    snapshots instead, so a caller can report ``UNVERIFIED`` without exception
    handling.
    """
    if role not in VALID_ROLES:
        raise ValueError(f"role must be one of {sorted(VALID_ROLES)}, got {role!r}")
    root = _validated_root(allowed_root)

    raw = Path(path)
    if raw.drive and not raw.is_absolute():
        # Drive-relative paths ("C:file.txt") depend on hidden per-drive state.
        return _error_snapshot(
            role, str(raw), READ_ERROR, PATH_OUTSIDE_ROOT,
            "drive-relative paths are not permitted",
        )

    lexical = raw if raw.is_absolute() else root / raw
    try:
        resolved = lexical.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        return _error_snapshot(
            role, str(lexical), READ_ERROR, IO_ERROR, f"cannot resolve path: {exc}"
        )

    if not _is_within(resolved, root):
        code = SYMLINK_ESCAPE if _lexically_within(lexical, root) else PATH_OUTSIDE_ROOT
        return _error_snapshot(
            role, str(resolved), READ_ERROR, code,
            "resolved path is outside the explicit allowed root",
        )

    try:
        if not resolved.exists():
            return _error_snapshot(
                role, str(resolved), READ_ERROR, FILE_NOT_FOUND, "file does not exist"
            )
        if not resolved.is_file():
            return _error_snapshot(
                role, str(resolved), READ_ERROR, NOT_A_FILE, "path is not a regular file"
            )
    except PermissionError as exc:
        return _error_snapshot(
            role, str(resolved), READ_ERROR, PERMISSION_DENIED, f"cannot stat file: {exc}"
        )
    except OSError as exc:
        return _error_snapshot(
            role, str(resolved), READ_ERROR, IO_ERROR, f"cannot stat file: {exc}"
        )
    if resolved.suffix.lower() not in SUPPORTED_SUFFIXES:
        return _error_snapshot(
            role, str(resolved), UNSUPPORTED_FORMAT, UNSUPPORTED_FORMAT,
            f"unsupported format {resolved.suffix!r}; P0 reads only .txt/.md",
        )

    try:
        raw_bytes = resolved.read_bytes()
    except PermissionError as exc:
        return _error_snapshot(
            role, str(resolved), READ_ERROR, PERMISSION_DENIED, f"permission denied: {exc}"
        )
    except OSError as exc:
        return _error_snapshot(
            role, str(resolved), READ_ERROR, IO_ERROR, f"cannot read file: {exc}"
        )

    try:
        text = raw_bytes.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        return _error_snapshot(
            role, str(resolved), READ_ERROR, INVALID_UTF8,
            f"invalid UTF-8 at byte offset {exc.start}",
        )

    return DocumentSnapshot(
        role=role,
        path=str(resolved),
        status=READABLE,
        sha256=hashlib.sha256(raw_bytes).hexdigest(),
        content=text,
    )


def read_pair(
    old_path: StrPath, new_path: StrPath, allowed_root: StrPath
) -> tuple[DocumentSnapshot, DocumentSnapshot]:
    """Read the old and new documents in one call, preserving role assignment."""
    return (
        read_document(old_path, "old", allowed_root),
        read_document(new_path, "new", allowed_root),
    )


def _validated_root(allowed_root: StrPath) -> Path:
    root = Path(allowed_root)
    try:
        resolved = root.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ValueError(f"allowed_root must exist: {allowed_root!r}") from exc
    if not resolved.is_dir():
        raise ValueError(f"allowed_root must be a directory: {allowed_root!r}")
    return resolved


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _lexically_within(lexical: Path, root: Path) -> bool:
    """Whether the written path is inside root before following any symlink."""
    try:
        Path(os.path.normpath(lexical)).relative_to(root)
    except ValueError:
        return False
    return True


def _error_snapshot(
    role: str, path: str, status: str, code: str, message: str
) -> DocumentSnapshot:
    return DocumentSnapshot(
        role=role,
        path=path,
        status=status,
        sha256=None,
        content=None,
        error_code=code,
        error_message=message,
    )
