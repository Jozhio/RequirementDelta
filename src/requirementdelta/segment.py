"""Traceable clause candidates, not a complete Markdown/semantic parser."""
from dataclasses import dataclass
import re
from .ingest import DocumentSnapshot
from .evidence import Evidence, build_evidence, verify_evidence, UnreadableSnapshotError


@dataclass(frozen=True)
class Clause:
    index: int
    text: str
    context: tuple[str, ...]
    kind: str
    evidence: Evidence


def match_text(text: str) -> str:
    """Matching copy only. Never use it as evidence or remove semantic words."""
    text = re.sub(r'^\s*(?:[-*+]\s+|\d+[.)]\s+|[一二三四五六七八九十]+、)', '', text)
    return re.sub(r'\s+', ' ', text).strip().rstrip('。；;')


def segment(snapshot: DocumentSnapshot) -> tuple[Clause, ...]:
    if not snapshot.is_readable:
        raise UnreadableSnapshotError(snapshot)
    text = snapshot.content or ''
    result = []
    headings: list[tuple[int, str]] = []
    fenced = False
    for line in re.finditer(r'[^\r\n]+', text):
        body = line.group()
        stripped = body.strip()
        if not stripped:
            continue
        heading = re.match(r'^[\s\ufeff]*(#{1,6})\s+(.+)', body)
        kind = 'text'
        if stripped.startswith(('```', '~~~')):
            fenced = not fenced
            kind = 'code'
        elif fenced:
            kind = 'code'
        elif heading:
            kind = 'heading'
            level = len(heading[1])
            headings = [(n, h) for n, h in headings if n < level]
        elif '|' in body and body.count('|') >= 2:
            kind = 'table'
        spans = [(0, len(body))] if kind != 'text' else [(m.start(), m.end()) for m in re.finditer(r'[^。；;]+[。；;]?', body)]
        for start, end in spans:
            while start < end and body[start].isspace():
                start += 1
            while end > start and body[end - 1].isspace():
                end -= 1
            if start == end:
                continue
            evidence = build_evidence(snapshot, line.start() + start, line.start() + end)
            if not verify_evidence(snapshot, evidence):
                raise ValueError('segment evidence failed verification')
            result.append(Clause(len(result), evidence.quote, tuple(h for _, h in headings), kind, evidence))
        if heading:
            headings.append((len(heading[1]), heading[2].strip()))
    return tuple(result)
