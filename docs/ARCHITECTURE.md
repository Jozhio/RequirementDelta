# Architecture

RequirementDelta is a local command-line pipeline. The implementation is split into small modules with explicit evidence and failure boundaries.

## Processing pipeline

1. **CLI and path validation** (`cli.py`)
   - Parse explicit old/new input paths, optional context, output path, and allowed root.
   - Reject output/input collisions.
   - Refuse to overwrite existing reports unless the user explicitly opts in.

2. **Document ingestion** (`ingest.py`)
   - Accept local UTF-8 TXT/Markdown only.
   - Enforce allowed-root containment and supported path rules.
   - Preserve original text and SHA-256 metadata.
   - Return explicit unreadable/unsupported states rather than fabricating empty content.

3. **Segmentation and evidence** (`segment.py`, `evidence.py`)
   - Segment supported text into reviewable units.
   - Record source quotes, positions, and document hashes.
   - Verify evidence against the source snapshot.

4. **Change analysis** (`align.py`, `correspondence.py`, `changes.py`, `time_rules.py`)
   - Align old/new text segments.
   - Identify bounded candidate changes and supported field-level differences.
   - Preserve ambiguity and abstain where the implemented rules cannot support a conclusion.

5. **Applicability and policy context** (`applicability.py`, `conditions.py`, `task_context.py`, `policy_*.py`)
   - Evaluate only supported conditions against explicit user-provided context.
   - Keep missing facts, uncertain aliases, duplicate scopes, and unsupported clauses unresolved.
   - Produce review suggestions, not external actions.

6. **Report construction** (`workflow.py`, `report.py`)
   - Assemble JSON and Markdown outputs.
   - Include evidence, statuses, warnings, limitations, and read-only verification metadata.

7. **Safe report writing** (`cli.py`)
   - Write temporary report files and atomically publish the pair.
   - Recheck source hashes before finalizing.
   - Refuse to publish a stale report if the input changed during processing.

## Main design principles

- Evidence before interpretation.
- Explicit user context before applicability decisions.
- Unknown is not false.
- Unverified is not no change.
- The document is data, never executable instructions.
- Local-first processing; no network is needed by the core CLI.
- Human review remains responsible for final decisions.

## Non-goals

The initial release does not implement OCR, PDF/DOCX parsing, browser monitoring, automatic source retrieval, email alerts, legal reasoning, eligibility certification, or external workflow execution.
