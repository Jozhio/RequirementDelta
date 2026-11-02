"""Stable Markdown rendering for the P0-4 report dict."""
from __future__ import annotations


def _cell(value, limit: int = 180) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>")
    text = text.replace("|", "\\|")
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return text


def _quote(value, limit: int = 180) -> str:
    return "`" + _cell(value, limit) + "`"


def _evidence_text(evidence) -> str:
    if not evidence:
        return "—"
    return (
        f"line {evidence.get('line_start')}–{evidence.get('line_end')}, "
        f"bytes [{evidence.get('byte_start')},{evidence.get('byte_end')}), "
        f"chars [{evidence.get('char_start')},{evidence.get('char_end')}), "
        f"sha {str(evidence.get('doc_sha256'))[:12]}…"
    )


def _input_rows(report: dict) -> list[str]:
    rows = [
        "| 角色 | 状态 | SHA-256 | 路径 | 错误码 |",
        "|---|---|---|---|---|",
    ]
    for role in ("old", "new"):
        item = report["inputs"][role]
        rows.append(
            "| "
            + " | ".join(
                [
                    role,
                    _cell(item.get("status")),
                    _cell(str(item.get("sha256") or "—")[:16]),
                    _cell(item.get("path")),
                    _cell(item.get("error_code")),
                ]
            )
            + " |"
        )
    return rows


def _overall_text(status: str) -> str:
    return {
        "REVIEW_REQUIRED": "检测到变化或不确定项，需要人工复核。",
        "NO_SUPPORTED_CHANGE_FOUND": (
            "在受支持的变化规则内未发现可确认变化。"
            "这**不等于已确认不存在变化**；未支持格式、语义和外部要求仍需人工核查。"
        ),
        "NO_TEXT_DIFFERENCE": (
            "两版输入文本逐字节相同。本报告只说明文本无差异，"
            "**不等于已确认不存在变化**；未支持格式、语义、外部要求或遗漏仍需人工核查。"
        ),
        "UNVERIFIED": "输入或证据未验证；不得把本报告读作“无变化”或“安全”。",
    }.get(status, status)


