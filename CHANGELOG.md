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

### Limitations
- No PDF/DOCX/OCR, web monitoring, or remote document retrieval.
- No independent user study or real-world accuracy claim.
- Codex project-level Skill metadata discovery was verified with Codex CLI 0.164.0; an actual Skill-triggered model session remains untested.
- Claude Code project-level Skill files are included, but live `/skills` discovery and invocation remain untested.
- AionUi native Skill discovery is not claimed or tested.
