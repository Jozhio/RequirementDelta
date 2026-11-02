# Usage

## 1. Requirements

- Windows 10/11 (initial supported platform).
- Python 3.11 or newer.
- UTF-8 encoded local `.txt` or `.md` files.

The runtime uses the Python standard library. No network connection or paid API is required.

## 2. Install

From the repository root:

```powershell
py -3.11 -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
python -m pip install .
```

For development:

```powershell
python -m pip install -e ".[test]"
```

## 3. Compare two versions

```powershell
requirementdelta analyze `
  --old .\\examples\\old.md `
  --new .\\examples\\new.md `
  --output .\\out\\demo
```

The CLI creates:
- `report.json`
- `report.md`

The output directory is created if needed. If either report already exists, the command refuses to overwrite it unless `--overwrite` is explicitly supplied.

The source launcher is also available:

```powershell
python .\\scripts\\run_cli.py analyze `
  --old .\\examples\\old.md `
  --new .\\examples\\new.md `
  --output .\\out\\demo
```

## 4. Parameters

| Parameter | Required | Description |
|---|---|---|
| `--old` | Yes | Old local TXT/Markdown file |
| `--new` | Yes | New local TXT/Markdown file |
| `--output` | Yes | Output directory for JSON and Markdown reports |
| `--context` | No | User-confirmed context JSON using schema 0.3 or 0.4 |
| `--allowed-root` | No | Explicit allowed root for input containment; defaults to the common parent directory |
| `--overwrite` | No | Explicitly allow replacing existing reports |
| `--quiet` | No | Suppress the console summary |

## 5. Context schema 0.3: project/task context

Use schema 0.3 for supported project-level or task-level conditions.

```json
{
  "schema_version": "0.3",
  "confirmed_by_user": true,
  "facts": [
    {"field": "project", "value": "Example Project"},
    {"field": "participating", "value": true}
  ],
  "completed_tasks": [],
  "pending_tasks": []
}
```

Only include facts that the user has explicitly confirmed. Missing facts are not treated as false.

## 6. Context schema 0.4: document-level policy context

Use schema 0.4 for the limited document-level policy rules implemented by RequirementDelta.

```json
{
  "schema_version": "0.4",
  "confirmed_by_user": true,
  "program": "Applying to Example Summer of Code",
  "role": null,
  "facts": [
    {"field": "participating", "value": true},
    {"field": "condition:uses_ai_for_code", "value": true},
    {"field": "condition:uses_ai_for_comments", "value": false}
  ],
  "completed_tasks": [],
  "pending_tasks": []
}
```

The `program` value must exactly match the supported document heading. Abbreviations and aliases are not silently treated as equivalent. Missing or ambiguous context must remain unresolved.

## 7. Exit codes

| Code | Meaning |
|---:|---|
| 0 | Report successfully generated; the report may still require human review |
| 2 | Input, path, format, argument, or context error |
| 3 | Internal, evidence, write, or concurrent-input-change error |

An exit code of 0 does not mean the document is legally compliant or that all requirements are understood.

## 8. Report interpretation

- `REVIEW_REQUIRED`: a change or unresolved item needs human review.
- `UNVERIFIED`: one or more inputs/evidence could not be verified. Do not read this as “no change”.
- `NEEDS_CONFIRMATION`: user context is incomplete or does not match an exact supported scope.
- `INSUFFICIENT_CONTEXT`: the tool cannot decide applicability from the available facts.
- `DOES_NOT_APPLY`: only a specific supported condition was determined not to apply; it is not a universal eligibility decision.

Read the evidence quotes, source positions, hashes, warnings, and limitations before acting.

## 9. Troubleshooting

- If Python is not found, install Python 3.11+ and ensure the Python launcher or executable is available.
- If the console command is not found after installation, activate the virtual environment or use the source launcher.
- If an output already exists, choose a new output directory or explicitly use `--overwrite` after checking the existing files.
- If input is missing, unreadable, unsupported, or invalid UTF-8, correct the input. Do not treat the result as no change.
