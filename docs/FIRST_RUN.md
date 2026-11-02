# First run: verify a released CLI with synthetic documents

This tutorial uses **fictional** examples. It is a developer-verified smoke test, not evidence of independent user adoption or a real-world accuracy benchmark.

## 1. Prerequisites

Windows 10/11, Python 3.11+, Git and network access for installation. Local comparison runs without any cloud API after installation. macOS/Linux are not yet independently verified.

## 2. Install the released version

In a new working directory, open PowerShell:

```powershell
git clone --branch v0.1.0 --depth 1 https://github.com/Jozhio/RequirementDelta.git
cd RequirementDelta
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\requirementdelta.exe --version
```

The version command should print `RequirementDelta 0.1.0`.

## 3. Run a synthetic comparison

The `examples/` directory contains a fictional application deadline change, from December 8 to December 3, 2026.

```powershell
.\.venv\Scripts\requirementdelta.exe analyze --old .\examples\old.md --new .\examples\new.md --output .\out\first-run
Get-Content .\out\first-run\report.md -Encoding UTF8
```

This should generate both:

- `out/first-run/report.json`
- `out/first-run/report.md`

The result needs human review and is **not** an official eligibility or application decision. If the output directory already exists with reports, choose a **fresh directory**; overwriting is disabled by default.

## 4. Optional Agent Skill install

For Codex and Claude Code, with Node.js 22.20+ installed:

```powershell
npx skills add Jozhio/RequirementDelta --skill requirementdelta -a codex -a claude-code --copy -y
```

This installs **only the Agent instructions**; it does not install the Python CLI or make it visible to every Agent automatically. The skills CLI can send anonymous installation telemetry; set `DISABLE_TELEMETRY=1` if you wish to opt out.

## 5. Send safe, genuine feedback

If you actually tried this workflow, use the [first-use feedback form](https://github.com/Jozhio/RequirementDelta/issues/new/choose).

- Share only fictional or sanitized input examples in a public Issue.
- Do not upload private policy, application, research, or personal documents.
- Remove usernames, secrets and identifying local paths from logs.
- [Disclose vulnerabilities privately](https://github.com/Jozhio/RequirementDelta/security/advisories).

## Not supported or verified

No PDF/DOCX/OCR, URL monitoring, legal advice, automatic application submission, generalized rule understanding, macOS/Linux validation, or independent human usability study is claimed.
