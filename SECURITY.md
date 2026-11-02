# Security Policy

## Supported versions

Security fixes are currently considered for the latest public release candidate. This project is early-stage and does not yet promise a formal security response SLA.

## Reporting a vulnerability

Do not publish sensitive vulnerability details, private documents, credentials, or exploit material in a public issue.

A private vulnerability reporting channel must be configured in the public repository before the first public release. Until that channel is published, do not include confidential details in public discussions; wait for the repository maintainer to provide a private reporting route.

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
