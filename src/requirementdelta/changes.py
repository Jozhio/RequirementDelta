"""P0-2 bounded requirement-change candidates. No user/action decisions.

CHANGED concerns the supported literal requirement in this excerpt; UNKNOWN
is explicit abstention. Added/deleted clauses are text presence only, never a
claim of worldwide policy creation/repeal. Core has no I/O or dataset access.
"""
from dataclasses import dataclass, replace
from datetime import datetime
import re
from .ingest import DocumentSnapshot
from .evidence import Evidence, verify_evidence
from .segment import segment, match_text
from .align import align, CandidatePair
from .time_rules import bounded_time_change
from .correspondence import Correspondence, find_correspondences


@dataclass(frozen=True)
class FieldChange:
    kind: str
    old_value: tuple[str, ...]
    new_value: tuple[str, ...]
    direction: str = 'NOT_INFERRED'


@dataclass(frozen=True)
class Change:
    relation: str
    material_status: str
    review_status: str
    reason: str
    score: float
    fields: tuple[FieldChange, ...]
    old_evidence: Evidence | None
    new_evidence: Evidence | None
    old_context: tuple[str, ...]
    new_context: tuple[str, ...]


@dataclass(frozen=True)
class Comparison:
    schema_version: str
    text_status: str
    material_status: str
    review_status: str
    old_sha256: str | None
    new_sha256: str | None
    changes: tuple[Change, ...]
    limitations: tuple[str, ...]
    correspondences: tuple[Correspondence, ...] = ()


DATE = re.compile(r'(?:\d{4}年)?\d{1,2}月\d{1,2}日(?:\s*\d{1,2}:\d{2})?|\d{4}-\d{2}-\d{2}(?:[ T]\d{1,2}:\d{2})?')
ZONE = re.compile(r'北京时间|东京时间|Asia/Shanghai|Asia/Tokyo|\bUTC\b')
NUMBER = re.compile(r'\d+(?:\.\d+)?\s*(?:MB|GB|KB|hours?|小时|天|日|%)', re.I)
MODAL = re.compile(r'必须|需要|可选|可以|须|需|\bmust\b|\boptional\b|\bmay\b|\bshould\b', re.I)
FORMAT = re.compile(r'PDF/A|PDF|ZIP|MP4|DOCX', re.I)
RISK = re.compile(r'只有|仅|除非|如果|若|禁止|不(?!得超过)|无|未|所有|资格|青年|辅助|生成|收到|\b(?:not|unless|if|except|only|without|no)\b', re.I)
REQUIREMENT = re.compile(r'截止|提交|上传|上限|不得超过|必须|须|需|必填|\b(?:must|should|may|submit|deadline|hours|disclos\w*)\b', re.I)
MATERIAL = re.compile(r'(?:必须|须|需要|需)提交(?P<items>[^。]+)[。]?$')


def _dates(values: tuple[str, ...]) -> tuple[datetime, ...] | None:
    parsed = []
    for raw in values:
        if not re.match(r'\d{4}(?:年|-)', raw):
            return None
        text = raw.replace('年', '-').replace('月', '-').replace('日', ' ').replace('T', ' ').strip()
        try:
            parsed.append(datetime.strptime(text, '%Y-%m-%d %H:%M' if ':' in text else '%Y-%m-%d'))
        except ValueError:
            return None
    return tuple(parsed)


def _values(pattern, text):
    matches = list(pattern.finditer(text))
    if pattern is NUMBER:
        dates = list(DATE.finditer(text))
        matches = [m for m in matches if not any(m.start() < d.end() and d.start() < m.end() for d in dates)]
    return tuple(m.group() for m in matches)


def _fields(a: str, b: str) -> tuple[tuple[FieldChange, ...], bool]:
    fields = []
    for kind, pattern in [('DATE', DATE), ('TIMEZONE', ZONE), ('NUMBER', NUMBER), ('MODALITY', MODAL), ('FORMAT', FORMAT)]:
        old, new = _values(pattern, a), _values(pattern, b)
        if old != new and (old or new):
            direction = 'NOT_INFERRED'
            if kind == 'DATE' and len(old) == len(new) == 1 and _dates(old) and _dates(new):
                direction = 'EARLIER' if _dates(new)[0] < _dates(old)[0] else 'LATER' if _dates(new)[0] > _dates(old)[0] else 'SAME_LITERAL_DATE'
            fields.append(FieldChange(kind, old, new, direction))
    # Deterministic rule: ONLY one token family changed, same template and count.
    for kind, pattern in [('DATE', DATE), ('TIMEZONE', ZONE), ('NUMBER', NUMBER), ('MODALITY', MODAL), ('FORMAT', FORMAT)]:
        old, new = _values(pattern, a), _values(pattern, b)
        if not old or old == new or len(old) != len(new):
            continue
        if pattern.sub('<VALUE>', a) != pattern.sub('<VALUE>', b):
            continue
        if kind == 'DATE' and (not _dates(old) or not _dates(new)):
            return tuple(fields), False
        if kind == 'NUMBER':
            units = lambda xs: [re.sub(r'[\d.\s]', '', x).lower() for x in xs]
            if units(old) != units(new):
                return tuple(fields), False
        return tuple(fields), True
    # Narrow explicit submission-list grammar, not a bag of material keywords.
    ma, mb = MATERIAL.fullmatch(a), MATERIAL.fullmatch(b)
    if ma and mb and a[:ma.start('items')] == b[:mb.start('items')]:
        def items(m):
            return tuple(re.split(r'，以及|以及|、|及|与|和', m['items'].rstrip('。')))
        ia, ib = items(ma), items(mb)
        if (set(ia) < set(ib) or set(ib) < set(ia)) and all(re.fullmatch(r'[\w\u4e00-\u9fff/]+', x) for x in ia + ib):
            fields.append(FieldChange('MATERIAL', ia, ib))
            return tuple(fields), True
    return tuple(fields), False


