# Security Policy

## Supported versions

Security fixes are currently considered for the latest public release candidate. This project is early-stage and does not yet promise a formal security response SLA.

## Reporting a vulnerability

Do not publish sensitive vulnerability details, private documents, credentials, or exploit material in a public issue.

Before the first public release, the maintainer must make the repository public and enable GitHub Private Vulnerability Reporting in the repository security settings. After it is enabled, use the **Report a vulnerability** option from the [repository's Security Advisories page](https://github.com/Jozhio/RequirementDelta/security/advisories). This reporting route is **not active while the repository remains private in staging**. Until activation is verified, do not include confidential details in public issues or discussions; request a private reporting route from the maintainer without disclosing the vulnerability itself.

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
