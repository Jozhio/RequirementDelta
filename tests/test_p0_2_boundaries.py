from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import pytest
from requirementdelta.ingest import read_pair
from requirementdelta.evidence import verify_evidence
from requirementdelta.segment import segment
from requirementdelta.changes import analyze


def inputs(tmp_path, old, new):
    for role, text in [('old',old),('new',new)]:
        (tmp_path/(role+'.md')).write_bytes(text.encode('utf-8'))
    return read_pair('old.md','new.md',tmp_path)


@pytest.mark.parametrize('old,new',[
    ('并非必须提交PDF。','必须提交ZIP。'),
    ('必须提交未经签名的报告。','必须提交报告。'),
    ('不要求提交PDF。','不要求提交ZIP。'),
    ('须提交无水印PDF。','须提交PDF。'),
    ('must not submit PDF','must not submit ZIP'),
    ('Submission limit is 5 MB unless exempt','Submission limit is 8 MB unless exempt'),
])
def test_negation_and_exceptions_never_automatic(tmp_path, old,new):
    result=analyze(*inputs(tmp_path,old,new))
    assert result.material_status=='UNKNOWN'
    assert result.review_status=='NEEDS_REVIEW'


def test_duplicate_candidates_keep_each_explicit_span(tmp_path):
    old,new=inputs(tmp_path,'重复\n重复','重复\n重复\n重复')
    result=analyze(old,new)
    starts=[c.old_evidence.char_start for c in result.changes if c.old_evidence]
    assert starts==[0,3]
    assert result.review_status=='NEEDS_REVIEW'


def test_traceable_segments_with_unicode_and_line_endings(tmp_path):
    old,_=inputs(tmp_path,'\ufeff# 标题\r\n- 截止2028年2月8日；提交😀报告。\r末行','x')
    clauses=segment(old)
    for c in clauses:
        assert verify_evidence(old,c.evidence)
        assert old.content[c.evidence.char_start:c.evidence.char_end]==c.text
    assert clauses[1].context==('标题',)


def test_forged_evidence_fails_closed(tmp_path,monkeypatch):
    old,new=inputs(tmp_path,'上限10 MB。','上限15 MB。')
    monkeypatch.setattr('requirementdelta.changes.verify_evidence',lambda *args: False)
    result=analyze(old,new)
    assert result.review_status=='UNVERIFIED'
    assert not result.changes


def test_swap_roles_rejected(tmp_path):
    old,new=inputs(tmp_path,'a','b')
    with pytest.raises(ValueError):
        analyze(new,old)


def test_engine_is_readonly_and_deterministic(tmp_path):
    old,new=inputs(tmp_path,'上限10 MB。','上限15 MB。')
    before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in tmp_path.iterdir()}
    assert asdict(analyze(old,new))==asdict(analyze(old,new))
    assert before=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in tmp_path.iterdir()}


def test_identical_table_labels_are_not_crossmatched(tmp_path):
    old,new=inputs(tmp_path,'| Alpha | 90 hours |','| Beta | 70 hours |')
    assert analyze(old,new).material_status=='UNKNOWN'


def test_incomplete_date_retains_candidate_not_calendar_decision(tmp_path):
    old,new=inputs(tmp_path,'提问截止3月2日；报名截止3月8日。','提问截止3月4日；报名截止3月8日。')
    result=analyze(old,new)
    assert result.review_status=='NEEDS_REVIEW'
    changed=[c for c in result.changes if c.fields]
    assert len(changed)==1 and '提问' in changed[0].old_evidence.quote
    assert all(f.direction=='NOT_INFERRED' for f in changed[0].fields)


def test_explicit_sequence_requirement_makes_reorder_uncertain(tmp_path):
    old,new=inputs(tmp_path,'请按顺序完成：\n提交报告；提交代码。','请按顺序完成：\n提交代码；提交报告。')
    result=analyze(old,new)
    assert result.material_status=='UNKNOWN'
    assert result.review_status=='NEEDS_REVIEW'


def test_large_candidate_set_abstains_before_quadratic_matching(tmp_path):
    old,new=inputs(tmp_path,'\n'.join(f'项目{i}说明。' for i in range(1001)), '新的说明')
    result=analyze(old,new)
    assert result.material_status=='UNKNOWN'
    assert result.review_status=='NEEDS_REVIEW'
    assert any('limit' in text.lower() for text in result.limitations)




