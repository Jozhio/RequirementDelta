# RequirementDelta

**本地、可追溯证据的需求文档变更审查工具：Python CLI + Agent Skill**

[English](README.md) · [正式版本 v0.1.0](https://github.com/Jozhio/RequirementDelta/releases/tag/v0.1.0) · [使用文档](docs/USAGE.md) · [安全说明](SECURITY.md)

RequirementDelta 用于比较两份**用户明确选择的**旧版、新版需求或规则文档，找出当前规则支持识别的变化，并在报告中保留对应原文、位置及 SHA-256 校验信息。

适用于竞赛通知、项目要求、申请指南、任务规范等**变更初筛**，但**不是**通用语义理解、法律合规判断或官方资格认定工具。

## 适合解决的问题

假设一份虚构申请规则发生变化：

| 项目 | 旧版 | 新版 |
|---|---|---|
| 截止时间 | 2026-12-08 18:00 | 2026-12-03 18:00 |

RequirementDelta 可以针对当前支持的规则类型生成一份**需要人工复核的变更报告**，保留原文证据，而不是直接替你判断“肯定符合申请资格”。

- 对比本地 UTF-8 `.txt` 或 `.md` 两份文档。
- 生成 `report.json`（机器可读）与 `report.md`（人工查看）。
- 保留新旧证据、来源行号、文档哈希及不确定状态。
- 仅在用户明确确认上下文时，尝试执行受限的适用性规则分析。
- 默认不覆盖已有报告；不执行文档中出现的指令。
- 核心 CLI 在安装后离线运行，不要求付费模型 API。

## 快速开始（Windows）

已验证环境：Windows 10/11、Python 3.11/3.13。安装需要 Git 和网络；运行本地比较无需联网。

打开 PowerShell，在**你自己的项目目录**中执行：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install "git+https://github.com/Jozhio/RequirementDelta.git@v0.1.0"
.\.venv\Scripts\requirementdelta.exe --version
```

准备两个 UTF-8 Markdown 或 TXT 文件（例如 `old.md` 和 `new.md`），执行：

```powershell
.\.venv\Scripts\requirementdelta.exe analyze --old .\old.md --new .\new.md --output .\out\review
```

报告位于：

```text
out/review/
  report.json
  report.md
```

如果报告已经存在，默认拒绝覆盖。也可以克隆本仓库并使用 `examples/old.md`、`examples/new.md` 运行示例，详见 [英文使用文档](docs/USAGE.md)。

## 作为 Agent Skill 使用（可选）

RequirementDelta 提供 Codex、Claude Code 的 Skill 指令包。使用 [skills CLI](https://www.skills.sh/docs/cli) 安装时，需要 Node.js 22.20+。

在目标项目目录中执行：

```powershell
npx skills add Jozhio/RequirementDelta --skill requirementdelta -a codex -a claude-code --copy -y
```

**务必注意：安装 Skill 不等于安装 Python CLI。** 请先完成上一节的 CLI 安装，并确保 Agent 可以访问该执行文件。

Skill 负责指导 Agent 调用已安装的 CLI、读取报告，并解释需要人工确认的结论；不会替 CLI 重新实现变更检测算法。`--copy` 可避免 Windows 项目目录中的符号链接权限问题。

安装 skills CLI 时可能会发送匿名安装统计；不希望发送时可提前设置环境变量 `DISABLE_TELEMETRY=1`。安装需要联网，分析过程在本地进行。

[Agent Skill 集成说明](docs/SKILL_INTEGRATION.md)

## 如何解读结果

| 状态 | 含义 |
|---|---|
| `NO_TEXT_DIFFERENCE` | 已解码的两份输入文字完全相同。 |
| `NO_SUPPORTED_CHANGE_FOUND` | 在目前实现的规则范围内，未确认支持的变化；**不代表不存在其他变化**。 |
| `REVIEW_REQUIRED` | 检测到变化或未决问题，需要人工复核。 |
| `UNVERIFIED` | 输入或证据不能核实，**不能当作“没有变化”**。 |
| `NEEDS_CONFIRMATION` | 适用性判断所需的用户信息尚未确认或无法精确匹配。 |
| `INSUFFICIENT_CONTEXT` | 现有事实不足以给出适用性判断。 |

上下文 JSON 使用受支持的 `0.3` / `0.4` schema；未获得用户确认的事实不能擅自猜测。详细参数和示例见 [USAGE.md](docs/USAGE.md)。

## 验证情况

正式版本 `v0.1.0` 的 GitHub Actions 已在 Windows Python 3.11、3.13 上分别通过 **258 项测试，0 失败、0 跳过**，还包括 CLI 入口及 wheel 打包检查。

开发者使用合成文件完成了 Codex 与 Claude Code 的 Skill 调用、公开 GitHub 地址安装、少量异常输入和提示注入测试。**这些是内部技术验证，不是独立真实用户研究，也不能证明各种真实政策文档的准确率。**

[查看 GitHub Actions](https://github.com/Jozhio/RequirementDelta/actions/runs/41381291152)

## 重要限制

- **只支持本地 UTF-8 TXT/Markdown。** 不支持 PDF、DOCX、OCR、网页抓取和自动监控。
- 规则检测范围有限，复杂改写或隐含条件可能没有被识别。
- 不保证法律合规、官方申请资格、竞赛获奖资格或任何最终审批结果。
- 不自动提交申请，不执行源文档中的命令，不上传文档。
- 报告可能包含本地路径及原文片段，请在分享前自行核查和脱敏。
- 尚未验证 macOS/Linux、AionUi 原生集成及独立用户体验。

## 项目与参与

- [GitHub Release v0.1.0](https://github.com/Jozhio/RequirementDelta/releases/tag/v0.1.0)
- [架构说明](docs/ARCHITECTURE.md)
- [安全与边界](docs/SAFETY.md)
- [贡献指南](CONTRIBUTING.md)
- [私密报告漏洞](https://github.com/Jozhio/RequirementDelta/security/advisories)

**许可证：MIT，Copyright (c) 2026 Jozhio。**
