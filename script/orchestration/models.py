from __future__ import annotations

import collections
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


def utc_now_iso() -> str:
    """Return the current UTC timestamp formatted as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


# ==============================================================================
# 1. RETRY POLICY
# ==============================================================================
class RetryPolicy(BaseModel):
    """Rules for retrying a failed task when network or transient errors happen."""

    max_attempts: int = Field(default=1, ge=1, le=5)
    backoff_seconds: float = Field(default=0.0, ge=0.0, le=60.0)
    retryable_errors: list[str] = Field(
        default_factory=lambda: [
            "timeout",
            "temporarily unavailable",
            "connection reset",
            "connection aborted",
            "rate limit",
            "429",
            "502",
            "503",
            "504",
        ]
    )


# ==============================================================================
# 2. TASK SPECIFICATION ("The Recipe Step")
# ==============================================================================
class TaskSpec(BaseModel):
    """Defines a single job for the AI agent (e.g., 'cut video', 'extract audio')."""

    id: str = Field(min_length=1, description="Unique ID for this task (e.g. 'cut_intro')")
    phase: str = Field(min_length=1, description="Production stage (e.g. 'editing_execution')")
    kind: str = Field(min_length=1, description="Category of task (e.g. 'cut', 'merge', 'download')")
    tool_name: str = ""
    description: str = ""
    arguments: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list, description="IDs of tasks that must finish first")
    resources: dict[str, int] = Field(default_factory=dict, description="Resource slots needed (e.g. {'ffmpeg_pool': 1})")
    conflict_keys: list[str] = Field(default_factory=list, description="Locks preventing concurrent writes to the same file")
    input_artifacts: list[str] = Field(default_factory=list)
    output_kinds: list[str] = Field(default_factory=list)
    estimated_seconds: float = Field(default=0.0, ge=0.0)
    priority: int = Field(default=0, ge=-100, le=100)
    optional: bool = False
    timeout_seconds: float | None = Field(default=None, gt=0.0)
    retry: RetryPolicy = Field(default_factory=RetryPolicy)

    @field_validator("depends_on", "conflict_keys", "input_artifacts", "output_kinds")
    @classmethod
    def _dedupe_strings(cls, value: list[str]) -> list[str]:
        """Strip whitespace and remove duplicate IDs while keeping order."""
        return list(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))

    @field_validator("resources")
    @classmethod
    def _validate_resources(cls, value: dict[str, int]) -> dict[str, int]:
        """Keep only non-empty resource names with positive allocations."""
        cleaned: dict[str, int] = {}
        for name, amount in value.items():
            key = str(name).strip()
            parsed = int(amount)
            if key and parsed > 0:
                cleaned[key] = parsed
        return cleaned


# ==============================================================================
# 3. ARTIFACT REFERENCE ("The Item on the Pantry Shelf")
# ==============================================================================
class ArtifactRef(BaseModel):
    """Tracks a file produced by a task (e.g., a cut video clip or audio track)."""

    id: str
    kind: str
    path: str = ""
    producer_task_id: str
    phase: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    checksum: str = ""
    size_bytes: int = 0
    created_at: str = Field(default_factory=utc_now_iso)
    valid: bool = True

    def resolved_path(self) -> Path | None:
        """Return the absolute path on disk, or None if path is empty."""
        return Path(self.path).resolve(strict=False) if self.path else None


# ==============================================================================
# 4. TASK STATUS & RUNTIME STATE
# ==============================================================================
TaskStatus = Literal["pending", "running", "completed", "failed", "skipped"]


class TaskState(BaseModel):
    """Live status and results for a task during execution."""

    task_id: str
    task_fingerprint: str = ""
    dependency_fingerprints: dict[str, str] = Field(default_factory=dict)
    status: TaskStatus = "pending"
    attempts: int = 0
    started_at: str | None = None
    completed_at: str | None = None
    error: str = ""
    result: dict[str, Any] = Field(default_factory=dict)
    artifact_ids: list[str] = Field(default_factory=list)
    elapsed_seconds: float = Field(default=0.0, ge=0.0)


class TaskExecutionResult(BaseModel):
    """The result returned by a worker when a task finishes."""

    data: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[ArtifactRef] = Field(default_factory=list)


# ==============================================================================
# 5. RESOURCE POOL CONFIG ("The Kitchen Capacity")
# ==============================================================================
class ResourcePoolConfig(BaseModel):
    """Limits how many tasks of each type can run at the same time to protect RAM/CPU."""

    search_pool: int = Field(default=4, ge=1)
    download_pool: int = Field(default=3, ge=1)
    video_analysis_pool: int = Field(default=3, ge=1)
    llm_pool: int = Field(default=4, ge=1)
    ffmpeg_pool: int = Field(default=3, ge=1)
    tts_pool: int = Field(default=3, ge=1)
    export_pool: int = Field(default=1, ge=1)

    def as_dict(self) -> dict[str, int]:
        return {name: int(value) for name, value in self.model_dump().items()}


# ==============================================================================
# 6. EXECUTION PLAN ("The Full Recipe Card")
# ==============================================================================
class ExecutionPlan(BaseModel):
    """A collection of tasks that together produce a complete video."""

    plan_id: str
    phase: str
    goal: str = ""
    tasks: list[TaskSpec] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now_iso)
    deadline_at_epoch: float | None = Field(default=None, gt=0.0)

    def get_task(self, task_id: str) -> TaskSpec | None:
        """Find a task by its ID."""
        for t in self.tasks:
            if t.id == task_id:
                return t
        return None

    def get_dependents(self, task_id: str) -> list[str]:
        """Find all tasks waiting on this task to finish."""
        return sorted([t.id for t in self.tasks if task_id in t.depends_on])

    def validate_dag(self) -> bool:
        """Check that all dependencies exist and that there are no circular loops."""
        task_map = {t.id: t for t in self.tasks}

        # 1. Check for missing dependency IDs
        for t in self.tasks:
            for dep_id in t.depends_on:
                if dep_id not in task_map:
                    raise KeyError(f"Task '{t.id}' references non-existent dependency '{dep_id}'.")

        # 2. Check for circular loops (A needs B, B needs A)
        in_degree = {t.id: len(t.depends_on) for t in self.tasks}
        dependents_map: dict[str, list[str]] = collections.defaultdict(list)
        for t in self.tasks:
            for dep_id in t.depends_on:
                dependents_map[dep_id].append(t.id)

        ready_queue = collections.deque([t_id for t_id, deg in in_degree.items() if deg == 0])
        processed_count = 0

        while ready_queue:
            curr = ready_queue.popleft()
            processed_count += 1
            for downstream in dependents_map.get(curr, []):
                in_degree[downstream] -= 1
                if in_degree[downstream] == 0:
                    ready_queue.append(downstream)

        if processed_count != len(self.tasks):
            trapped = [t_id for t_id, deg in in_degree.items() if deg > 0]
            raise ValueError(f"Circular dependency cycle detected in ExecutionPlan across tasks: {sorted(trapped)}")

        return True

    def topological_sort(self) -> list[TaskSpec]:
        """Return tasks in a valid order where prerequisites come before dependent tasks."""
        self.validate_dag()
        task_map = {t.id: t for t in self.tasks}
        in_degree = {t.id: len(t.depends_on) for t in self.tasks}

        dependents_map: dict[str, list[str]] = collections.defaultdict(list)
        for t in self.tasks:
            for dep_id in t.depends_on:
                dependents_map[dep_id].append(t.id)

        # Start with root tasks (no prerequisites), higher priority first
        ready_pool = [task_map[t_id] for t_id, deg in in_degree.items() if deg == 0]
        ready_pool.sort(key=lambda t: t.priority, reverse=True)

        ordered: list[TaskSpec] = []
        while ready_pool:
            curr = ready_pool.pop(0)
            ordered.append(curr)

            for downstream_id in dependents_map.get(curr.id, []):
                in_degree[downstream_id] -= 1
                if in_degree[downstream_id] == 0:
                    ready_pool.append(task_map[downstream_id])

            ready_pool.sort(key=lambda t: t.priority, reverse=True)

        return ordered

    def get_ready_tasks(
        self,
        completed_task_ids: set[str],
        active_or_running_ids: set[str] | None = None,
    ) -> list[TaskSpec]:
        """Find all tasks whose prerequisites are 100% completed and ready to run."""
        active = active_or_running_ids or set()
        ready: list[TaskSpec] = []

        for task in self.tasks:
            if task.id in completed_task_ids or task.id in active:
                continue
            if all(dep in completed_task_ids for dep in task.depends_on):
                ready.append(task)

        ready.sort(key=lambda t: t.priority, reverse=True)
        return ready

    def visualize_ascii(self) -> str:
        """Render a clean, human-readable diagram of the tasks."""
        lines = [f"=== ExecutionPlan: {self.plan_id} (Phase: {self.phase}, {len(self.tasks)} tasks) ==="]
        try:
            tasks_to_show = self.topological_sort()
        except Exception:
            tasks_to_show = self.tasks

        for idx, t in enumerate(tasks_to_show, start=1):
            deps = f" [needs: {', '.join(t.depends_on)}]" if t.depends_on else " [ROOT]"
            prio = f"P:{t.priority}"
            tool = f"tool='{t.tool_name or t.kind}'"
            lines.append(f"  ({idx:02d}) [{t.id}] '{t.description or t.kind}' -> {tool} | {prio}{deps}")

        return "\n".join(lines)
