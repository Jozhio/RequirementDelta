# Contributing

Thank you for considering a contribution.

## Before opening a change

- Read README.md and docs/SAFETY.md.
- Keep the supported scope narrow and evidence-driven.
- Do not add real personal data, private application documents, credentials, or third-party documents without confirmed redistribution rights.
- Do not describe synthetic cases as real-world benchmark evidence.
- Preserve fail-closed behavior: unknown and unverified inputs must not become a confident no-change result.

## Development setup

Use Python 3.11 or newer:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
python -m pytest tests -q -rs
```

## Pull requests

A pull request should include:
- a clear description of the behavior change;
- tests for normal, boundary, and failure behavior;
- updates to user-facing documentation when the CLI or report contract changes;
- confirmation that no private data, local paths, generated reports, or secrets were added.

Do not weaken safety tests or expected outcomes merely to make a test pass. Explain any intentional change to uncertainty or evidence semantics.
