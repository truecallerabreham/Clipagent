from __future__ import annotations

import collections
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum, IntEnum
from typing import Any, Sequence

# ==============================================================================
# MILESTONE 12: THE TASK RECIPE (orchestration/models.py)
# ==============================================================================
# Major Aim:
#   Serve as the architectural blueprint layer ("the task recipe") for the AI video
#   editing agent's factory floor. Defines formal schemas for asynchronous task
#   lifecycle states, execution priorities, resource budgeting (CPU/IO/GPU/API),
#   immutable artifact references, and a Directed Acyclic Graph (DAG) task engine
#   with cycle detection, topological sorting, and dependency resolution.
#
# Visual Example Flow:
#   Workflow Recipe:
#     [Task 1: Download Media]
#           |
#           v
#     [Task 2: Standardize Media] ---> [Task 3: Transcribe Speech]
#           |                                    |
#           v                                    v
#     [Task 4: Cut Segments]        [Task 5: Synthesize Subtitles]
#           \                                    /
#            \---> [Task 6: Merge & Add Subtitles] ---> [Task 7: Final Export]
#
#   Execution Engine:
#     1. Cycle Detection: Validates DAG has zero circular loops (e.g. A -> B -> A).
#     2. Ready Tasks Discovery: Identifies tasks whose dependencies are 100% completed.
#     3. Resource Budgeting: Tags CPU-heavy (FFmpeg) vs Network-API (Gemini/Qwen) tasks.
#     4. Priority Ordering: Schedules Critical and High priority tasks ahead of Normal.
# ==============================================================================


class TaskStatus(str, Enum):
    """Lifecycle execution states of an orchestrated task."""
    PENDING = "pending"          # Created, waiting for dependencies to evaluate
    BLOCKED = "blocked"          # Has one or more unresolved prerequisite dependencies
    READY = "ready"              # All dependencies completed; eligible for worker dispatch
    RUNNING = "running"          # Actively executing in a worker thread/process
    COMPLETED = "completed"      # Successfully executed; output artifacts registered
    FAILED = "failed"            # Raised an exception or exceeded retry threshold
    CANCELLED = "cancelled"      # Cancelled manually or due to upstream failure
    SKIPPED = "skipped"          # Bypassed via caching or conditional logic


class TaskPriority(IntEnum):
    """Execution priority levels for task queue dispatch ordering."""
    CRITICAL = 100   # Circuit breakers, emergency stops, pipeline aborts
    HIGH = 75        # User-blocking requests, final exports, audio synthesis
    NORMAL = 50      # Standard video cutting, merging, standardization
    LOW = 25         # Pre-fetching, background thumbnail/GIF generation
    BACKGROUND = 10  # Cache cleanup, logging, disk housekeeping


class ResourceType(str, Enum):
    """Hardware or network resource domain consumed by a task."""
    CPU_HEAVY = "cpu_heavy"      # Multi-threaded FFmpeg encoding, scaling, rendering
    IO_HEAVY = "io_heavy"        # Large file copying, disk extraction, local IO
    GPU_HEAVY = "gpu_heavy"      # Local neural inference (Whisper, neural filters)
    NETWORK_API = "network_api"  # External LLM calls (Gemini/Qwen, YouTube download)
    LIGHTWEIGHT = "lightweight"  # In-memory JSON parsing, timeline calculation, probing