def render_markdown(report: dict) -> str:
    lines = [
        "# RequirementDelta P0-4 变化与适用性报告",
        "",
        f"- 报告 schema：`{report['schema_version']}`",
        f"- 工具阶段：`{report['tool']['stage']}`",
        f"- 总体状态：**{report['summary']['overall_status']}**",
        f"- 状态解释：{_overall_text(report['summary']['overall_status'])}",
        "",
        "## 1. 输入",
        "",
        *_input_rows(report),
        "",
    ]
    context = report.get("context") or {}
    if context.get("provided"):
        lines += [
            "## 2. 用户上下文",
            "",
            f"- schema：`{context.get('schema_version')}`",
            f"- 用户确认：`{context.get('confirmed_by_user')}`",
        ]
        if "program" in context:
            lines.append(f"- program：`{_cell(context.get('program'))}`")
        if "role" in context:
            lines.append(f"- role：`{_cell(context.get('role'))}`")
        lines += [
            f"- facts：`{len(context.get('facts') or [])}` 条",
            f"- completed_tasks：`{len(context.get('completed_tasks') or [])}` 条",
            f"- pending_tasks：`{len(context.get('pending_tasks') or [])}` 条",
            "",
        ]
    else:
        lines += [
            "## 2. 用户上下文",
            "",
            "未提供用户上下文：本轮只输出变化与证据，**未进行适用性判断**。",
            "",
        ]

    summary = report["summary"]
    lines += [
        "## 3. 运行摘要",
        "",
        "| 指标 | 值 |",
        "|---|---:|",
        f"| 变化条款 | {summary.get('changes_total', 0)} |",
        f"| 其中 CHANGED | {summary.get('changes_changed', 0)} |",
        f"| 其中 UNKNOWN | {summary.get('changes_unknown', 0)} |",
        f"| 其中 NEEDS_REVIEW | {summary.get('changes_review', 0)} |",
        f"| 评估结果 | {summary.get('assessments_total', 0)} |",
    ]
    for status, count in (summary.get("applicability_counts") or {}).items():
        lines.append(f"| 适用性 {status} | {count} |")
    lines += [
        f"| 建议人工行动 | {summary.get('recommended_actions_total', 0)} |",
        f"| 人工复核项 | {summary.get('review_items_total', 0)} |",
        f"| 未验证项 | {summary.get('unverified_items_total', 0)} |",
        f"| 不安全确定行动 | {summary.get('unsafe_deterministic_actions', 0)} |",
        "",
    ]

    lines += ["## 4. 检测到的变化", ""]
    changes = report.get("changes") or []
    if not changes:
        lines += [
            "在受支持规则内没有形成可确认的条款变化。",
            "",
            _overall_text(report["summary"]["overall_status"]),
            "",
        ]
    else:
        lines += [
            "| change_id | 关系 | material | review | 旧位置 | 新位置 | 原因 |",
            "|---|---|---|---|---|---|---|",
        ]
        for change in changes:
            lines.append(
                "| "
                + " | ".join(
                    [
                        f"`{change['change_id']}`",
                        _cell(change["relation"]),
                        _cell(change["material_status"]),
                        _cell(change["review_status"]),
                        _cell(_evidence_text(change.get("old_evidence"))),
                        _cell(_evidence_text(change.get("new_evidence"))),
                        _cell(change.get("reason")),
                    ]
                )
                + " |"
            )
        lines += [""]
        for change in changes:
            lines += [
                f"### {change['change_id']}",
                "",
                f"- 关系：`{change['relation']}`；material：`{change['material_status']}`；"
                f"review：`{change['review_status']}`",
                f"- 原因：{_cell(change.get('reason'), 500)}",
            ]
            if change.get("fields"):
                lines.append("- 字段变化：")
                for field in change["fields"]:
                    lines.append(
                        f"  - `{field.get('kind')}`: "
                        f"`{_cell(field.get('old_value'))}` → `{_cell(field.get('new_value'))}`"
                    )
            if change.get("old_evidence"):
                ev = change["old_evidence"]
                lines += [
                    f"- 旧版证据：{_evidence_text(ev)}",
                    f"  - {_quote(ev.get('quote'))}",
                ]
            else:
                lines.append("- 旧版证据：无（新增条款；报告不据此宣称全球新义务）。")
            if change.get("new_evidence"):
                ev = change["new_evidence"]
                lines += [
                    f"- 新版证据：{_evidence_text(ev)}",
                    f"  - {_quote(ev.get('quote'))}",
                ]
            else:
                lines.append("- 新版证据：无（删除条款；报告不据此宣称规则废止）。")
            lines += [""]

    correspondences = report.get("correspondences") or []
    if correspondences:
        lines += ["## 5. 跨段落证据关联（仅复核提示）", ""]
        for index, link in enumerate(correspondences, 1):
            lines.append(f"{index}. `{link['relation']}` / `{link['review_status']}`：{_cell(link.get('reason'), 400)}")
        lines += [""]

    lines += ["## 6. 适用性评估", ""]
    assessments = report.get("assessments") or []
    if not assessments:
        lines += [
            "没有适用性评估结果。"
            + (" 未提供用户上下文。" if not context.get("provided") else " 当前输入没有可评估的变化。"),
            "",
        ]
    else:
        lines += [
            "| 来源 | change_id | 适用性 | 任务状态 | 行动状态 | evidence | 置信度 |",
            "|---|---|---|---|---|---|---|",
        ]
        for result in assessments:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _cell(result.get("source")),
                        f"`{_cell(result.get('change_id'))}`",
                        _cell(result.get("applicability_status")),
                        _cell(result.get("task_status")),
                        _cell(result.get("action_status")),
                        _cell(result.get("evidence_status")),
                        _cell(result.get("confidence")),
                    ]
                )
                + " |"
            )
        lines += [""]
        for result in assessments:
            actions = result.get("recommended_actions") or []
            if not actions:
                continue
            lines.append(f"### {result.get('change_id')} 的建议行动")
            lines.append("")
            for action in actions:
                lines += [
                    f"- 任务：`{_cell(action.get('task_id'))}`；进度：`{_cell(action.get('progress_status'))}`"
                    f"；外部执行：`{action.get('executes_external_action')}`",
                    f"  - 要求：{_cell(action.get('requirement'), 400)}",
                    f"  - 提示：{_cell(action.get('message'), 500)}",
                    f"  - 证据引用：`{_cell(action.get('evidence_ref'))}`",
                ]
            lines.append("")

    sections = report.get("policy_sections") or []
    if sections:
        lines += ["## 7. 文档级政策节", ""]
        lines += [
            "| scope_id | program | role | 适用性 | 行动 | 未决条款 | 局部验证 |",
            "|---|---|---|---|---|---:|---|",
        ]
        for section in sections:
            lines.append(
                "| "
                + " | ".join(
                    [
                        f"`{_cell(section.get('scope_id'))}`",
                        _cell(section.get("program_text")),
                        _cell(section.get("role_text")),
                        _cell(section.get("applicability_status")),
                        _cell(section.get("action_status")),
                        str(len(section.get("unresolved_clauses") or [])),
                        _cell(section.get("local_validation_status")),
                    ]
                )
                + " |"
            )
        lines += [""]

    lines += ["## 8. 人工复核项", ""]
    review_items = report.get("review_items") or []
    if not review_items:
        lines += ["无额外人工复核项（仍请阅读覆盖限制）。", ""]
    else:
        for item in review_items:
            if item["kind"] == "HUMAN_ACTION":
                lines.append(
                    f"- **HUMAN_ACTION** `{_cell(item.get('task_id'))}` "
                    f"({_cell(item.get('progress_status'))})：{_cell(item.get('message'), 500)}"
                )
            elif item["kind"] == "UNRESOLVED_POLICY_CLAUSE":
                lines.append(
                    f"- **UNRESOLVED_POLICY_CLAUSE** `{_cell(item.get('clause_kind'))}`："
                    f"{_quote(item.get('quote'))}；{_cell(item.get('reason'))}"
                )
            elif item["kind"] == "CHANGE_REVIEW":
                lines.append(
                    f"- **CHANGE_REVIEW** `{_cell(item.get('change_id'))}`："
                    f"{_cell(item.get('reason'), 500)}"
                )
            else:
                lines.append(
                    f"- **{_cell(item.get('kind'))}** `{_cell(item.get('change_id'))}`："
                    f"{_cell('; '.join(item.get('reasoning') or []), 500)}"
                )
        lines += [""]

    lines += ["## 9. 未验证事项", ""]
    unverified = report.get("unverified_items") or []
    if not unverified:
        lines += ["无未验证事项记录。", ""]
    else:
        for item in unverified:
            lines.append(f"- `{_cell(item.get('kind'))}`：{_cell(item.get('message') or item.get('limitations'))}")
        lines += [""]

    warnings = report.get("warnings") or []
    if warnings:
        lines += ["## 10. 警告与范围说明", ""]
        for warning in warnings:
            lines.append(f"- {_cell(warning, 600)}")
        lines += [""]

    lines += [
        "## 11. 覆盖范围与限制",
        "",
        f"- 输入格式：{_cell(', '.join(report['coverage'].get('formats') or []))}",
        f"- 变化规则：{_cell(report['coverage'].get('change_rules'), 500)}",
        f"- 适用性规则：{_cell(report['coverage'].get('applicability_rules'), 500)}",
        f"- 政策规则：{_cell('; '.join(report['coverage'].get('policy_rules') or []), 500)}",
    ]
    for limitation in report["coverage"].get("limitations") or []:
        lines.append(f"- 限制：{_cell(limitation, 600)}")
    lines += [
        "",
        f"- 无变化措辞：{_cell(report['coverage'].get('no_change_meaning'), 600)}",
        "",
        "## 12. 只读与运行状态",
        "",
        f"- 输入未被修改：`{report['read_only'].get('inputs_unchanged')}`",
        f"- 已检查：`{report['read_only'].get('checked')}`",
        "",
        "---",
        "",
        "本报告是人工复核辅助，不构成官方、法律、资格或合规结论；"
        "`ACTION_REVIEW_REQUIRED` 不等于用户违规，`NO_CURRENT_ACTION` 仅针对已评估条款。",
        "",
    ]
    return "\n".join(lines)
