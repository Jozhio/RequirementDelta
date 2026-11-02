from dataclasses import asdict
from pathlib import Path
import pytest
from requirementdelta.ingest import read_pair
from requirementdelta.evidence import verify_evidence
from requirementdelta.changes import analyze


def run(tmp_path, old, new):
    (tmp_path/'old.md').write_bytes(old.encode('utf-8'))
    (tmp_path/'new.md').write_bytes(new.encode('utf-8'))
    snapshots = read_pair('old.md', 'new.md', tmp_path)
    result = analyze(*snapshots)
    for change in result.changes:
        for snap, evidence in zip(snapshots, [change.old_evidence, change.new_evidence]):
            if evidence is not None:
                assert verify_evidence(snap, evidence)
    return result


def test_exact_unchanged(tmp_path):
    r=run(tmp_path,'须提交报告。','须提交报告。')
    assert r.text_status=='NO_TEXT_CHANGE'
    assert r.material_status=='UNCHANGED'


def test_reorder_not_delete_add(tmp_path):
    r=run(tmp_path,'一、提交报告。二、提交代码。','一、提交代码。二、提交报告。')
    assert {c.relation for c in r.changes}=={'POSSIBLE_MOVED'}
    assert r.material_status=='UNCHANGED'


def test_insert_does_not_mark_all_later_items_moved(tmp_path):
    r=run(tmp_path,'提交报告。\n提交代码。','提交视频。\n提交报告。\n提交代码。')
    assert not any(c.relation=='POSSIBLE_MOVED' for c in r.changes)
    assert any(c.relation=='ADDED' and c.old_evidence is None for c in r.changes)


def test_duplicates_not_arbitrarily_matched(tmp_path):
    r=run(tmp_path,'提交报告。\n提交报告。','提交报告。')
    assert r.review_status=='NEEDS_REVIEW'
    assert all(c.material_status!='CHANGED' for c in r.changes)


@pytest.mark.parametrize('old,new,kind',[
    ('截止2027年2月8日18:00。','截止2027年2月3日18:00。','DATE'),
    ('文件不得超过90 MB。','文件不得超过35 MB。','NUMBER'),
    ('演示视频可选提交。','演示视频必须提交。','MODALITY'),
    ('必须提交报告PDF。','必须提交报告PDF及代码ZIP。','MATERIAL'),
    ('报告需提交PDF格式。','报告需提交PDF/A格式。','FORMAT'),
    ('截止2027年2月8日18:00（北京时间）。','截止2027年2月8日18:00（东京时间）。','TIMEZONE'),
])
def test_supported_changes(tmp_path,old,new,kind):
    r=run(tmp_path,old,new)
    assert r.material_status=='CHANGED'
    assert any(f.kind==kind for c in r.changes for f in c.fields)


def test_date_direction(tmp_path):
    r=run(tmp_path,'截止2027-02-08 18:00。','截止2027-02-03 18:00。')
    assert any(f.direction=='EARLIER' for c in r.changes for f in c.fields)


@pytest.mark.parametrize('old,new',[
    ('允许AI辅助完成作品。','禁止AI生成参赛作品。'),
    ('所有队伍须提交视频。','只有决赛队伍须提交视频。'),
    ('须提交报告。','不必提交报告。'),
    ('标题：创新赛。','标题：青年创新赛。'),
    ('材料齐全即可。','请确保全部证明均已备妥。'),
    ('截止11月1日之前。','截止10月31日23:59。'),
    ('截止2027年2月28日。','截止2027年2月30日。'),
])
def test_ambiguity_abstains(tmp_path,old,new):
    r=run(tmp_path,old,new)
    assert r.review_status=='NEEDS_REVIEW'
    assert r.material_status=='UNKNOWN'


def test_deleted_requirement_not_global_repeal(tmp_path):
    r=run(tmp_path,'须提交盖章表。\n须提交报告。','须提交报告。')
    c=next(c for c in r.changes if c.relation=='DELETED')
    assert c.new_evidence is None and c.old_evidence
    assert c.review_status=='NEEDS_REVIEW'
    assert c.material_status=='UNKNOWN'


def test_context_change_not_silent_no_change(tmp_path):
    r=run(tmp_path,'# 本科生\n须提交报告。','# 全体学生\n须提交报告。')
    assert r.material_status=='UNKNOWN'
    assert r.review_status=='NEEDS_REVIEW'


def test_numeric_table_attribution(tmp_path):
    r=run(tmp_path,'| Project | Hours |\n| Alpha | 350 hours |\n| Beta | 90 hours |',
        '| Project | Hours |\n| Alpha | 175 hours |\n| Beta | 90 hours |')
    changed=[c for c in r.changes if c.material_status=='CHANGED']
    assert len(changed)==1
    assert 'Alpha' in changed[0].old_evidence.quote
    assert 'Beta' not in changed[0].new_evidence.quote


def test_two_events_only_correct_date_changes(tmp_path):
    r=run(tmp_path,'提问截止2027年1月2日；报名截止2027年1月8日。',
        '提问截止2027年1月4日；报名截止2027年1月8日。')
    changed=[c for c in r.changes if c.material_status=='CHANGED']
    assert len(changed)==1 and '提问' in changed[0].old_evidence.quote


def test_unreadable_has_no_changes(tmp_path):
    (tmp_path/'old.md').write_text('ok',encoding='utf-8')
    r=analyze(*read_pair('old.md','missing.md',tmp_path))
    assert r.review_status=='UNVERIFIED' and not r.changes
    assert r.text_status=='UNVERIFIED'


def test_empty_not_semantically_safe(tmp_path):
    r=run(tmp_path,'','')
    assert r.review_status=='NEEDS_REVIEW'
    assert r.material_status=='UNKNOWN'


def test_result_reproducible_and_no_action_fields(tmp_path):
    r=run(tmp_path,'上限10 MB。','上限20 MB。')
    again=analyze(*read_pair('old.md','new.md',tmp_path))
    assert asdict(r)==asdict(again)
    assert 'action_status' not in str(asdict(r))
