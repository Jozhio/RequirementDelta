# Agent Skill integration

RequirementDelta 0.1.0 includes an instruction-only Agent Skill. It orchestrates the existing local CLI; it does not reimplement comparison rules and does not install the Python package.

## Package layout

```text
skills/requirementdelta/
  SKILL.md                         # canonical source
  references/
    CONTEXT_SCHEMAS.md
    REPORT_INTERPRETATION.md

.agents/skills/requirementdelta/
  SKILL.md                         # Codex project-level copy

.claude/skills/requirementdelta/
  SKILL.md                         # Claude Code project-level copy
```

All three `SKILL.md` files must remain byte-identical. Edit the canonical file under `skills/requirementdelta/`, then copy it to the two host-specific locations and run the package tests.

## Install the Python CLI

The Skill and the CLI are separate components. The CLI must be installed in the environment that the agent's terminal uses.

From this repository root, Windows PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\requirementdelta.exe --version
```

Expected version:

```text
RequirementDelta 0.1.0
```

If the target project is a different repository, install the CLI from a trusted local RequirementDelta checkout into that project's chosen Python environment. Do not assume the package is published on PyPI. The installation step may need build-time dependencies; the installed runtime itself uses the Python standard library and does not need a network connection.

If the agent's shell does not activate the virtual environment, use the explicit path to that environment's `requirementdelta.exe` (Windows) or `requirementdelta` executable (POSIX). Do not install into the system Python merely to make the command visible.

## Use in Codex

Codex discovers repository skills from `.agents/skills/<skill-name>/SKILL.md`.

When working in this repository, the project-level Skill is at:

```text
.agents/skills/requirementdelta/SKILL.md
```

After opening the repository in Codex, check the available Skills list or invoke `$requirementdelta` explicitly. Discovery does not guarantee automatic invocation for every relevant request; the user can invoke it directly.

Official documentation: [Codex customization and Skills](https://learn.chatgpt.com/docs/customization/overview).

## Use in Claude Code

Claude Code discovers project Skills from:

```text
.claude/skills/requirementdelta/SKILL.md
```

After opening this repository in Claude Code, use `/skills` to inspect available Skills or invoke `/requirementdelta` explicitly. Host version, permissions, and project trust settings still govern whether the Skill can run terminal commands.

Official documentation: [Claude Agent Skills overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview).

## Copy into another project

From this repository root, set `$target` to the user's intended project root. These commands copy only Skill instructions and references; they do not install the Python CLI.

Windows PowerShell — Codex:

```powershell
$target = 'C:\path\to\target-project'
New-Item -ItemType Directory -Force (Join-Path $target '.agents\skills\requirementdelta') | Out-Null
Copy-Item -Recurse -Force '.\skills\requirementdelta\*' (Join-Path $target '.agents\skills\requirementdelta')
```

Windows PowerShell — Claude Code:

```powershell
$target = 'C:\path\to\target-project'
New-Item -ItemType Directory -Force (Join-Path $target '.claude\skills\requirementdelta') | Out-Null
Copy-Item -Recurse -Force '.\skills\requirementdelta\*' (Join-Path $target '.claude\skills\requirementdelta')
```

Replace the placeholder with a real target path. Do not copy into a project without the user's approval.

## What this does not claim

- The Skill is not an MCP server, plugin, Python package, or security sandbox.
- The Skill does not grant shell permissions or bypass host approval.
- This repository's Codex and Claude Code directory layouts are provided, but native discovery and live invocation must be tested in each installed host.
- AionUi native Skill discovery is not claimed or tested in this phase.
- The Skill does not fetch official documents or verify whether a supplied version is the latest.

## Verification

Run the public test suite:

```powershell
python -m pytest tests -q -rs
```

The Skill package tests verify:
- required frontmatter fields and naming constraints;
- the canonical file and both host copies are byte-identical;
- all linked reference files exist;
- the instructions preserve the CLI's actual command and uncertainty contract;
- the documented no-context workflow produces a valid report with read-only inputs.

On one Windows workstation, Codex CLI 0.164.0 discovered the project-level Skill and completed a Skill-guided comparison using the installed RequirementDelta 0.1.0 CLI. Claude Code 2.1.310 (configured with a DeepSeek model) also completed a real Skill-guided comparison. Both outputs were independently validated against source evidence and matched the direct CLI result for one synthetic Markdown pair. Codex additionally passed a single document-injection test; Claude passed an instruction-only refusal test with tools disabled. This does not validate every permission mode, environment or adversarial input. The Claude custom-model identification warning and a Codex user-level Skill traversal warning remain unresolved. AionUi native discovery is not claimed.

These results establish limited local Skill-triggered operation on one Windows device. Other hosts, permission settings and clean third-party installations require separate verification.
