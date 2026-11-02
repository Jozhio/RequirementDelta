"""P0-3 deterministic applicability; no file writes, network or external actions.

Assesses a specific change, never certifies the whole document or eligibility.
Use assess() for the batch API. assess_change() also rejects forged change records.
"""
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date
import hashlib
import json
import re

from .changes import analyze
from .evidence import build_evidence, verify_evidence
from .conditions import Condition, parse_condition, evaluate_condition, has_conflict, condition_dict
from .task_context import UserTaskContext


@dataclass(frozen=True)
class Scope:
    project: str
    condition: Condition
    task_ids: tuple[str, ...]
    body: str
    source: str = 'EXPLICIT_PARTICIPANT_CLAUSE'


PREFIX = re.compile(r'项目“([^”\r\n]{1,160})”的参与者(?:（(.+)）)?(.+)')
ITEMS = r'[A-Za-z0-9_\u4e00-\u9fff/-]{1,60}(?:、[A-Za-z0-9_\u4e00-\u9fff/-]{1,60})*'
BODY = re.compile(r'(?:必须提交(?P<items>' + ITEMS + r')|须于(?P<date>\d{4}-\d{2}-\d{2})前提交(?P<dated>' + ITEMS + r'))')


def extract_scope(quote):
    """Parse the entire explicit clause. Unsupported text raises ValueError."""
    m = PREFIX.fullmatch(quote.strip().removesuffix('。'))
    if not m:
        raise ValueError('no complete supported project/participant clause')
    project, expression, body = m.groups()
    b = BODY.fullmatch(body)
    if not b or re.search(r'除外|除非|但|不|未|无须|无需|禁止|如果|只有|仅|或者|以及|而|则', body):
        raise ValueError('unsupported obligation/negation in requirement body')
    if b['date']:
        date.fromisoformat(b['date'])
    base = Condition('AND', children=(Condition('EQ', 'project', project), Condition('EQ', 'participating', True)))
    cond = Condition('AND', children=(base, parse_condition(expression))) if expression else base
    items = (b['items'] or b['dated']).split('、')
    if len(set(items)) != len(items):
        raise ValueError('duplicate requirement items')
    return Scope(project, cond, tuple('submit:' + item for item in items), body)


def _table_scope(change, old, new):
    """Generic exact project-title + hours-column interpretation, not aliases."""
    extras = []
    rows = []
    for snapshot, ev in [(old, change.old_evidence), (new, change.new_evidence)]:
        if ev is None:
            raise ValueError('table requires both sides')
        cells = [v.strip() for v in ev.quote.strip().strip('|').split('|')]
        if len(cells) != 4 or not cells[0] or not re.fullmatch(r'\d+ hours?', cells[3]):
            raise ValueError('unsupported project-hours row')
        # Find the nearest preceding table header, not any unrelated header.
        before = snapshot.content[:ev.char_start]
        lines = list(re.finditer(r'[^\r\n]+', before))
        header = None
        for line in reversed(lines):
            text = line.group().strip()
            if not text.startswith('|'):
                break
            if 'Project Title' in text:
                header = line
                break
        if header is None:
            raise ValueError('project table header absent')
        labels = [x.strip().strip('*') for x in header.group().strip().strip('|').split('|')]
        if labels != ['Project Title', 'Project Idea Link', 'Description', 'Hours']:
            raise ValueError('unsupported column semantics')
        evidence = build_evidence(snapshot, header.start(), header.end())
        if not verify_evidence(snapshot, evidence):
            raise ValueError('table header evidence invalid')
        extras.append(asdict(evidence))
        rows.append(cells)
    if rows[0][:3] != rows[1][:3] or change.old_context != change.new_context:
        raise ValueError('table identity/context changed')
    cond = Condition('AND', children=(Condition('EQ', 'project', rows[1][0]), Condition('EQ', 'participating', True)))
    return Scope(rows[1][0], cond, ('review:project_plan',), rows[1][3], 'PROJECT_HOURS_TABLE'), extras


