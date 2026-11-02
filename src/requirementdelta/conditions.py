"""Bounded full-consumption condition grammar, no eval or fuzzy matching.

NOT > AND > OR. Three-valued evaluation, with contradictions handled separately.
All names and values are exact; no implicit geographical or role hierarchies.
"""
from dataclasses import dataclass
from datetime import date
import re


@dataclass(frozen=True)
class Condition:
    op: str
    field: str = ''
    value: str | bool | tuple[str, str] | None = None
    children: tuple['Condition', ...] = ()


FIELDS = {'赛道': 'track', '类别': 'category', '角色': 'role', '地域': 'region', '进度': 'progress'}
TOKEN = re.compile(r'\s*(?:(?P<eq>赛道|类别|角色|地域|进度)为“(?P<value>[^”\r\n]{1,80})”|'
                   r'条件“(?P<name>[\w\u4e00-\u9fff-]{1,40})”为(?P<bool>真|假)|'
                   r'日期在(?P<start>\d{4}-\d{2}-\d{2})至(?P<end>\d{4}-\d{2}-\d{2})|'
                   r'(?P<op>AND\b|OR\b|NOT\b|且|或|非|\(|\)))')


def parse_condition(text: str) -> Condition:
    if not isinstance(text, str) or not text.strip() or len(text) > 512:
        raise ValueError('condition absent or too long')
    tokens, pos = [], 0
    while pos < len(text.rstrip()):
        m = TOKEN.match(text, pos)
        if not m:
            raise ValueError('unsupported condition syntax')
        pos = m.end()
        if m['eq']:
            token = Condition('EQ', FIELDS[m['eq']], m['value'])
        elif m['name']:
            token = Condition('EQ', 'condition:' + m['name'], m['bool'] == '真')
        elif m['start']:
            a, b = date.fromisoformat(m['start']), date.fromisoformat(m['end'])
            if a > b:
                raise ValueError('reversed date interval')
            token = Condition('RANGE', 'date', (m['start'], m['end']))
        else:
            token = {'且': 'AND', '或': 'OR', '非': 'NOT'}.get(m['op'], m['op'])
        tokens.append(token)
    if len(tokens) > 64:
        raise ValueError('too many condition tokens')
    index = 0

    def primary(depth=0):
        nonlocal index
        if depth > 12 or index >= len(tokens):
            raise ValueError('invalid nesting or missing operand')
        t = tokens[index]
        index += 1
        if t == 'NOT':
            return Condition('NOT', children=(primary(depth + 1),))
        if t == '(':
            result = expression(depth + 1)
            if index >= len(tokens) or tokens[index] != ')':
                raise ValueError('unclosed parentheses')
            index += 1
            return result
        if isinstance(t, Condition):
            return t
        raise ValueError('expected condition')

    def conjunction(depth):
        nonlocal index
        node = primary(depth)
        while index < len(tokens) and tokens[index] == 'AND':
            index += 1
            node = Condition('AND', children=(node, primary(depth)))
        return node

    def expression(depth):
        nonlocal index
        node = conjunction(depth)
        while index < len(tokens) and tokens[index] == 'OR':
            index += 1
            node = Condition('OR', children=(node, conjunction(depth)))
        return node

    result = expression(0)
    if index != len(tokens):
        raise ValueError('unconsumed condition text')
    return result


def evaluate_condition(node, context):
    """Return (true/false/unknown, atomic traces, missing field names)."""
    if node.op in {'EQ', 'RANGE'}:
        values = context.values(node.field)
        if len(values) != 1:
            return None, [{'field': node.field, 'operator': node.op, 'expected': node.value, 'result': None}], [node.field]
        actual = next(iter(values))
        result = actual == node.value if node.op == 'EQ' else node.value[0] <= actual <= node.value[1]
        return result, [{'field': node.field, 'operator': node.op, 'expected': node.value, 'result': result}], []
    outcomes = [evaluate_condition(c, context) for c in node.children]
    vals = [x[0] for x in outcomes]
    trace = [t for x in outcomes for t in x[1]]
    missing = sorted({k for x in outcomes for k in x[2]})
    if node.op == 'NOT':
        result = None if vals[0] is None else not vals[0]
        # Record the exclusion itself, not a misleading positive match.
        trace = [{'operator': 'NOT', 'condition': condition_dict(node.children[0]), 'result': result}]
    elif node.op == 'AND':
        result = False if False in vals else None if None in vals else True
    elif node.op == 'OR':
        result = True if True in vals else None if None in vals else False
    else:
        raise ValueError('unknown condition operator')
    return result, trace, missing


def condition_dict(node):
    return {'operator': node.op, 'field': node.field, 'value': node.value,
            'children': [condition_dict(c) for c in node.children]}


def has_conflict(node):
    """Conservative DNF satisfiability check, bounded to 64 branches.

    A contradictory branch is surfaced even if another OR branch is satisfiable.
    Negated date ranges split into disjoint outside intervals.
    """
    def dnf(n, negate=False):
        if n.op == 'NOT':
            return dnf(n.children[0], not negate)
        if n.op in {'EQ', 'RANGE'}:
            if n.op == 'RANGE' and negate:
                a, b = map(date.fromisoformat, n.value)
                return [[('date_bounds', 'date', (1, a.toordinal() - 1), False)],
                        [('date_bounds', 'date', (b.toordinal() + 1, date.max.toordinal()), False)]]
            value = tuple(date.fromisoformat(x).toordinal() for x in n.value) if n.op == 'RANGE' else n.value
            return [[('date_bounds' if n.op == 'RANGE' else 'EQ', n.field, value, negate)]]
        op = ('OR' if n.op == 'AND' else 'AND') if negate else n.op
        a, b = [dnf(c, negate) for c in n.children]
        branches = a + b if op == 'OR' else [x + y for x in a for y in b]
        if len(branches) > 64:
            raise ValueError('condition complexity exceeds 64 branches')
        return branches

    for branch in dnf(node):
        positives, negatives = {}, {}
        lo, hi = 1, date.max.toordinal()
        for kind, field, value, negate in branch:
            if kind == 'date_bounds':
                lo, hi = max(lo, value[0]), min(hi, value[1])
            elif negate:
                negatives.setdefault(field, set()).add(value)
            else:
                positives.setdefault(field, set()).add(value)
        if lo > hi or any(len(v) > 1 or v & negatives.get(k, set()) for k, v in positives.items()):
            return True
        if any({True, False} <= v for k, v in negatives.items() if k == 'participating' or k.startswith('condition:')):
            return True
    return False

