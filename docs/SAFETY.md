# Safety, privacy, and limitations

## Local processing

The core CLI reads local input files and writes reports to the explicitly selected output directory. It does not need a network connection, paid API, model endpoint, or external upload.

## Treat documents as data

Text inside a requirement document may contain instructions, commands, URLs, or malicious prompt-injection content. RequirementDelta treats all document content as data. It does not execute commands found in documents or send their contents to external services.

## Input protection

- Input files must be local UTF-8 TXT/Markdown.
- The reader enforces the allowed-root boundary.
- Unsupported formats are rejected rather than parsed as text.
- Missing files, permission failures, invalid UTF-8, and evidence failures must remain explicit errors or unverified states.
- Source bytes are not modified by analysis.
- Source hashes are rechecked during report generation to detect concurrent changes.

## Output protection

- Reports are written only to the requested output directory.
- Existing reports are not overwritten by default.
- The output directory and report files must not collide with protected input paths.
- Review reports before sharing: they may contain original quotes and local file paths.

## Human review

RequirementDelta does not provide:
- legal advice;
- official eligibility or compliance determinations;
- final approval decisions;
- guarantees that every semantic change has been found;
- automatic submission, email, notification, or other external action.

Any suggested action is a prompt for human review. The user remains responsible for checking official sources and making the final decision.

## Uncertainty is a valid outcome

- `NEEDS_CONFIRMATION` means the supplied context is not sufficient for a confident applicability decision.
- `INSUFFICIENT_CONTEXT` means the implemented rules cannot decide from the available facts.
- `UNVERIFIED` means an input or evidence could not be verified. It must never be interpreted as “no change”, “safe”, or “not applicable”.
- `NO_SUPPORTED_CHANGE_FOUND` means only that the bounded supported rules did not confirm a change; it is not proof that no change exists.

## Supported input scope

Initial release supports local UTF-8 `.txt` and `.md` files only. PDF, DOCX, scanned documents, OCR, webpages, and remote URLs are outside the supported scope.

## Sensitive information

Do not include passwords, API keys, access tokens, identity numbers, account numbers, or unnecessary personal data in context files. Do not publish reports containing private project details without reviewing and redacting them.

## Security reports

See [SECURITY.md](../SECURITY.md) for responsible vulnerability reporting.
