# Security Policy

## Supported versions

Security fixes are considered for the latest published version, beginning with v0.1.0. This project is early-stage and does not yet promise a formal security response SLA.

## Reporting a vulnerability

Do not publish sensitive vulnerability details, private documents, credentials, or exploit material in a public issue.

GitHub Private Vulnerability Reporting is **enabled** for this public repository. To report a vulnerability privately, select **Report a vulnerability** on the [repository's Security Advisories page](https://github.com/Jozhio/RequirementDelta/security/advisories). Do not include confidential reports, exploit details, credentials, or private document content in public issues or discussions.

## Scope

Please report issues involving:
- path traversal or allowed-root bypass;
- unintended input modification or report overwrite;
- code execution or network transmission caused by document content;
- secret or private-path leakage in release artifacts;
- evidence verification or fail-closed behavior that can be bypassed.

## Out of scope

- Unsupported document formats being rejected.
- Results requiring human review due to ambiguous or missing context.
- A failure to infer a legal, compliance, or eligibility conclusion that the tool does not claim to provide.

## Responsible disclosure

Please allow time for investigation and a fix before public disclosure. Do not test against systems or data that you do not own or have permission to use.
