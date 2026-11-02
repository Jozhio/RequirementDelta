# Context schemas 0.3 and 0.4

RequirementDelta does not infer the user's personal circumstances. Context files are optional inputs that must be based only on facts the user explicitly confirms.

## General rules

- Use UTF-8 JSON.
- `confirmed_by_user` must be `true` before treating context as user-confirmed.
- Missing values remain unknown. Do not convert missing, null, or ambiguous facts to `false`.
- Do not add identity numbers, passwords, API keys, account numbers, or unrelated personal information.
- Do not add undocumented keys. The parser rejects unsupported keys.
- A context file can contain personal information. Store it only at a user-approved local path and do not publish it.
- If the user has not confirmed a fact, omit it or set its value to `null`; ask before creating or editing the context file.

## Schema 0.3 — project/task context

Use for supported project-level or task-level conditions.

Allowed top-level keys:
- `schema_version` (must be `"0.3"`)
- `confirmed_by_user` (boolean)
- `facts` (array of `{"field": "...", "value": ...}`)
- `completed_tasks` (array of task IDs)
- `pending_tasks` (array of task IDs)

Supported text fact fields:
- `project`
- `role`
- `track`
- `category`
- `region`
- `progress`

Other supported facts:
- `date`: ISO date `YYYY-MM-DD`
- `participating`: boolean or null
- `condition:<key>`: boolean or null; the key may contain letters, digits, underscore, hyphen, or Chinese characters.

Text facts must be non-empty strings without surrounding whitespace and at most 256 characters. At most 64 facts and 128 task IDs per completed/pending list are accepted.

Example:

```json
{
  "schema_version": "0.3",
  "confirmed_by_user": true,
  "facts": [
    {"field": "project", "value": "Example Project"},
    {"field": "participating", "value": true},
    {"field": "condition:has_required_certificate", "value": null}
  ],
  "completed_tasks": [],
  "pending_tasks": []
}
```

The example is synthetic. Replace it only with facts the user has confirmed. A null value is unknown, not false.

## Schema 0.4 — document-level policy context

Use for the limited document-level policy clauses implemented by RequirementDelta.

Allowed top-level keys:
- `schema_version` (must be `"0.4"`)
- `confirmed_by_user` (boolean)
- `program` (optional exact programme/activity heading)
- `role` (optional exact role)
- `facts` (same fact rules as schema 0.3)
- `completed_tasks`
- `pending_tasks`

The `program` must exactly match a supported heading in the new document. Do not normalize abbreviations, aliases, case, or partial matches. If the exact programme anchor is not present or is ambiguous, applicability must remain unresolved. `role` is optional; if the document names a specific role, the role must be explicitly confirmed.

Example:

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

This is a synthetic example, not a recommendation about any real programme. The two AI-related conditions are independent user assertions; do not infer one from the other.

## Agent procedure

1. Ask which context schema is appropriate only after determining what the changed document section concerns.
2. Ask the user for the exact programme heading when schema 0.4 is required.
3. Ask only for facts needed by supported conditions.
4. Repeat the proposed facts back to the user and obtain explicit confirmation.
5. Create a JSON file only at a user-approved path.
6. Pass that path using `--context`.
7. If the user does not want to provide context, omit `--context` and report changes only.

A context result is limited to the implemented rules. It is not a legal, compliance, official approval, or universal eligibility determination.
