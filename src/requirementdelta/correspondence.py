"""Exact unique obligation-sentence links inside changed paragraphs.

Advisory evidence only: surrounding conditions may differ. This does not alter
the clause alignment or establish semantic equivalence/global policy status.
"""
from collections import defaultdict
from dataclasses import dataclass
import re
from .ingest import DocumentSnapshot
from .evidence import Evidence, build_evidence, verify_evidence


@dataclass(frozen=True)
class Correspondence:
    relation: str
    review_status: str
    reason: str
    old_evidence: Evidence
    new_evidence: Evidence


_OBLIGATION = re.compile(r'\b(?:must|shall|should|required)\b|必须|须提交|需提交', re.I)
_BREAK = re.compile(r'[。！？]|[.!?](?=[ \t]+[A-Z])')


def _sentences(snapshot):
    result = defaultdict(list)
    fenced = False
    for line in re.finditer(r'[^\r\n]+', snapshot.content):
        body = line.group()
        if body.lstrip().startswith(('```', '~~~')):
            fenced = not fenced
            continue
        if fenced:
            continue
        if body.lstrip().startswith(('#', '>', '|', '```', '~~~')):
            continue
        start = 0
        spans = []
        for match in _BREAK.finditer(body):
            spans.append((start, match.end()))
            start = match.end()
        if start < len(body):
            spans.append((start, len(body)))
        for start, end in spans:
            while start < end and body[start].isspace():
                start += 1
            while end > start and body[end - 1].isspace():
                end -= 1
            quote = body[start:end]
            if len(quote) >= 12 and _OBLIGATION.search(quote):
                result[quote].append((line.start() + start, line.start() + end, body.strip()))
    return result


def find_correspondences(old: DocumentSnapshot, new: DocumentSnapshot,
                         paired_spans: tuple[tuple[Evidence, Evidence], ...] = ()) -> tuple[Correspondence, ...]:
    if not old.is_readable or not new.is_readable:
        return ()
    a, b = _sentences(old), _sentences(new)
    links = []
    for quote in sorted(a.keys() & b.keys()):
        if len(a[quote]) != 1 or len(b[quote]) != 1:
            continue
        if old.content.count(quote) != 1 or new.content.count(quote) != 1:
            continue
        x, y = a[quote][0], b[quote][0]
        if x[2] == y[2]:
            continue
        if any(left.char_start <= x[0] < x[1] <= left.char_end and
               right.char_start <= y[0] < y[1] <= right.char_end for left, right in paired_spans):
            continue  # Already explained by the main clause correspondence.
        ea, eb = build_evidence(old, x[0], x[1]), build_evidence(new, y[0], y[1])
        if not verify_evidence(old, ea) or not verify_evidence(new, eb):
            raise ValueError('correspondence evidence failed verification')
        links.append(Correspondence('POSSIBLE_MOVED', 'NEEDS_REVIEW',
                    'Unique exact obligation sentence in different paragraph contexts; review surrounding conditions. Not semantic equivalence.', ea, eb))
    return tuple(links)
