"""Deterministic one-to-one candidates; similarity is NOT semantic confidence."""
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from .segment import Clause, match_text


@dataclass(frozen=True)
class CandidatePair:
    old: Clause | None
    new: Clause | None
    relation: str
    score: float
    ambiguous: bool = False


def _score(a: Clause, b: Clause) -> float:
    if a.kind != b.kind:
        return 0.0
    if a.kind == 'table':
        # Object attribution is mandatory; never borrow a different table row.
        if a.text.strip('| ').split('|')[0].strip() != b.text.strip('| ').split('|')[0].strip():
            return 0.0
    return SequenceMatcher(None, match_text(a.text), match_text(b.text), autojunk=False).ratio()


def align(old: tuple[Clause, ...], new: tuple[Clause, ...]) -> tuple[CandidatePair, ...]:
    keys_a = [match_text(c.text) for c in old]
    keys_b = [match_text(c.text) for c in new]
    counts_a, counts_b = Counter(keys_a), Counter(keys_b)
    repeated = {key for key in counts_a.keys() | counts_b.keys() if counts_a[key] > 1 or counts_b[key] > 1}
    used_a, used_b, pairs = set(), set(), []
    new_keys = {key: j for j, key in enumerate(keys_b) if key not in repeated}
    exact = []
    for i, key in enumerate(keys_a):
        if key not in repeated and key in new_keys and old[i].kind == new[new_keys[key]].kind:
            j = new_keys[key]
            exact.append((i, j))
            used_a.add(i)
            used_b.add(j)
    for i, j in exact:
        moved = any((i - x) * (j - y) < 0 for x, y in exact)
        pairs.append(CandidatePair(old[i], new[j], 'POSSIBLE_MOVED' if moved else 'UNCHANGED', 1.0))
    remaining_a = [i for i in range(len(old)) if i not in used_a and keys_a[i] not in repeated]
    remaining_b = [j for j in range(len(new)) if j not in used_b and keys_b[j] not in repeated]
    scores = {(i, j): _score(old[i], new[j]) for i in remaining_a for j in remaining_b}
    for i in remaining_a:
        ranked = sorted(((scores[i, j], j) for j in remaining_b), reverse=True)
        if not ranked or ranked[0][0] < .52:
            continue
        score, j = ranked[0]
        reverse = sorted(((scores[x, j], x) for x in remaining_a), reverse=True)
        if reverse[0][1] != i or j in used_b:
            continue
        if (len(ranked) > 1 and score - ranked[1][0] < .06) or (len(reverse) > 1 and score - reverse[1][0] < .06):
            continue
        used_a.add(i)
        used_b.add(j)
        pairs.append(CandidatePair(old[i], new[j], 'MODIFIED', round(score, 6)))
    pairs.extend(CandidatePair(c, None, 'DELETED', 0.0, keys_a[i] in repeated) for i, c in enumerate(old) if i not in used_a)
    pairs.extend(CandidatePair(None, c, 'ADDED', 0.0, keys_b[j] in repeated) for j, c in enumerate(new) if j not in used_b)
    return tuple(sorted(pairs, key=lambda p: (p.old.index if p.old else len(old) + p.new.index, p.new.index if p.new else -1)))
