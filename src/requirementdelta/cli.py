"""0.1.0 command-line entry point.

Read-only inputs, no network, no execution of document content. Writes only
report.json and report.md in the explicitly selected output directory.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from .ingest import DocumentSnapshot, read_pair
from .policy_context import PolicyContext
from .report import render_markdown
from .task_context import UserTaskContext
from .workflow import (
    OVERALL_UNVERIFIED,
    build_error_report,
    build_report,
)

EXIT_OK = 0
EXIT_INPUT = 2
EXIT_INTERNAL = 3
MAX_CONTEXT_BYTES = 1_048_576


class CliError(Exception):
    def __init__(self, message: str, code: int = EXIT_INPUT):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class CliPaths:
    old_path: Path
    new_path: Path
    allowed_root: Path
    output_dir: Path
    report_json: Path
    report_md: Path
    context_path: Path | None


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _path_key(path: Path) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


def _same_path(left: Path, right: Path) -> bool:
    return _path_key(left) == _path_key(right)


def _common_root(old_path: Path, new_path: Path) -> Path:
    try:
        common = os.path.commonpath([str(old_path.parent), str(new_path.parent)])
    except ValueError as exc:
        raise CliError("old and new files are on different drives; provide --allowed-root") from exc
    root = Path(common).resolve(strict=False)
    if not root.is_dir():
        raise CliError(f"allowed root is not an existing directory: {root}")
    return root


def _resolve_output(args) -> tuple[Path, Path, Path]:
    output = Path(args.output).expanduser().resolve(strict=False)
    if output.exists() and not output.is_dir():
        raise CliError(f"output path exists and is not a directory: {output}")
    report_json = output / "report.json"
    report_md = output / "report.md"
    if not args.overwrite:
        for path in (report_json, report_md):
            if path.exists():
                raise CliError(
                    f"refusing to overwrite existing report: {path}; use --overwrite"
                )
    return output, report_json, report_md


def _resolve_paths(args) -> CliPaths:
    old_path = Path(args.old).expanduser().resolve(strict=False)
    new_path = Path(args.new).expanduser().resolve(strict=False)
    context_path = (
        Path(args.context).expanduser().resolve(strict=False)
        if args.context
        else None
    )
    if args.allowed_root:
        root = Path(args.allowed_root).expanduser().resolve(strict=False)
        if not root.is_dir():
            raise CliError(f"allowed root is not an existing directory: {root}")
    else:
        root = _common_root(old_path, new_path)
    output_dir, report_json, report_md = _resolve_output(args)

    protected = {_path_key(old_path), _path_key(new_path)}
    if context_path is not None:
        protected.add(_path_key(context_path))
    if _path_key(output_dir) in protected:
        raise CliError("output directory conflicts with an input file")
    for target in (report_json, report_md):
        if _path_key(target) in protected:
            raise CliError(f"report path conflicts with an input file: {target}")
    return CliPaths(
        old_path=old_path,
        new_path=new_path,
        allowed_root=root,
        output_dir=output_dir,
        report_json=report_json,
        report_md=report_md,
        context_path=context_path,
    )


def _read_context(path: Path):
    try:
        if not path.is_file():
            raise CliError(f"context file does not exist or is not a regular file: {path}")
        raw = path.read_bytes()
    except OSError as exc:
        raise CliError(f"cannot read context file: {exc}") from exc
    if len(raw) > MAX_CONTEXT_BYTES:
        raise CliError(f"context file exceeds {MAX_CONTEXT_BYTES} bytes")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise CliError(f"context file is not valid UTF-8: {exc}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CliError(f"context file is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise CliError("context JSON must be an object")
    schema = data.get("schema_version")
    try:
        if schema == "0.3":
            return UserTaskContext.from_dict(data), "0.3"
        if schema == "0.4":
            return PolicyContext.from_dict(data), "0.4"
        raise CliError("context schema_version must be 0.3 or 0.4")
    except CliError:
        raise
    except (ValueError, TypeError) as exc:
        raise CliError(f"invalid context: {exc}") from exc


def _read_inputs(paths: CliPaths) -> tuple[DocumentSnapshot, DocumentSnapshot]:
    try:
        return read_pair(paths.old_path, paths.new_path, paths.allowed_root)
    except (ValueError, OSError) as exc:
        raise CliError(f"cannot read input documents: {exc}") from exc


def _verify_inputs(
    paths: CliPaths, old: DocumentSnapshot, new: DocumentSnapshot
) -> bool:
    try:
        fresh_old, fresh_new = read_pair(
            paths.old_path, paths.new_path, paths.allowed_root
        )
    except (ValueError, OSError):
        return False
    return (
        fresh_old.is_readable
        and fresh_new.is_readable
        and fresh_old.sha256 == old.sha256
        and fresh_new.sha256 == new.sha256
    )


def _set_read_only(report: dict, unchanged: bool | None, checked: bool) -> None:
    report["read_only"] = {
        "inputs_unchanged": unchanged,
        "checked": checked,
    }


def _atomic_write_pair(
    report: dict,
    paths: CliPaths,
    *,
    overwrite: bool,
    inputs_readable: bool,
    old: DocumentSnapshot | None,
    new: DocumentSnapshot | None,
) -> int:
    paths.output_dir.mkdir(parents=True, exist_ok=True)
    for target in (paths.report_json, paths.report_md):
        if target.exists() and not overwrite:
            raise CliError(f"refusing to overwrite existing report: {target}")
        if target.exists() and target.is_dir():
            raise CliError(f"report path is a directory: {target}")

    if inputs_readable and old is not None and new is not None:
        unchanged = _verify_inputs(paths, old, new)
        _set_read_only(report, unchanged, True)
        if not unchanged:
            report["summary"]["overall_status"] = OVERALL_UNVERIFIED
            report["warnings"].append(
                "Input files changed while the report was being generated; this report is not valid."
            )
    else:
        _set_read_only(report, None, False)

    json_text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    md_text = render_markdown(report)
    json_tmp = paths.report_json.with_name(paths.report_json.name + f".tmp-{os.getpid()}")
    md_tmp = paths.report_md.with_name(paths.report_md.name + f".tmp-{os.getpid()}")
    try:
        json_tmp.write_text(json_text, encoding="utf-8", newline="\n")
        md_tmp.write_text(md_text, encoding="utf-8", newline="\n")
        if inputs_readable and old is not None and new is not None:
            if not _verify_inputs(paths, old, new):
                raise CliError(
                    "Input files changed after report generation; refusing to publish a stale report.",
                    EXIT_INTERNAL,
                )
        if paths.report_json.exists() or paths.report_md.exists():
            if not overwrite:
                raise CliError(
                    "Refusing to overwrite an existing report created concurrently.",
                    EXIT_INPUT,
                )
        os.replace(json_tmp, paths.report_json)
        os.replace(md_tmp, paths.report_md)
        return EXIT_OK
    except OSError as exc:
        raise CliError(f"cannot write report: {exc}", EXIT_INTERNAL) from exc
    finally:
        for temp in (json_tmp, md_tmp):
            try:
                if temp.exists():
                    temp.unlink()
            except OSError:
                pass


def _summary_lines(report: dict, paths: CliPaths) -> list[str]:
    summary = report["summary"]
    lines = [
        "RequirementDelta 0.1.0",
        f"old: {report['inputs']['old']['status']} sha256={str(report['inputs']['old']['sha256'])[:16]}…",
        f"new: {report['inputs']['new']['status']} sha256={str(report['inputs']['new']['sha256'])[:16]}…",
        f"context: {report['run']['context_schema'] or 'not provided'}",
        f"changes: {summary['changes_total']} "
        f"(CHANGED {summary['changes_changed']}, UNKNOWN {summary['changes_unknown']})",
        f"assessments: {summary['assessments_total']} "
        + ", ".join(
            f"{key}={value}" for key, value in summary["applicability_counts"].items()
        ),
        f"overall: {summary['overall_status']}",
        f"reports: {paths.report_json}",
        f"         {paths.report_md}",
    ]
    for error in report.get("errors") or []:
        lines.append(f"error: {error}")
    return lines


def _run_analyze(args) -> int:
    paths = _resolve_paths(args)
    old, new = _read_inputs(paths)

    context = None
    context_error = None
    if paths.context_path is not None:
        try:
            context, _schema = _read_context(paths.context_path)
        except CliError as exc:
            context_error = str(exc)

    if not old.is_readable or not new.is_readable:
        message = (
            "Input document read failed: "
            f"old={old.status}/{old.error_code}, new={new.status}/{new.error_code}. "
            "No change judgment is possible."
        )
        report = build_error_report(old, new, message)
        _atomic_write_pair(
            report,
            paths,
            overwrite=args.overwrite,
            inputs_readable=False,
            old=old,
            new=new,
        )
        if not args.quiet:
            print("\n".join(_summary_lines(report, paths)))
        return EXIT_INPUT

    if context_error is not None:
        report = build_error_report(
            old,
            new,
            "User context is invalid; applicability was not assessed.",
            context_error=context_error,
        )
        _atomic_write_pair(
            report,
            paths,
            overwrite=args.overwrite,
            inputs_readable=True,
            old=old,
            new=new,
        )
        if not args.quiet:
            print("\n".join(_summary_lines(report, paths)))
        return EXIT_INPUT

    try:
        report = build_report(old, new, context)
    except Exception as exc:  # fail closed, never produce a false no-change report
        report = build_error_report(
            old,
            new,
            f"Internal analysis error: {exc}",
        )
        _atomic_write_pair(
            report,
            paths,
            overwrite=args.overwrite,
            inputs_readable=True,
            old=old,
            new=new,
        )
        if not args.quiet:
            print("\n".join(_summary_lines(report, paths)))
        return EXIT_INTERNAL

    write_code = _atomic_write_pair(
        report,
        paths,
        overwrite=args.overwrite,
        inputs_readable=True,
        old=old,
        new=new,
    )
    if write_code != EXIT_OK:
        return write_code
    if report["summary"]["overall_status"] == OVERALL_UNVERIFIED:
        exit_code = EXIT_INTERNAL
    else:
        exit_code = EXIT_OK
    if not args.quiet:
        print("\n".join(_summary_lines(report, paths)))
    return exit_code


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="requirementdelta",
        description="RequirementDelta 0.1.0: local, read-only text requirement change review.",
    )
    parser.add_argument("--version", action="version", version="RequirementDelta 0.1.0")
    subparsers = parser.add_subparsers(dest="command", required=True)
    analyze = subparsers.add_parser(
        "analyze",
        help="compare two UTF-8 .txt/.md files and write report.json + report.md",
    )
    analyze.add_argument("--old", required=True, help="old requirement file (.txt/.md)")
    analyze.add_argument("--new", required=True, help="new requirement file (.txt/.md)")
    analyze.add_argument("--context", help="optional 0.3 UserTaskContext or 0.4 PolicyContext JSON")
    analyze.add_argument("--output", required=True, help="output directory for report.json/report.md")
    analyze.add_argument(
        "--allowed-root",
        help="explicit root for old/new input containment; defaults to their common parent",
    )
    analyze.add_argument(
        "--overwrite",
        action="store_true",
        help="allow replacing existing report.json/report.md",
    )
    analyze.add_argument("--quiet", action="store_true", help="suppress the console summary")
    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command != "analyze":
        parser.error("unknown command")
    try:
        return _run_analyze(args)
    except CliError as exc:
        print(f"requirementdelta: {exc}", file=sys.stderr)
        return exc.code
    except Exception as exc:  # pragma: no cover - last-resort fail closed
        print(f"requirementdelta: internal error: {exc}", file=sys.stderr)
        return EXIT_INTERNAL


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