def _classify(pair: CandidatePair) -> Change:
    old, new = pair.old, pair.new
    fields: tuple[FieldChange, ...] = ()
    material, status = 'UNKNOWN', 'NEEDS_REVIEW'
    reason = 'Unmatched textual presence only; opposite-side evidence absent. Do not infer global obligation creation/repeal.'
    if pair.ambiguous:
        reason = 'Repeated text; occurrence correspondence is ambiguous.'
    elif old and new:
        a, b = match_text(old.text), match_text(new.text)
        if old.context != new.context:
            reason = 'Heading/context changed; identical wording need not have the same scope.'
        elif pair.relation in {'UNCHANGED', 'POSSIBLE_MOVED'}:
            material, status = 'UNCHANGED', 'VERIFIED'
            reason = 'Exact clause wording modulo list marker/whitespace; no material change detected in this matched clause.'
        elif old.kind in {'heading', 'code'} or new.kind in {'heading', 'code'}:
            reason = 'Heading or code change is not interpreted as a requirement.'
        else:
            fields, supported = _fields(a, b)
            literal_time = bounded_time_change(a, b)
            if literal_time:
                kind, before, after, reason = literal_time
                fields = (FieldChange(kind, (before,), (after,)),)
                material, status = 'CHANGED', 'NEEDS_REVIEW'
            elif RISK.search(a) or RISK.search(b):
                reason = 'Negation, conditional/scope or reference-event ambiguity; literal candidates only.'
            elif supported and REQUIREMENT.search(a + b):
                material, status = 'CHANGED', 'VERIFIED'
                reason = 'Explicit field/list changed with unchanged surrounding object/template; excerpt-level only, no user action inferred.'
            else:
                reason = 'Lexical correspondence only; semantic rewrite, incomplete date or unsupported template requires review.'
    return Change(pair.relation, material, status, reason, pair.score, fields,
                  old.evidence if old else None, new.evidence if new else None,
                  old.context if old else (), new.context if new else ())


def analyze(old: DocumentSnapshot, new: DocumentSnapshot) -> Comparison:
    if old.role != 'old' or new.role != 'new':
        raise ValueError('analyze requires old/new snapshot roles in that order')
    limitations = ('Finite literal rules; not general semantic reasoning or user applicability.',
                   'Single-sided text differences never prove global obligation repeal.',
                   'Similarity scores are lexical, not probabilities.')
    if not old.is_readable or not new.is_readable:
        return Comparison('0.2', 'UNVERIFIED', 'UNKNOWN', 'UNVERIFIED', old.sha256, new.sha256, (),
                          limitations + (f'Input read errors: old={old.error_code}, new={new.error_code}',))
    text_status = 'NO_TEXT_CHANGE' if old.content == new.content else 'TEXT_CHANGE'
    if max(len(old.content), len(new.content)) > 200_000:
        return Comparison('0.2', text_status, 'UNKNOWN', 'NEEDS_REVIEW', old.sha256, new.sha256, (),
                          limitations + ('Analysis limit: 200000 characters per document; no partial certainty.',))
    a, b = segment(old), segment(new)
    if max(len(a), len(b)) > 1000 or len(a) * len(b) > 250_000:
        return Comparison('0.2', text_status, 'UNKNOWN', 'NEEDS_REVIEW', old.sha256, new.sha256, (),
                          limitations + ('Analysis limit: 1000 clauses/document and 250000 candidate pairs; no partial certainty.',))
    pairs = align(a, b)
    changes = tuple(_classify(pair) for pair in pairs)
    if re.search(r'按顺序|依次|先.*再|\bin order\b|\bsequence\b', old.content + '\n' + new.content, re.I):
        changes = tuple(replace(c, material_status='UNKNOWN', review_status='NEEDS_REVIEW',
                                reason='Explicit sequence context: reordering may change required execution order.')
                        if c.relation == 'POSSIBLE_MOVED' else c for c in changes)
    # Mandatory use of the P0-1 verifier: invalid evidence fails the whole run closed.
    for change in changes:
        for snapshot, evidence in [(old, change.old_evidence), (new, change.new_evidence)]:
            if evidence is not None and not verify_evidence(snapshot, evidence):
                return Comparison('0.2', 'UNVERIFIED', 'UNKNOWN', 'UNVERIFIED', old.sha256, new.sha256, (), limitations + ('Evidence validation failed.',))
    try:
        paired_spans = tuple((p.old.evidence, p.new.evidence) for p in pairs if p.old and p.new)
        correspondences = find_correspondences(old, new, paired_spans)
    except ValueError:
        return Comparison('0.2', 'UNVERIFIED', 'UNKNOWN', 'UNVERIFIED', old.sha256, new.sha256, (), limitations + ('Correspondence evidence validation failed.',))
    for link in correspondences:
        if not verify_evidence(old, link.old_evidence) or not verify_evidence(new, link.new_evidence):
            return Comparison('0.2', 'UNVERIFIED', 'UNKNOWN', 'UNVERIFIED', old.sha256, new.sha256, (), limitations + ('Correspondence evidence validation failed.',))
    unknown = not a or not b or any(c.material_status == 'UNKNOWN' for c in changes)
    changed = any(c.material_status == 'CHANGED' for c in changes)
    material = 'CHANGED' if changed else 'UNKNOWN' if unknown else 'UNCHANGED'
    status = 'NEEDS_REVIEW' if unknown or any(c.review_status == 'NEEDS_REVIEW' for c in changes) or correspondences else 'VERIFIED'
    return Comparison('0.2', text_status,
                      material, status, old.sha256, new.sha256, changes, limitations, correspondences)
