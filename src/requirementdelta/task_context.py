"""Minimal, explicitly supplied task facts. Unknown never means false."""
from dataclasses import dataclass
from datetime import date
import re

TEXT_FIELDS = frozenset({'project', 'role', 'track', 'category', 'region', 'progress'})


@dataclass(frozen=True)
class Fact:
    field: str
    value: str | bool | None


@dataclass(frozen=True)
class UserTaskContext:
    confirmed_by_user: bool
    facts: tuple[Fact, ...] = ()
    completed_tasks: tuple[str, ...] = ()
    pending_tasks: tuple[str, ...] = ()
    schema_version: str = '0.3'

    def __post_init__(self):
        if self.schema_version != '0.3' or type(self.confirmed_by_user) is not bool:
            raise ValueError('schema_version 0.3 and boolean confirmation required')
        if not isinstance(self.facts, tuple) or len(self.facts) > 64:
            raise ValueError('facts must be a tuple of at most 64 explicit assertions')
        for fact in self.facts:
            if not isinstance(fact, Fact):
                raise ValueError('expected Fact')
            k, v = fact.field, fact.value
            if not isinstance(k, str):
                raise ValueError('fact field must be text')
            boolean = k == 'participating' or bool(re.fullmatch(r'condition:[\w\u4e00-\u9fff-]{1,40}', k))
            if k not in TEXT_FIELDS and k != 'date' and not boolean:
                raise ValueError('unsupported fact field')
            if v is None:
                continue
            if boolean:
                if type(v) is not bool:
                    raise ValueError('boolean facts accept true/false/null only')
            elif not isinstance(v, str) or not v.strip() or v != v.strip() or len(v) > 256:
                raise ValueError('text facts must be nonempty strings <=256 characters')
            elif k == 'date':
                if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', v):
                    raise ValueError('date must be ISO YYYY-MM-DD')
                date.fromisoformat(v)
        for tasks in (self.completed_tasks, self.pending_tasks):
            if not isinstance(tasks, tuple) or len(tasks) > 128 or any(
                not isinstance(t, str) or not t.strip() or len(t) > 256 for t in tasks
            ):
                raise ValueError('task IDs must be tuples of <=128 nonempty strings')

    @classmethod
    def from_dict(cls, data):
        allowed = {'schema_version', 'confirmed_by_user', 'facts', 'completed_tasks', 'pending_tasks'}
        if not isinstance(data, dict) or set(data) - allowed:
            raise ValueError('unsupported context keys; identity/credentials are not accepted')
        raw = data.get('facts', [])
        if not isinstance(raw, list) or any(not isinstance(f, dict) or set(f) != {'field', 'value'} for f in raw):
            raise ValueError('facts must be a list of field/value assertions')
        completed, pending = data.get('completed_tasks', []), data.get('pending_tasks', [])
        if not isinstance(completed, list) or not isinstance(pending, list):
            raise ValueError('task lists must be JSON arrays')
        return cls(data.get('confirmed_by_user', False), tuple(Fact(**f) for f in raw),
                   tuple(completed), tuple(pending), data.get('schema_version', '0.3'))

    def values(self, key):
        return frozenset(f.value for f in self.facts if f.field == key and f.value is not None)

    def conflicts(self):
        keys = sorted({f.field for f in self.facts if len(self.values(f.field)) > 1})
        return keys + ['task:' + t for t in sorted(set(self.completed_tasks) & set(self.pending_tasks))]

