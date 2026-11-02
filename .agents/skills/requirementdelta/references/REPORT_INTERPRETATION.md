# Report interpretation reference

The CLI writes a JSON object (`report.json`) and a Markdown rendering (`report.md`). Use the JSON as the machine-readable source of truth. The report schema is `p0-4-report-v1`; it is independent of the software version `0.1.0`.

## Validate first

Check:
- `schema_version == "p0-4-report-v1"`
- `tool.name == "requirementdelta"`
- `errors` is an empty array
- `read_only.checked == true`
- `read_only.inputs_unchanged == true`
- `summary.unsafe_deterministic_actions == 0`

If the JSON is missing or malformed, any required check fails, `errors` is non-empty, or the input hashes were not verified unchanged, do not interpret the report as a valid comparison. State that verification failed and recommend rerunning only after the cause is resolved.

## Overall status

| `summary.overall_status` | Meaning | Safe wording |
|---|---|---|
| `NO_TEXT_DIFFERENCE` | The decoded input texts are identical. | “The two supported text inputs are identical.” |
| `NO_SUPPORTED_CHANGE_FOUND` | The bounded implemented rules found no supported change. | “No change was confirmed within the supported rules; this does not prove there is no meaningful change.” |
| `REVIEW_REQUIRED` | A supported change or unresolved item requires human review. | “The comparison found changes or unresolved items that need review.” |
| `UNVERIFIED` | An input, evidence item, or concurrent-input check could not be verified. | “The result is unverified; no no-change or applicability conclusion can be made.” |

Never map `REVIEW_REQUIRED` to “user is affected” or `NO_SUPPORTED_CHANGE_FOUND` to “nothing changed”.

## Change records

Each item in `changes` may include:
- `change_id`: deterministic identifier for this change and source snapshots.
- `relation`: relation such as `ADDED`, `MODIFIED`, `REMOVED`, or `UNCHANGED`.
- `material_status`: `CHANGED`, `UNKNOWN`, or another explicit engine status.
- `review_status`: `VERIFIED`, `NEEDS_REVIEW`, or another explicit engine status.
- `reason`: bounded-rule explanation, not a probability or legal interpretation.
- `fields`: detected field-level changes such as dates, numbers, or labels.
- `old_evidence` and `new_evidence`: source quotes, line/character/byte positions, and document SHA-256 hashes.
- `old_context` and `new_context`: nearby source text when available.

Evidence records can contain absolute paths and original source quotes. Do not expose absolute paths by default. Cite line numbers and short excerpts. SHA-256 identifies the bytes read; it does not authenticate the source or prove that it is official.

A score in a change record is a lexical similarity score, not a probability, confidence interval, or chance that a legal obligation changed.

## Applicability records

Each item in `assessments` can include `applicability_status`, `action_status`, `task_status`, `evidence_status`, `reasoning`, `questions`, and `recommended_actions`.

| Applicability state | Meaning |
|---|---|
| `APPLIES` | A supported rule matched the supplied confirmed context. This is not an official eligibility or legal decision. |
| `DOES_NOT_APPLY` | A specific supported condition was determined not to apply. This is not a universal “not eligible” or “no obligation” result. |
| `NEEDS_CONFIRMATION` | More explicit user facts or exact scope confirmation are needed. |
| `INSUFFICIENT_CONTEXT` | The implemented rules cannot decide from the supplied facts. |
| `UNVERIFIED` | Evidence or input validation failed. Do not infer applicability. |

Action states:
- `ACTION_REVIEW_REQUIRED`: a human action is suggested for review; it is not executed.
- `NO_CURRENT_ACTION`: no current action was produced for the evaluated clause; it is not proof that no other action exists.
- `NEEDS_REVIEW`: unresolved review is required.
- `UNVERIFIED`: evidence or input verification failed.

`recommended_actions` are informational prompts. The tool does not submit, email, notify, register, approve, or modify external systems.

## Context absence and uncertainty

When no context file is supplied:
- `summary.assessments_total` is normally zero;
- `summary.unassessed_changes_total` may be positive;
- a warning says that applicability was not assessed.

State this explicitly. Do not infer personal applicability from document wording or conversational assumptions.

Read:
- `review_items` for changes and assessments needing human review;
- `unverified_items` for unresolved evidence/input conditions;
- `warnings` for scope and interpretation warnings;
- `coverage.formats` and `coverage.limitations` for the implemented boundary.

If `summary.unsafe_deterministic_actions` is not zero, flag it and stop before recommending any action.

## Exit codes

| Exit | Meaning | Handling |
|---:|---|---|
| `0` | Report generation succeeded. | Still inspect overall status and all validation fields. |
| `2` | Input, path, format, argument, or context error. | An error report may exist; explain the failure, not a successful comparison. |
| `3` | Internal, evidence, write, or concurrent-input-change error. | Treat as unverified and stop. |

The exit code alone is not the report result.

## Privacy and disclosure

The JSON and Markdown reports may contain:
- absolute paths of old/new input files;
- source quotes from both versions;
- hashes and line/byte positions;
- user-confirmed context facts.

Treat reports and context JSON as private. Do not paste the complete report into a chat, issue, or public repository. Provide only the minimum necessary evidence and redact paths or sensitive quotes before sharing.