def _closed_addition(change, old, new, scope):
    """Only an auditable closed local set of mandatory project clauses.

    A schema-like restricted document subset, not general absence reasoning.
    Full snapshots and Counter comparison prove textual presence/absence locally.
    """
    heading = '# 项目“' + scope.project + '”'
    def parse_doc(snapshot):
        lines = [s.strip() for s in snapshot.content.splitlines() if s.strip()]
        if not lines or lines[0] != heading:
            raise ValueError('closed project heading required')
        for text in lines[1:]:
            rule = extract_scope(text)
            if rule.project != scope.project or has_conflict(rule.condition):
                raise ValueError('mixed or conflicting project scope')
        counts = Counter(lines[1:])
        if any(v != 1 for v in counts.values()):
            raise ValueError('duplicate clause')
        return counts
    try:
        a, b = parse_doc(old), parse_doc(new)
        return a < b and change.new_evidence.quote.strip() in b - a
    except ValueError:
        return False


def _base(change, old, new):
    refs = {'old': asdict(change.old_evidence) if change and change.old_evidence else None,
            'new': asdict(change.new_evidence) if change and change.new_evidence else None,
            'old_snapshot_sha256': old.sha256, 'new_snapshot_sha256': new.sha256,
            'scope': [], 'absent_side_reason': None}
    if change and change.relation == 'ADDED':
        refs['absent_side_reason'] = 'No aligned old clause; old snapshot hash records the compared version. No global novelty claim.'
    payload = json.dumps(refs, sort_keys=True, ensure_ascii=False).encode('utf-8')
    return {'schema_version': '0.3', 'change_id': 'C-' + hashlib.sha256(payload).hexdigest()[:24],
            'relation': change.relation if change else 'UNVERIFIED',
            'upstream_material_status': change.material_status if change else 'UNKNOWN',
            'upstream_review_status': change.review_status if change else 'UNVERIFIED',
            'applicability_status': 'INSUFFICIENT_CONTEXT', 'legacy_applicability': 'UNKNOWN',
            'action_status': 'NEEDS_REVIEW', 'matched_conditions': [], 'excluded_conditions': [],
            'missing_information': [], 'reasoning': [], 'questions': [], 'evidence_refs': refs,
            'recommended_actions': [], 'confidence': 'UNDETERMINED', 'uncertainty': [],
            'condition_tree': None, 'local_validation': None, 'evidence_status': 'UNVERIFIED'}


def _uncertain(result, reason, missing=(), unverified=False):
    result['applicability_status'] = 'NEEDS_CONFIRMATION' if missing else 'INSUFFICIENT_CONTEXT'
    result['action_status'] = 'UNVERIFIED' if unverified else 'NEEDS_REVIEW'
    result['missing_information'] = sorted(set(missing))
    result['reasoning'].append(reason)
    result['uncertainty'].append(reason)
    result['questions'] = ['请确认：' + key for key in result['missing_information']] or ['请提供可核验的完整适用条款及其上下文。']
    return result


