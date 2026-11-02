# RequirementDelta

**Local, evidence-traceable review of changes between requirement documents.**

RequirementDelta compares two local versions of a UTF-8 text or Markdown requirement document. It identifies changes within a bounded set of supported rules, preserves the original evidence, and can assess limited applicability when the user explicitly provides supported project or task context.

RequirementDelta is an assistive review tool. It is not a legal, compliance, eligibility, or approval system.

## What it does

- Compare two local UTF-8 `.txt` or `.md` files.
- Preserve old/new source quotes, positions, and SHA-256 hashes for supported changes.
- Apply a limited set of deterministic rules to supported requirement changes.
- Assess selected applicability conditions only when the user supplies explicit context.
- Preserve ambiguity and missing information instead of silently converting them into a negative answer.
- Generate a machine-readable `report.json` and a human-readable `report.md`.
- Run locally without uploading input documents or executing instructions found inside them.

## Status

Version `0.1.0` is the first public-release candidate. It is an early-stage tool with a deliberately narrow scope. Automated tests and developer-run synthetic scenarios are not proof of real-world accuracy or independent user usability.

## Requirements

- Windows 10/11 is the initial supported platform.
- Python 3.11 or newer.
- Runtime uses the Python standard library.
- pytest is required only for development tests.

## Install from a local checkout

From the repository root, create and activate a virtual environment, then install the project:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install .
```

For development and tests:

```powershell
python -m pip install -e ".[test]"
```

## Quick start

The files in `examples/` are fictional synthetic examples.

```powershell
requirementdelta analyze `
  --old .\examples\old.md `
  --new .\examples\new.md `
  --output .\out\demo
```

If the console command is not available in the current environment, the source launcher can be used from the repository root:

```powershell
python .\scripts\run_cli.py analyze `
  --old .\examples\old.md `
  --new .\examples\new.md `
  --output .\out\demo
```

The output directory contains:

```text
out/demo/
  report.json
  report.md
```

By default, existing reports are not overwritten. Use `--overwrite` only when you intentionally want to replace both report files.

## Optional user context

The CLI accepts a JSON context file using one of the supported schemas:

- `0.3`: project/task context.
- `0.4`: document-level policy context.

Example command:

```powershell
requirementdelta analyze `
  --old .\path\old.md `
  --new .\path\new.md `
  --context .\path\context.json `
  --output .\out\review
```

Context must be explicitly confirmed by the user and must match the schema. Missing facts, aliases, ambiguous scopes, and unsupported conditions remain unresolved. Without context, the tool reports changes and evidence but does not infer personal applicability.

See [Usage](docs/USAGE.md) for context examples and parameter details.

## Report status

| Status | Meaning |
|---|---|
| `NO_TEXT_DIFFERENCE` | The decoded input texts are identical; this says nothing about unsupported formats or external versions. |
| `NO_SUPPORTED_CHANGE_FOUND` | No change was confirmed within the implemented rule set; this is not proof that no change exists. |
| `REVIEW_REQUIRED` | A change or unresolved item needs human review. |
| `UNVERIFIED` | An input or evidence could not be verified; never interpret this as “no change” or “safe”. |

Applicability states such as `APPLIES`, `DOES_NOT_APPLY`, `NEEDS_CONFIRMATION`, and `INSUFFICIENT_CONTEXT` must be read together with their evidence and limitations.

## Supported scope and limitations

- Input formats: local UTF-8 `.txt` and `.md` only.
- No PDF, DOCX, scanned documents, OCR, browser monitoring, or URL fetching.
- Change detection uses a bounded rule set; it is not general-purpose semantic understanding.
- Applicability is limited to implemented schemas and supported conditions.
- Complex paraphrases, implicit obligations, unsupported syntax, and ambiguous scope may remain unresolved.
- SHA-256 identifies the bytes read; it does not prove source authenticity or semantic correctness.
- Reports may contain source quotes and local file paths. Review and redact reports before sharing.
- The tool does not submit applications, send messages, or execute recommended actions.

See [Safety and limitations](docs/SAFETY.md).

## Privacy and safety

The core CLI is local and does not need network access. Document content is treated as data, never as executable instructions. Do not put passwords, access tokens, identity numbers, or unnecessary personal information into context files.

The tool is not a substitute for official guidance, professional advice, or human review.

## Agent Skill (Codex and Claude Code)

This repository also includes an instruction-only Agent Skill:

- Canonical package: `skills/requirementdelta/SKILL.md`
- Codex project discovery: `.agents/skills/requirementdelta/SKILL.md`
- Claude Code project discovery: `.claude/skills/requirementdelta/SKILL.md`

The Skill orchestrates the existing local CLI; it does not install the CLI or replace its deterministic rules. Install the Python package first, then use the project-level Skill in the corresponding agent. See [Agent Skill integration](docs/SKILL_INTEGRATION.md).

On one Windows workstation, Codex and Claude Code (configured with a DeepSeek model) have each completed a Skill-guided comparison of the same synthetic Markdown pair, with CLI output and evidence independently checked. Codex also passed one synthetic document-injection scenario; Claude passed an instruction-only refusal check with tools disabled. These are limited internal technical tests, not independent user testing or broad security validation. AionUi native Skill discovery and integration have not been tested.

## Development tests

Install the test extra and run:

```powershell
python -m pip install -e ".[test]"
python -m pytest tests -q -rs
```

Only tests included in the clean public release candidate should be treated as public regression tests. Internal research reports and historical private fixtures are not part of this distribution.

## Contributing and security

- See [Contributing](CONTRIBUTING.md) before submitting a change.
- See [Security](SECURITY.md) for responsible vulnerability reporting.

## License

MIT License. See [LICENSE](LICENSE). The license applies only to original project materials included in the clean public distribution; third-party materials are excluded.