@dataclass(slots=True)
class ResourceRequirement:
    """Resource budget specification required to run a task safely without crashing system."""
    resource_type: ResourceType = ResourceType.LIGHTWEIGHT
    cpu_cores: int = 1
    memory_mb: int = 256
    gpu_vram_mb: int = 0
    concurrency_key: str = "default"  # Shared lock key (e.g. 'ffmpeg_encoder', 'gemini_api')

    def to_dict(self) -> dict[str, Any]:
        return {
            "resource_type": self.resource_type.value,
            "cpu_cores": self.cpu_cores,
            "memory_mb": self.memory_mb,
            "gpu_vram_mb": self.gpu_vram_mb,
            "concurrency_key": self.concurrency_key,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ResourceRequirement:
        return cls(
            resource_type=ResourceType(data.get("resource_type", ResourceType.LIGHTWEIGHT.value)),
            cpu_cores=int(data.get("cpu_cores", 1)),
            memory_mb=int(data.get("memory_mb", 256)),
            gpu_vram_mb=int(data.get("gpu_vram_mb", 0)),
            concurrency_key=str(data.get("concurrency_key", "default")),
        )


@dataclass(slots=True)
class ArtifactRef:
    """Immutable pointer to a verified data asset produced or consumed by tasks."""
    artifact_id: str
    artifact_type: str  # e.g. 'video_file', 'audio_file', 'json_blueprint', 'subtitle_file'
    path: str | None = None
    checksum_sha256: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "path": self.path,
            "checksum_sha256": self.checksum_sha256,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ArtifactRef:
        return cls(
            artifact_id=data["artifact_id"],
            artifact_type=data["artifact_type"],
            path=data.get("path"),
            checksum_sha256=data.get("checksum_sha256"),
            metadata=data.get("metadata", {}),
        )


@dataclass(slots=True)
class TaskDefinition:
    """The task blueprint ('recipe') specifying action, parameters, dependencies, and limits."""
    task_id: str
    task_name: str
    action: str  # Registered tool or callable name (e.g. 'cut_video', 'merge_videos')
    params: dict[str, Any] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)
    priority: TaskPriority = TaskPriority.NORMAL
    resource_req: ResourceRequirement = field(default_factory=ResourceRequirement)
    max_retries: int = 2
    timeout_seconds: float = 300.0
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_name": self.task_name,
            "action": self.action,
            "params": self.params,
            "dependencies": self.dependencies,
            "priority": int(self.priority.value),
            "resource_req": self.resource_req.to_dict(),
            "max_retries": self.max_retries,
            "timeout_seconds": self.timeout_seconds,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskDefinition:
        priority_val = data.get("priority", TaskPriority.NORMAL.value)
        return cls(
            task_id=data["task_id"],
            task_name=data.get("task_name", data["task_id"]),
            action=data["action"],
            params=data.get("params", {}),
            dependencies=data.get("dependencies", []),
            priority=TaskPriority(priority_val),
            resource_req=ResourceRequirement.from_dict(data.get("resource_req", {})),
            max_retries=int(data.get("max_retries", 2)),
            timeout_seconds=float(data.get("timeout_seconds", 300.0)),
            tags=data.get("tags", []),
        )


@dataclass(slots=True)
class TaskResult:
    """Immutable audit record detailing the outcome and outputs of an executed task."""
    task_id: str
    status: TaskStatus
    output: Any = None
    output_artifacts: list[ArtifactRef] = field(default_factory=list)
    error_message: str | None = None
    execution_time_seconds: float = 0.0
    started_at: float | None = None
    completed_at: float | None = None
    retry_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "output": self.output,
            "output_artifacts": [a.to_dict() for a in self.output_artifacts],
            "error_message": self.error_message,
            "execution_time_seconds": round(self.execution_time_seconds, 3),
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "retry_count": self.retry_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskResult:
        return cls(
            task_id=data["task_id"],
            status=TaskStatus(data["status"]),
            output=data.get("output"),
            output_artifacts=[ArtifactRef.from_dict(a) for a in data.get("output_artifacts", [])],
            error_message=data.get("error_message"),
            execution_time_seconds=float(data.get("execution_time_seconds", 0.0)),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            retry_count=int(data.get("retry_count", 0)),
        )


