"""Additional adversarial synthetic tests, separate from core scenarios."""
from pathlib import Path
from dataclasses import replace
import pytest
from requirementdelta.ingest import read_pair
from requirementdelta.changes import analyze
from requirementdelta.applicability import assess, assess_change
from requirementdelta.conditions import parse_condition, has_conflict, evaluate_condition
from requirementdelta.task_context import UserTaskContext, Fact
from test_applicability import context, texts, pair, run


@pytest.mark.parametrize('expression', [
    '非(条件“报名”为真)且非(条件“报名”为假)',
    '日期在2030-01-01至2030-01-02且日期在2030-02-01至2030-02-02',
    '日期在2030-01-01至2030-01-02且非(日期在2030-01-01至2030-01-02)',
    '非(赛道为“A”或赛道为“B”)且赛道为“A”',
])
def test_source_logical_conflicts(expression):
    assert has_conflict(parse_condition(expression))


@pytest.mark.parametrize('expression', ['非(赛道为“A”且赛道为“B”)', '非(日期在2030-01-01至2030-01-02)'])
def test_noncontradictory_negations(expression):
    assert not has_conflict(parse_condition(expression))


@pytest.mark.parametrize('expression', ['赛道为“A”xxx', '赛道为“A”且', '()', 'NOT', '(', '赛道为“A” OR OR 赛道为“B”', '('*15+'赛道为“A”'+')'*15])
def test_invalid_grammar_rejected(expression):
    with pytest.raises(ValueError):
        parse_condition(expression)


@pytest.mark.parametrize('expression', ['赛道为“A” OR 角色为“导师”', '赛道为“A”或角色为“导师”'])
def test_or_true_does_not_need_irrelevant_fact(expression):
    ctx = UserTaskContext.from_dict(context(track='A'))
    truth, _, _ = evaluate_condition(parse_condition(expression), ctx)
    assert truth is True


def test_changed_scope_is_not_promoted(tmp_path):
    a = '项目“星辰”的参与者（赛道为“A”）必须提交PDF。'
    b = '项目“星辰”的参与者（赛道为“B”）必须提交PDF。'
    r, _ = run(tmp_path, context(project='星辰', participating=True, track='B'), text_pair=(a,b))
    assert r['applicability_status'] == 'NEEDS_CONFIRMATION'
    assert not r['recommended_actions']


def test_scope_heading_context_not_ignored(tmp_path):
    a,b = texts()
    rs = assess(*pair(tmp_path, '# 决赛参与者\n'+a, '# 决赛参与者\n'+b), UserTaskContext.from_dict(context(project='星辰', participating=True)))
    assert all(r['applicability_status'] == 'INSUFFICIENT_CONTEXT' for r in rs)


@pytest.mark.parametrize('old,new', [
    ('# 项目“星辰”\n例外未列明。', '# 项目“星辰”\n例外未列明。\n项目“星辰”的参与者必须提交报告。'),
    ('# 项目“星辰”\n项目“星辰”的参与者必须提交代码。', '# 项目“星辰”\n项目“星辰”的参与者必须提交报告。'),
    ('# 项目“星辰”', '# 项目“星辰”\n项目“星辰”的参与者必须提交报告。\n项目“星辰”的参与者必须提交报告。'),
])
def test_closed_addition_rejects_exceptions_removals_duplicates(tmp_path, old, new):
    rs = assess(*pair(tmp_path, old,new), UserTaskContext.from_dict(context(project='星辰',participating=True)))
    assert all(r['local_validation'] != 'CLOSED_SCOPE_ADDITION' for r in rs)


def test_completed_old_format_not_claimed_new_format_done(tmp_path):
    ctx = context(project='星辰', participating=True)
    ctx['completed_tasks'] = ['submit:PDF']
    r,_ = run(tmp_path,ctx)
    assert r['recommended_actions'][0]['progress_status'] == 'ASK_PROGRESS'


def test_added_material_does_not_recommend_unchanged_material(tmp_path):
    a = '项目“星辰”的参与者必须提交报告。'
    b = '项目“星辰”的参与者必须提交报告、代码。'
    rs=assess(*pair(tmp_path,a,b),UserTaskContext.from_dict(context(project='星辰',participating=True)))
    # Upstream narrow list grammar may not support scoped lists; never promote.
    assert all(not r['recommended_actions'] or [x['task_id'] for x in r['recommended_actions']]==['submit:代码'] for r in rs)


@pytest.mark.parametrize('bad', [
    lambda: UserTaskContext(True, (Fact('participating', 1),)),
    lambda: UserTaskContext(True, (Fact('project', []),)),
    lambda: UserTaskContext(True, (), 'submit:PDF'),
    lambda: UserTaskContext(True, (Fact('date', '2026-2-1'),)),
])
def test_direct_dataclass_cannot_bypass_validation(bad):
    with pytest.raises(ValueError):
        bad()




def test_table_without_header_is_not_project_evidence(tmp_path):
    rs=assess(*pair(tmp_path,'| Example | link | Description | 350 hours |','| Example | link | Description | 175 hours |'),UserTaskContext.from_dict(context(project='Example',participating=True)))
    assert rs[0]['applicability_status']=='INSUFFICIENT_CONTEXT'


def test_participation_false_without_project_cannot_exclude(tmp_path):
    r,_=run(tmp_path,context(participating=False))
    assert r['applicability_status']=='NEEDS_CONFIRMATION'
    assert 'project' in r['missing_information']


def test_whitespace_project_name_cannot_create_false_exclusion():
    with pytest.raises(ValueError):
        UserTaskContext.from_dict(context(project=' 星辰 ',participating=True))


def test_scope_contradiction_conflict_and_trace_json_native(tmp_path):
    import json
    r,_=run(tmp_path,context(project='星辰',participating=True), '日期在2030-01-01至2030-01-05')
    assert json.loads(json.dumps(r,ensure_ascii=False))==r


def test_evidence_validation_explicit_flag(tmp_path):
    r,_=run(tmp_path,context(project='星辰',participating=True))
    assert r['evidence_status']=='VERIFIED'


