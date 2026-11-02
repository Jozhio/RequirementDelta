# Changelog

All notable changes to RequirementDelta are documented here.

## [0.1.0] - Unreleased

First public-release candidate, prepared from the P0-4 prototype.

### Added
- Local CLI for comparing two UTF-8 TXT/Markdown versions.
- Traceable source evidence and SHA-256 metadata.
- Bounded applicability assessment using explicit user context.
- JSON and Markdown reports.
- Standard Python packaging metadata and a console entry point; clean offline wheel installation verified on Python 3.11 and 3.13.
- Public usage, architecture, safety, and Agent Skill integration documentation.
- Instruction-only Agent Skill with canonical, Codex (.agents), and Claude Code (.claude) copies.
- Context-schema and report-interpretation references for the Skill.
- Skill package regression tests for metadata, host-copy parity, references, and CLI smoke behavior.

### Internal validation
- On a Windows test workstation, both Codex and Claude Code (using a configured DeepSeek model) completed one real Skill-guided comparison of the same synthetic Markdown input; the generated CLI reports and evidence were independently checked.
- Codex also completed one limited synthetic document-injection test without executing document-borne instructions. Claude Code completed an instruction-only refusal check with tools disabled; this does not validate unrestricted tool permissions.
- Public GitHub URL installation was verified separately for the Python CLI and skills CLI in isolated Windows projects. The skills CLI installed matching project-local copies for Codex and Claude Code; a skills.sh catalog listing is not yet claimed.

### Limitations
- No PDF/DOCX/OCR, web monitoring, or remote document retrieval.
- No independent user study or real-world accuracy claim.
- No AionUi native Skill discovery or broad adversarial security campaign has been completed.
