from pathlib import Path
import pytest
from requirementdelta.ingest import read_pair
from requirementdelta.evidence import verify_evidence
from requirementdelta.changes import analyze


def compare(tmp_path, a, b):
    for role,text in [('old',a),('new',b)]:
        (tmp_path/(role+'.md')).write_bytes(text.encode('utf-8'))
    snaps=read_pair('old.md','new.md',tmp_path)
    result=analyze(*snaps)
    for change in result.changes:
        for snap,key in zip(snaps,['old_evidence','new_evidence']):
            evidence=getattr(change,key)
            if evidence: assert verify_evidence(snap,evidence)
    return result,snaps


@pytest.mark.parametrize('unit',['日','天','小时'])
@pytest.mark.parametrize('a,b',[(12,9),(2,15)])
def test_relative_duration_change_retains_calendar_review(tmp_path,unit,a,b):
    result,_=compare(tmp_path,f'应于收到录用通知后{a}{unit}内提交。',f'应于收到录用通知后{b}{unit}内提交。')
    assert result.material_status=='CHANGED'
    assert result.review_status=='NEEDS_REVIEW'
    fields=[f for c in result.changes for f in c.fields]
    assert any(f.kind=='DURATION' and f.old_value==(f'{a}{unit}',) and f.new_value==(f'{b}{unit}',) for f in fields)
    assert all(f.direction=='NOT_INFERRED' for f in fields)


@pytest.mark.parametrize('old,new',[
    ('应于收到通知后8日内提交。','应于收到合同后4日内提交。'),
    ('如果收到通知后8日内提交。','如果收到通知后4日内提交。'),
    ('不要求收到通知后8日内提交。','不要求收到通知后4日内提交。'),
    ('应于收到通知后8日内提交。','应于收到通知后4小时内提交。'),
    ('应于收到通知后0日内提交。','应于收到通知后4日内提交。'),
    ('应于收到通知后-8日内提交。','应于收到通知后4日内提交。'),
    ('应于收到通知后8.5日内提交。','应于收到通知后4日内提交。'),
])
def test_relative_duration_unsupported_forms_abstain(tmp_path,old,new):
    r,_=compare(tmp_path,old,new)
    assert r.material_status=='UNKNOWN'
    assert r.review_status=='NEEDS_REVIEW'


@pytest.mark.parametrize('a,b',[('4月2日','4月6日'),('12月30日','1月2日'),('8月9日16:00','8月9日12:00')])
def test_partial_date_literal_change_not_absolute_comparison(tmp_path,a,b):
    r,_=compare(tmp_path,f'咨询截止{a}；报名截止8月20日。',f'咨询截止{b}；报名截止8月20日。')
    assert r.material_status=='CHANGED' and r.review_status=='NEEDS_REVIEW'
    changed=[c for c in r.changes if c.material_status=='CHANGED']
    assert len(changed)==1 and '咨询' in changed[0].old_evidence.quote
    assert [f.kind for f in changed[0].fields]==['DATE']
    assert changed[0].fields[0].direction=='NOT_INFERRED'


@pytest.mark.parametrize('a,b',[
    ('2月28日','2月30日'),('2月28日','2月29日'),('4月30日','4月31日'),
    ('1月2日','13月2日'),('1月2日17:00','1月2日25:00'),
    ('2028年1月2日','1月3日'),('1月2日之前','1月3日23:59前'),
])
def test_partial_date_invalid_or_incompatible_is_unknown(tmp_path,a,b):
    r,_=compare(tmp_path,'咨询截止'+a+'。','咨询截止'+b+'。')
    assert r.material_status=='UNKNOWN'


def test_full_dates_not_double_counted_as_numbers(tmp_path):
    r,_=compare(tmp_path,'截止2030年6月20日。','截止2030年6月18日。')
    assert r.material_status=='CHANGED'
    assert [f.kind for c in r.changes for f in c.fields]==['DATE']


def test_cross_paragraph_literal_obligation_link_is_review_only(tmp_path):
    phrase='Applicants must submit a signed declaration.'
    old='# Introduction\nWelcome to the program. '+phrase+' Other terms apply.'
    new='# Introduction\nWelcome to the program. Other terms apply.\n# Appendix\n'+phrase+' Ask the office about exemptions.'
    r,snaps=compare(tmp_path,old,new)
    assert len(r.correspondences)==1
    link=r.correspondences[0]
    assert link.relation=='POSSIBLE_MOVED'
    assert link.review_status=='NEEDS_REVIEW'
    assert link.old_evidence.quote==link.new_evidence.quote==phrase
    assert verify_evidence(snaps[0],link.old_evidence)
    assert verify_evidence(snaps[1],link.new_evidence)
    assert r.material_status=='UNKNOWN'


@pytest.mark.parametrize('variant',['duplicate','negated','changed'])
def test_cross_paragraph_no_forced_semantic_link(tmp_path,variant):
    phrase='Applicants must submit a signed declaration.'
    old='Background. '+phrase+' End.'
    new={'duplicate':phrase+'\n'+phrase,'negated':'It is not true that '+phrase,
         'changed':'Applicants must submit a different declaration.'}[variant]
    r,_=compare(tmp_path,old,new)
    assert r.correspondences==()


@pytest.mark.parametrize('mode',['fenced','quoted_duplicate'])
def test_correspondence_excludes_code_and_nonunique_source(tmp_path,mode):
    phrase='Applicants must submit a signed declaration.'
    if mode=='fenced':
        old='```text\nBackground. '+phrase+' End.\n```'
        new='```text\n'+phrase+' Revised notes.\n```'
    else:
        old='Background. '+phrase+' End.\n> '+phrase
        new=phrase+' Revised notes.'
    r,_=compare(tmp_path,old,new)
    assert r.correspondences==()


def test_already_aligned_paragraph_does_not_get_redundant_move_link(tmp_path):
    phrase='Applicants must submit a signed declaration.'
    r,_=compare(tmp_path,'Intro revised last week. '+phrase+' Contact the office.',
               'Intro revised this week. '+phrase+' Contact the office.')
    assert r.correspondences==()
