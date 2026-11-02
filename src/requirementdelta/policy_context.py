"""PolicyContext 0.4: explicit document-level context for P0-3.2.

This is additive. The existing 0.3 UserTaskContext and its API are unchanged.
Unknown is never false; missing program/role/facts stay unknown.
"""
from __future__ import annotations

from dataclasses import dataclass

from .task_context import Fact, UserTaskContext


@dataclass(frozen=True)
class PolicyContext:
    """User-confirmed context for one document-level policy assessment.

    ``program`` is the exact program/activity name from the document heading.
    No alias, abbreviation, case folding, or substring matching is performed.
    ``role`` is an optional exact role token; it is only used when the source
    scope names a specific role (e.g. Applicants). Generic ``Participants``
    scopes use the explicit ``participating`` boolean fact.
    """

    confirmed_by_user: bool
    facts: tuple[Fact, ...] = ()
    completed_tasks: tuple[str, ...] = ()
    pending_tasks: tuple[str, ...] = ()
    program: str | None = None
    role: str | None = None
    schema_version: str = "0.4"

    def __post_init__(self) -> None:
        if self.schema_version != "0.4":
            raise ValueError("PolicyContext requires schema_version 0.4")
        if type(self.confirmed_by_user) is not bool:
            raise ValueError("confirmed_by_user must be a boolean")
        self._validate_text("program", self.program)
        self._validate_text("role", self.role)
        # Reuse the 0.3 validator for facts, task lists, conflicts and limits.
        UserTaskContext(
            self.confirmed_by_user,
            self.facts,
            self.completed_tasks,
            self.pending_tasks,
            "0.3",
        )

    @staticmethod
    def _validate_text(name: str, value: str | None) -> None:
        if value is None:
            return
        if not isinstance(value, str) or not value or value != value.strip() or len(value) > 256:
            raise ValueError(f"{name} must be a nonempty exact string without surrounding whitespace")

    @classmethod
    def from_dict(cls, data: dict) -> "PolicyContext":
        allowed = {
            "schema_version",
            "confirmed_by_user",
            "program",
            "role",
            "facts",
            "completed_tasks",
            "pending_tasks",
        }
        if not isinstance(data, dict) or set(data) - allowed:
            raise ValueError("unsupported PolicyContext keys")
        raw = data.get("facts", [])
        if not isinstance(raw, list) or any(
            not isinstance(f, dict) or set(f) != {"field", "value"} for f in raw
        ):
            raise ValueError("facts must be a list of field/value assertions")
        completed = data.get("completed_tasks", [])
        pending = data.get("pending_tasks", [])
        if not isinstance(completed, list) or not isinstance(pending, list):
            raise ValueError("task lists must be JSON arrays")
        return cls(
            confirmed_by_user=data.get("confirmed_by_user", False),
            facts=tuple(Fact(**f) for f in raw),
            completed_tasks=tuple(completed),
            pending_tasks=tuple(pending),
            program=data.get("program"),
            role=data.get("role"),
            schema_version=data.get("schema_version", "0.4"),
        )

    def base_context(self) -> UserTaskContext:
        """0.3 context used by the existing three-valued condition evaluator."""
        facts = list(self.facts)
        if self.role is not None:
            # Keep a conflicting explicit role visible instead of silently
            # selecting one of two assertions.
            facts.append(Fact("role", self.role))
        return UserTaskContext(
            self.confirmed_by_user,
            tuple(facts),
            self.completed_tasks,
            self.pending_tasks,
            "0.3",
        )

    def values(self, key: str) -> frozenset:
        return self.base_context().values(key)

    def conflicts(self) -> list[str]:
        return self.base_context().conflicts()

    def task_conflict(self, task_id: str) -> bool:
        return task_id in self.completed_tasks and task_id in self.pending_tasks