class TaskGraph:
    """Directed Acyclic Graph (DAG) managing tasks, dependencies, cycles, and scheduling."""

    def __init__(self, name: str = "default_pipeline") -> None:
        self.name: str = name
        self._tasks: dict[str, TaskDefinition] = {}
        self._dependents: dict[str, set[str]] = collections.defaultdict(set)

    def add_task(self, task: TaskDefinition) -> None:
        """Add a task definition into the graph and index its dependency relationships."""
        if task.task_id in self._tasks:
            raise ValueError(f"Task with id '{task.task_id}' already exists in TaskGraph.")
        self._tasks[task.task_id] = task
        for dep_id in task.dependencies:
            self._dependents[dep_id].add(task.task_id)

    def get_task(self, task_id: str) -> TaskDefinition | None:
        """Retrieve a task definition by its unique identifier."""
        return self._tasks.get(task_id)

    def get_dependencies(self, task_id: str) -> list[str]:
        """Return all prerequisite task IDs that task_id depends upon."""
        task = self._tasks.get(task_id)
        return list(task.dependencies) if task else []

    def get_dependents(self, task_id: str) -> list[str]:
        """Return all downstream task IDs that depend on task_id."""
        return sorted(list(self._dependents.get(task_id, set())))

    def validate_dag(self) -> bool:
        """Verify that all referenced dependencies exist and the graph contains zero circular cycles.

        Raises:
            KeyError: If a task references a dependency ID that does not exist in the graph.
            ValueError: If a circular dependency cycle is detected (e.g. A -> B -> A).
        """
        # Step 1: Verify all dependencies exist in graph
        for t_id, task in self._tasks.items():
            for dep_id in task.dependencies:
                if dep_id not in self._tasks:
                    raise KeyError(
                        f"Task '{t_id}' references non-existent dependency '{dep_id}'."
                    )

        # Step 2: Kahn's Algorithm for cycle detection and topological sorting
        in_degree: dict[str, int] = {t_id: len(task.dependencies) for t_id, task in self._tasks.items()}
        zero_in_queue = collections.deque([t_id for t_id, deg in in_degree.items() if deg == 0])

        visited_count = 0
        while zero_in_queue:
            curr_id = zero_in_queue.popleft()
            visited_count += 1

            for dependent_id in self._dependents.get(curr_id, set()):
                in_degree[dependent_id] -= 1
                if in_degree[dependent_id] == 0:
                    zero_in_queue.append(dependent_id)

        if visited_count != len(self._tasks):
            cycle_tasks = [t_id for t_id, deg in in_degree.items() if deg > 0]
            raise ValueError(
                f"Circular dependency cycle detected in TaskGraph across tasks: {sorted(cycle_tasks)}"
            )

        return True

    def topological_sort(self) -> list[TaskDefinition]:
        """Return tasks in a valid linear execution order respecting all dependencies and priorities."""
        self.validate_dag()

        in_degree: dict[str, int] = {t_id: len(task.dependencies) for t_id, task in self._tasks.items()}
        # Priority ordering: Higher priority tasks are popped first
        ready_candidates: list[TaskDefinition] = [
            self._tasks[t_id] for t_id, deg in in_degree.items() if deg == 0
        ]
        # Sort ready candidates by priority descending
        ready_candidates.sort(key=lambda t: t.priority.value, reverse=True)

        sorted_order: list[TaskDefinition] = []

        while ready_candidates:
            curr_task = ready_candidates.pop(0)
            sorted_order.append(curr_task)

            # Check downstream dependents
            for dep_id in self.get_dependents(curr_task.task_id):
                in_degree[dep_id] -= 1
                if in_degree[dep_id] == 0:
                    ready_candidates.append(self._tasks[dep_id])

            # Re-sort ready queue by priority descending
            ready_candidates.sort(key=lambda t: t.priority.value, reverse=True)

        return sorted_order

    def get_ready_tasks(
        self,
        completed_task_ids: set[str],
        active_or_running_ids: set[str] | None = None,
    ) -> list[TaskDefinition]:
        """Identify all tasks whose dependencies are 100% completed and are ready to be dispatched.

        Args:
            completed_task_ids: Set of task IDs that have already finished with COMPLETED status.
            active_or_running_ids: Set of task IDs currently executing or already dispatched.

        Returns:
            List of TaskDefinition objects sorted by priority (highest priority first).
        """
        active_ids = active_or_running_ids or set()
        ready_tasks: list[TaskDefinition] = []

        for task_id, task in self._tasks.items():
            if task_id in completed_task_ids or task_id in active_ids:
                continue

            # Check if all dependencies are satisfied
            all_deps_met = all(dep in completed_task_ids for dep in task.dependencies)
            if all_deps_met:
                ready_tasks.append(task)

        # Sort by priority descending
        ready_tasks.sort(key=lambda t: t.priority.value, reverse=True)
        return ready_tasks

    def visualize_ascii(self) -> str:
        """Generate a clean ASCII tree diagram of the task pipeline graph."""
        lines = [f"=== TaskGraph: {self.name} ({len(self._tasks)} tasks) ==="]
        try:
            sorted_tasks = self.topological_sort()
        except Exception:
            sorted_tasks = list(self._tasks.values())

        for idx, t in enumerate(sorted_tasks, start=1):
            deps_str = f" [needs: {', '.join(t.dependencies)}]" if t.dependencies else " [ROOT]"
            priority_str = f"P:{t.priority.name}"
            res_str = f"Res:{t.resource_req.resource_type.value}"
            lines.append(f"  ({idx:02d}) [{t.task_id}] '{t.task_name}' -> action='{t.action}' | {priority_str} | {res_str}{deps_str}")

        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Serialize TaskGraph to dictionary structure."""
        return {
            "name": self.name,
            "tasks": [t.to_dict() for t in self._tasks.values()],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskGraph:
        """Construct TaskGraph from dictionary structure."""
        graph = cls(name=data.get("name", "pipeline"))
        for t_data in data.get("tasks", []):
            graph.add_task(TaskDefinition.from_dict(t_data))
        return graph

    def to_json(self, indent: int = 2) -> str:
        """Serialize TaskGraph to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> TaskGraph:
        """Construct TaskGraph from JSON string."""
        return cls.from_dict(json.loads(json_str))
