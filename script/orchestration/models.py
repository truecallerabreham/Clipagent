from __future__ import annotations

import collections
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

# ==============================================================================
# MILESTONE 12: THE TASK RECIPE (orchestration/models.py)
# ==============================================================================
# Major Aim:
#   Serve as the architectural blueprint schema layer ("the task recipe") for the
#   Clipagent factory floor, maintaining 100% exact architectural fidelity with
#   the reference architecture. Defines Pydantic models for task specifications (TaskSpec),
#   execution DAG plans (ExecutionPlan), live task states (TaskState), artifact
#   pointers (ArtifactRef), resource pool quotas (ResourcePoolConfig), and retry
#   policies (RetryPolicy), integrated with DAG cycle detection and topological sorting.
#
# Visual Example Flow:
#   ExecutionPlan:
#     - plan_id: "plan_edit_highlight_01"
#     - phase: "editing_execution"
#     - tasks:
#         [TaskSpec(id="t1", tool_name="download_material_video", ...)]
#             |
#             v
#         [TaskSpec(id="t2", tool_name="standardize_media_clips", depends_on=["t1"])]
#             |
#             v
#         [TaskSpec(id="t3", tool_name="batch_cut_video", depends_on=["t2"])]
#             |
#             v
#         [TaskSpec(id="t4", tool_name="merge_videos", depends_on=["t3"])]
#
#   Scheduling & Verification:
#     1. DAG Cycle Validation: Kahn's algorithm verifies zero circular loops (A -> B -> A).
#     2. Dynamic Ready Tasks: Dispatches tasks whose 'depends_on' are 100% completed.
#     3. Resource Pooling: Enforces concurrency caps (search, download, ffmpeg, tts, export).
#     4. State Tracking: Records TaskState (pending -> running -> completed/failed).
# ==============================================================================


def utc_now_iso() -> str:
    """Generate an ISO 8601 UTC timestamp string."""
    return datetime.now(timezone.utc).isoformat()


class RetryPolicy(BaseModel):
    """Execution retry strategy with backoff and error classification."""
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


class TaskSpec(BaseModel):
    """Specification of an orchestrated task ('the recipe') for the execution engine."""
    id: str = Field(min_length=1)
    phase: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    tool_name: str = ""
    description: str = ""
    arguments: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    resources: dict[str, int] = Field(default_factory=dict)
    conflict_keys: list[str] = Field(default_factory=list)
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
        return list(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))

    @field_validator("resources")
    @classmethod
    def _validate_resources(cls, value: dict[str, int]) -> dict[str, int]:
        normalized: dict[str, int] = {}
        for name, amount in value.items():
            key = str(name).strip()
            parsed = int(amount)
            if key and parsed > 0:
                normalized[key] = parsed
        return normalized


class ArtifactRef(BaseModel):
    """Immutable metadata record tracking an intermediate or final media asset."""
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
        """Resolve the physical filesystem path if set."""
        return Path(self.path).resolve(strict=False) if self.path else None


TaskStatus = Literal["pending", "running", "completed", "failed", "skipped"]


class TaskState(BaseModel):
    """Live execution state and results tracking for a scheduled task."""
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
    """Structured return payload produced by an executed task worker."""
    data: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[ArtifactRef] = Field(default_factory=list)


class ResourcePoolConfig(BaseModel):
    """Concurrency pool caps for different operational domains in the scheduler."""
    search_pool: int = Field(default=4, ge=1)
    download_pool: int = Field(default=3, ge=1)
    video_analysis_pool: int = Field(default=3, ge=1)
    llm_pool: int = Field(default=4, ge=1)
    ffmpeg_pool: int = Field(default=3, ge=1)
    tts_pool: int = Field(default=3, ge=1)
    export_pool: int = Field(default=1, ge=1)

    def as_dict(self) -> dict[str, int]:
        return {name: int(value) for name, value in self.model_dump().items()}