def _assess(change, old, new, context, authentic):
    r = _base(change, old, new)
    if not old.is_readable or not new.is_readable or old.role != 'old' or new.role != 'new':
        return _uncertain(r, 'Input snapshots are not readable old/new versions.', unverified=True)
    if not authentic:
        return _uncertain(r, 'Change is not a member of the regenerated P0-2 comparison.', unverified=True)
    for snapshot, ev in [(old, change.old_evidence), (new, change.new_evidence)]:
        if ev is not None and not verify_evidence(snapshot, ev):
            return _uncertain(r, 'Evidence failed the P0-1 verifier.', unverified=True)
    if change.new_evidence is None or (change.relation != 'ADDED' and change.old_evidence is None):
        return _uncertain(r, 'Required new or paired evidence is missing.', unverified=True)
    r['evidence_status'] = 'VERIFIED'
    try:
        if change.new_evidence.quote.lstrip().startswith('|'):
            scope, extras = _table_scope(change, old, new)
            r['evidence_refs']['scope'] = extras
        else:
            scope = extract_scope(change.new_evidence.quote)
            allowed_heading = '项目“' + scope.project + '”'
            if any(h != allowed_heading for h in change.new_context + change.old_context):
                raise ValueError('unparsed heading may alter scope')
            if change.old_evidence:
                old_scope = extract_scope(change.old_evidence.quote)
                if old_scope.condition != scope.condition:
                    return _uncertain(r, 'Applicability conditions changed between versions.', ['changed_scope'])
        r['condition_tree'] = condition_dict(scope.condition)
        if has_conflict(scope.condition):
            return _uncertain(r, 'The source condition contains a contradiction.', ['source_condition_conflict'])
    except ValueError as exc:
        return _uncertain(r, 'Unsupported or incomplete scope: ' + str(exc))
    if not context.confirmed_by_user:
        return _uncertain(r, 'Task facts have not been explicitly confirmed by the user.', ['confirmed_by_user'])
    conflicts = context.conflicts()
    if conflicts:
        return _uncertain(r, 'User assertions conflict; none was selected.', ['conflict:' + c for c in conflicts])
    if not context.values('project'):
        return _uncertain(r, 'Participation and other facts require an explicit current project anchor.', ['project'])
    if change.relation == 'ADDED' and _closed_addition(change, old, new, scope):
        r['local_validation'] = 'CLOSED_SCOPE_ADDITION'
        r['reasoning'].append('Full restricted document pair independently proves local addition; upstream review status is preserved.')
    elif change.material_status != 'CHANGED' or change.review_status != 'VERIFIED':
        return _uncertain(r, 'Upstream semantic/review uncertainty is not promoted to applicability.', ['upstream_change_review'])
    truth, trace, missing = evaluate_condition(scope.condition, context)
    r['matched_conditions'] = [x for x in trace if x['result'] is True]
    r['excluded_conditions'] = [x for x in trace if x['result'] is False]
    if truth is None:
        return _uncertain(r, 'A required explicit user fact is missing.', missing)
    r['applicability_status'] = 'APPLIES' if truth else 'DOES_NOT_APPLY'
    r['legacy_applicability'] = 'MATCHED' if truth else 'NOT_MATCHED'
    r['confidence'] = 'DETERMINISTIC_WITHIN_SUPPORTED_RULE'
    r['reasoning'].append('Complete supported condition evaluates ' + str(truth) + ' against user-confirmed facts; exact matching only.')
    r['uncertainty'] = ['Clause-local assessment only; no overall eligibility, compliance or action execution conclusion.']
    r['action_status'] = 'ACTION_REVIEW_REQUIRED' if truth else 'NO_CURRENT_ACTION'
    if truth:
        tasks = scope.task_ids
        # On list additions, do not treat unchanged materials as newly pending.
        material = next((f for f in change.fields if f.kind == 'MATERIAL'), None)
        if material:
            added = set(material.new_value) - set(material.old_value)
            tasks = tuple(t for t in tasks if t.removeprefix('submit:') in added) or ('review:removed_material',)
        for task in tasks:
            if task in context.completed_tasks:
                progress, message = 'COMPLETED_REVIEW', '你已标记完成此事项；请核对已完成内容是否符合新版，勿默认需要重复提交。'
            elif task in context.pending_tasks:
                progress, message = 'PENDING_REVIEW', '你已标记此事项待处理；请根据新旧证据复核相关材料或计划。'
            else:
                progress, message = 'ASK_PROGRESS', '请确认此事项的完成进度，再决定是否调整材料或计划。'
            r['recommended_actions'].append({'change_id': r['change_id'], 'task_id': task,
                'kind': 'HUMAN_REVIEW_ONLY', 'progress_status': progress, 'message': message,
                'requirement': scope.body, 'field_changes': [asdict(f) for f in change.fields],
                'evidence_ref': r['change_id'], 'executes_external_action': False})
    # Return only JSON-native values, with canonical order and no clock/random IDs.
    return json.loads(json.dumps(r, ensure_ascii=False))


def assess_change(change, old, new, context: UserTaskContext):
    if not isinstance(context, UserTaskContext):
        raise TypeError('context must be a validated UserTaskContext')
    comparison = analyze(old, new)
    return json.loads(json.dumps(_assess(change, old, new, context, change in comparison.changes), ensure_ascii=False))


def assess(old, new, context: UserTaskContext):
    """JSON-ready list, one result per changed clause; unchanged clauses omitted.

    If analysis cannot supply changes, return one explicit unresolved record.
    Empty results means no changed clauses, never means the user is compliant.
    """
    if not isinstance(context, UserTaskContext):
        raise TypeError('context must be a validated UserTaskContext')
    comparison = analyze(old, new)
    if comparison.review_status == 'UNVERIFIED' or (not comparison.changes and comparison.review_status == 'NEEDS_REVIEW'):
        return [_uncertain(_base(None, old, new), 'Comparison has no verified analyzable change records.', unverified=comparison.review_status == 'UNVERIFIED')]
    results = [_assess(c, old, new, context, True) for c in comparison.changes
               if c.relation != 'UNCHANGED' or c.material_status != 'UNCHANGED']
    return json.loads(json.dumps(results, ensure_ascii=False))