class ExecutionPlan(BaseModel):
    """A Directed Acyclic Graph (DAG) plan consisting of multiple task specifications."""
    plan_id: str
    phase: str
    goal: str = ""
    tasks: list[TaskSpec] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now_iso)
    deadline_at_epoch: float | None = Field(default=None, gt=0.0)

    def get_task(self, task_id: str) -> TaskSpec | None:
        """Find a task in the plan by ID."""
        for t in self.tasks:
            if t.id == task_id:
                return t
        return None

    def get_dependents(self, task_id: str) -> list[str]:
        """Return task IDs that directly depend on the given task_id."""
        dependents: list[str] = []
        for t in self.tasks:
            if task_id in t.depends_on:
                dependents.append(t.id)
        return sorted(dependents)

    def validate_dag(self) -> bool:
        """Verify all dependencies exist and check for circular dependency cycles.

        Raises:
            KeyError: If a task depends on a task ID that does not exist in the plan.
            ValueError: If a circular dependency cycle is detected.
        """
        task_map = {t.id: t for t in self.tasks}

        # Step 1: Verify all dependencies exist
        for t in self.tasks:
            for dep_id in t.depends_on:
                if dep_id not in task_map:
                    raise KeyError(
                        f"Task '{t.id}' references non-existent dependency '{dep_id}'."
                    )

        # Step 2: Kahn's algorithm for cycle detection
        in_degree: dict[str, int] = {t.id: len(t.depends_on) for t in self.tasks}
        dependents_map: dict[str, list[str]] = collections.defaultdict(list)
        for t in self.tasks:
            for dep_id in t.depends_on:
                dependents_map[dep_id].append(t.id)

        zero_in_queue = collections.deque([t_id for t_id, deg in in_degree.items() if deg == 0])
        visited_count = 0

        while zero_in_queue:
            curr_id = zero_in_queue.popleft()
            visited_count += 1
            for downstream in dependents_map.get(curr_id, []):
                in_degree[downstream] -= 1
                if in_degree[downstream] == 0:
                    zero_in_queue.append(downstream)

        if visited_count != len(self.tasks):
            cycle_tasks = [t_id for t_id, deg in in_degree.items() if deg > 0]
            raise ValueError(
                f"Circular dependency cycle detected in ExecutionPlan across tasks: {sorted(cycle_tasks)}"
            )

        return True

    def topological_sort(self) -> list[TaskSpec]:
        """Return tasks in a valid linear execution order respecting dependencies and priority."""
        self.validate_dag()
        task_map = {t.id: t for t in self.tasks}
        in_degree: dict[str, int] = {t.id: len(t.depends_on) for t in self.tasks}

        ready_candidates: list[TaskSpec] = [
            task_map[t_id] for t_id, deg in in_degree.items() if deg == 0
        ]
        # Sort ready candidates by priority descending
        ready_candidates.sort(key=lambda t: t.priority, reverse=True)

        dependents_map: dict[str, list[str]] = collections.defaultdict(list)
        for t in self.tasks:
            for dep_id in t.depends_on:
                dependents_map[dep_id].append(t.id)

        sorted_order: list[TaskSpec] = []

        while ready_candidates:
            curr_task = ready_candidates.pop(0)
            sorted_order.append(curr_task)

            for downstream_id in dependents_map.get(curr_task.id, []):
                in_degree[downstream_id] -= 1
                if in_degree[downstream_id] == 0:
                    ready_candidates.append(task_map[downstream_id])

            ready_candidates.sort(key=lambda t: t.priority, reverse=True)

        return sorted_order

    def get_ready_tasks(
        self,
        completed_task_ids: set[str],
        active_or_running_ids: set[str] | None = None,
    ) -> list[TaskSpec]:
        """Identify all tasks whose dependencies are completed and are ready for dispatch."""
        active_ids = active_or_running_ids or set()
        ready_tasks: list[TaskSpec] = []

        for task in self.tasks:
            if task.id in completed_task_ids or task.id in active_ids:
                continue

            all_deps_met = all(dep in completed_task_ids for dep in task.depends_on)
            if all_deps_met:
                ready_tasks.append(task)

        # Sort by priority descending
        ready_tasks.sort(key=lambda t: t.priority, reverse=True)
        return ready_tasks

    def visualize_ascii(self) -> str:
        """Render a clean ASCII diagram of the execution plan."""
        lines = [f"=== ExecutionPlan: {self.plan_id} (Phase: {self.phase}, {len(self.tasks)} tasks) ==="]
        try:
            ordered_tasks = self.topological_sort()
        except Exception:
            ordered_tasks = self.tasks

        for idx, t in enumerate(ordered_tasks, start=1):
            deps_str = f" [needs: {', '.join(t.depends_on)}]" if t.depends_on else " [ROOT]"
            priority_str = f"P:{t.priority}"
            tool_str = f"tool='{t.tool_name or t.kind}'"
            lines.append(f"  ({idx:02d}) [{t.id}] '{t.description or t.kind}' -> {tool_str} | {priority_str}{deps_str}")

        return "\n".join(lines)
