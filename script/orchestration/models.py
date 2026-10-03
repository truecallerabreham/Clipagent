from __future__ import annotations

# Standard library imports for collections, dates, filesystem paths, and type annotations
import collections  # Provides deque for Kahn's queue and defaultdict for graph mapping
from datetime import datetime, timezone  # Provides timezone-aware UTC timestamps
from pathlib import Path  # Provides object-oriented filesystem path operations
from typing import Any, Literal  # Provides flexible typing and fixed literal choices

# Third-party Pydantic V2 imports for strict data schemas and runtime validation
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
# Core Checking & Defense Mechanisms:
#   1. Pydantic Field Validation: Strips whitespace, removes duplicate dependencies,
#      and normalizes positive resource quotas automatically at instantiation.
#   2. Missing Dependency Verification: Rejects plans referencing nonexistent task IDs.
#   3. Kahn's Cycle Detection (DAG Defense): Mathematically proves zero circular deadlocks.
#   4. Priority-Aware Topological Sorting: Resolves linear sequence respecting constraints.
#   5. Dynamic Ready-Task Dispatch: Dynamically queries tasks whose dependencies are met.
# ==============================================================================


def utc_now_iso() -> str:
    """Generate an ISO 8601 UTC timestamp string."""
    # Obtain current system time localized to UTC and format as ISO 8601 string
    return datetime.now(timezone.utc).isoformat()


class RetryPolicy(BaseModel):
    """Execution retry strategy with backoff and error classification."""

    # Maximum number of retry attempts allowed (between 1 and 5 attempts)
    max_attempts: int = Field(default=1, ge=1, le=5)

    # Delay duration in seconds between successive retry attempts (0 to 60s)
    backoff_seconds: float = Field(default=0.0, ge=0.0, le=60.0)

    # List of substring error signatures that qualify a failure as retryable
    retryable_errors: list[str] = Field(
        default_factory=lambda: [
            "timeout",  # Network or execution timeout
            "temporarily unavailable",  # Service transient error
            "connection reset",  # TCP socket connection reset
            "connection aborted",  # TCP socket connection aborted
            "rate limit",  # API provider rate limit reached
            "429",  # HTTP 429 Too Many Requests
            "502",  # HTTP 502 Bad Gateway
            "503",  # HTTP 503 Service Unavailable
            "504",  # HTTP 504 Gateway Timeout
        ]
    )


class TaskSpec(BaseModel):
    """Specification of an orchestrated task ('the recipe') for the execution engine."""

    # Unique task identifier within the execution plan (e.g., 'task_cut_intro')
    id: str = Field(min_length=1)

    # Name of the workflow phase to which this task belongs (e.g., 'editing_execution')
    phase: str = Field(min_length=1)

    # Architectural kind/category of the task (e.g., 'download', 'cut', 'merge')
    kind: str = Field(min_length=1)

    # Exact registered tool name to execute (e.g., 'cut_video', 'batch_cut_video')
    tool_name: str = ""

    # Human-readable explanation of the task's specific purpose for agent logging
    description: str = ""

    # Key-value arguments passed directly to the tool function during execution
    arguments: dict[str, Any] = Field(default_factory=dict)

    # List of task IDs that must complete before this task can be dispatched
    depends_on: list[str] = Field(default_factory=list)

    # Resource pool quotas consumed by this task during execution (e.g. {'ffmpeg_pool': 1})
    resources: dict[str, int] = Field(default_factory=dict)

    # Mutex lock keys preventing conflicting tasks from running concurrently
    conflict_keys: list[str] = Field(default_factory=list)

    # IDs of artifacts required by this task as inputs
    input_artifacts: list[str] = Field(default_factory=list)

    # Categories/kinds of artifacts this task is expected to produce
    output_kinds: list[str] = Field(default_factory=list)

    # Anticipated execution duration in seconds for scheduling heuristics
    estimated_seconds: float = Field(default=0.0, ge=0.0)

    # Scheduling priority weight (-100 to 100); higher priority tasks dispatch first
    priority: int = Field(default=0, ge=-100, le=100)

    # Flag indicating whether failure of this task is non-fatal to the entire plan
    optional: bool = False

    # Hard execution timeout in seconds; cancels task if exceeded
    timeout_seconds: float | None = Field(default=None, gt=0.0)

    # Retry policy configuration governing automated re-execution upon error
    retry: RetryPolicy = Field(default_factory=RetryPolicy)

    @field_validator("depends_on", "conflict_keys", "input_artifacts", "output_kinds")
    @classmethod
    def _dedupe_strings(cls, value: list[str]) -> list[str]:
        """Checking Mechanism: Clean whitespace and deduplicate string lists."""
        # Strip each string, filter out blanks, and preserve insertion order via dict keys
        return list(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))

    @field_validator("resources")
    @classmethod
    def _validate_resources(cls, value: dict[str, int]) -> dict[str, int]:
        """Checking Mechanism: Normalize resource amounts and discard non-positive values."""
        # Initialize dictionary to collect validated non-empty positive resources
        normalized: dict[str, int] = {}
        # Iterate over each resource name and requested allocation amount
        for name, amount in value.items():
            # Strip whitespace from the resource pool name
            key = str(name).strip()
            # Cast requested amount to integer
            parsed = int(amount)
            # Only retain entries with non-empty names and positive allocation > 0
            if key and parsed > 0:
                # Save normalized key and valid amount
                normalized[key] = parsed
        # Return cleaned resource allocation map
        return normalized


class ArtifactRef(BaseModel):
    """Immutable metadata record tracking an intermediate or final media asset."""

    # Globally unique identifier for this artifact (e.g. 'art_clip_01')
    id: str

    # Category of the media artifact (e.g., 'source_video', 'audio_track', 'subtitles')
    kind: str

    # Physical filesystem path where the artifact file is saved on disk
    path: str = ""

    # ID of the task that created and saved this artifact
    producer_task_id: str

    # Production phase during which this artifact was generated
    phase: str

    # Arbitrary domain metadata (e.g., resolution, fps, duration, sample rate)
    metadata: dict[str, Any] = Field(default_factory=dict)

    # Cryptographic checksum (e.g. SHA-256) verifying asset integrity
    checksum: str = ""

    # Physical file size in bytes
    size_bytes: int = 0

    # UTC timestamp recording when this artifact was cataloged
    created_at: str = Field(default_factory=utc_now_iso)

    # Validity flag; set to False if file is corrupted, deleted, or superseded
    valid: bool = True

    def resolved_path(self) -> Path | None:
        """Resolve the physical filesystem path if set."""
        # Return resolved absolute Path if path is non-empty, otherwise return None
        return Path(self.path).resolve(strict=False) if self.path else None


# Type choice representing the five standard lifecycle states of an orchestrated task
TaskStatus = Literal["pending", "running", "completed", "failed", "skipped"]


class TaskState(BaseModel):
    """Live execution state and results tracking for a scheduled task."""

    # Task ID corresponding to the TaskSpec being tracked
    task_id: str

    # Hash fingerprint of the task's arguments and spec for caching
    task_fingerprint: str = ""

    # Fingerprints of all upstream dependencies at time of execution
    dependency_fingerprints: dict[str, str] = Field(default_factory=dict)

    # Current lifecycle state (defaults to 'pending')
    status: TaskStatus = "pending"

    # Number of execution attempts already performed
    attempts: int = 0

    # ISO timestamp when task execution started
    started_at: str | None = None

    # ISO timestamp when task execution completed or failed
    completed_at: str | None = None

    # Error message if task failed; empty string on success
    error: str = ""

    # Arbitrary return dictionary produced by the completed task
    result: dict[str, Any] = Field(default_factory=dict)

    # List of artifact IDs generated by this task execution
    artifact_ids: list[str] = Field(default_factory=list)

    # Total elapsed wall-clock duration in seconds
    elapsed_seconds: float = Field(default=0.0, ge=0.0)


class TaskExecutionResult(BaseModel):
    """Structured return payload produced by an executed task worker."""

    # Key-value payload returned from the tool function
    data: dict[str, Any] = Field(default_factory=dict)

    # List of newly generated ArtifactRef metadata objects created by the worker
    artifacts: list[ArtifactRef] = Field(default_factory=list)


class ResourcePoolConfig(BaseModel):
    """Concurrency pool caps for different operational domains in the scheduler."""

    # Maximum concurrent internet material searches allowed
    search_pool: int = Field(default=4, ge=1)

    # Maximum concurrent video downloads allowed
    download_pool: int = Field(default=3, ge=1)

    # Maximum concurrent video analysis / frame inspection tasks
    video_analysis_pool: int = Field(default=3, ge=1)

    # Maximum concurrent LLM API calls allowed
    llm_pool: int = Field(default=4, ge=1)

    # Maximum concurrent FFmpeg video processing tasks (CPU/GPU intensive)
    ffmpeg_pool: int = Field(default=3, ge=1)

    # Maximum concurrent TTS audio generation tasks
    tts_pool: int = Field(default=3, ge=1)

    # Maximum concurrent final video rendering/export tasks (heaviest workload)
    export_pool: int = Field(default=1, ge=1)

    def as_dict(self) -> dict[str, int]:
        """Convert pool limits to a clean string-to-int dictionary."""
        # Export model fields as native dictionary with integer values
        return {name: int(value) for name, value in self.model_dump().items()}


class ExecutionPlan(BaseModel):
    """A Directed Acyclic Graph (DAG) plan consisting of multiple task specifications."""

    # Unique identifier for this entire execution plan
    plan_id: str

    # Workflow phase name represented by this plan
    phase: str

    # High-level objective or goal of this plan (e.g. 'Produce 60s Reel')
    goal: str = ""

    # Complete list of task specifications comprising the plan
    tasks: list[TaskSpec] = Field(default_factory=list)

    # ISO timestamp when this plan was generated
    created_at: str = Field(default_factory=utc_now_iso)

    # Optional epoch timestamp after which execution should be aborted
    deadline_at_epoch: float | None = Field(default=None, gt=0.0)

    def get_task(self, task_id: str) -> TaskSpec | None:
        """Find a task in the plan by ID."""
        # Loop through each task in the plan
        for t in self.tasks:
            # Check if task ID matches query ID
            if t.id == task_id:
                # Return matched task specification
                return t
        # Return None if no task with the specified ID was found
        return None

    def get_dependents(self, task_id: str) -> list[str]:
        """Return task IDs that directly depend on the given task_id."""
        # List to accumulate downstream dependent task IDs
        dependents: list[str] = []
        # Inspect every task in the plan
        for t in self.tasks:
            # Check if target task_id is listed in this task's depends_on
            if task_id in t.depends_on:
                # Add this task's ID as a downstream dependent
                dependents.append(t.id)
        # Return sorted list of dependent task IDs for determinism
        return sorted(dependents)

    def validate_dag(self) -> bool:
        """Checking Mechanism: Verify dependencies exist and check for circular dependency cycles.

        Raises:
            KeyError: If a task depends on a task ID that does not exist in the plan.
            ValueError: If a circular dependency cycle is detected.
        """
        # Build quick lookup map of task IDs to TaskSpec objects
        task_map = {t.id: t for t in self.tasks}

        # Step 1: Verify all dependencies exist in the plan (Referential Integrity Check)
        for t in self.tasks:
            # Check every declared dependency ID for this task
            for dep_id in t.depends_on:
                # If dependency is missing from the task map, raise error immediately
                if dep_id not in task_map:
                    raise KeyError(
                        f"Task '{t.id}' references non-existent dependency '{dep_id}'."
                    )

        # Step 2: Kahn's Algorithm for DAG cycle detection and verification
        # Calculate in-degree (number of pending upstream dependencies) for each task
        in_degree: dict[str, int] = {t.id: len(t.depends_on) for t in self.tasks}

        # Build reverse adjacency list: mapping each task ID to tasks that depend on it
        dependents_map: dict[str, list[str]] = collections.defaultdict(list)
        for t in self.tasks:
            for dep_id in t.depends_on:
                dependents_map[dep_id].append(t.id)

        # Enqueue all root tasks that have 0 in-degree (no prerequisites)
        zero_in_queue = collections.deque([t_id for t_id, deg in in_degree.items() if deg == 0])

        # Counter tracking how many tasks can be cleanly visited without encountering deadlocks
        visited_count = 0

        # Process tasks in zero_in_queue until empty
        while zero_in_queue:
            # Pop the next ready task ID
            curr_id = zero_in_queue.popleft()
            # Increment visited counter
            visited_count += 1
            # Decrement in-degree for all downstream tasks depending on curr_id
            for downstream in dependents_map.get(curr_id, []):
                in_degree[downstream] -= 1
                # When all prerequisites are resolved (in-degree hits 0), enqueue downstream task
                if in_degree[downstream] == 0:
                    zero_in_queue.append(downstream)

        # If visited count does not equal total tasks, at least one circular loop exists
        if visited_count != len(self.tasks):
            # Collect all tasks that remain stuck with in_degree > 0
            cycle_tasks = [t_id for t_id, deg in in_degree.items() if deg > 0]
            # Raise ValueError detailing the circular deadlock
            raise ValueError(
                f"Circular dependency cycle detected in ExecutionPlan across tasks: {sorted(cycle_tasks)}"
            )

        # Successfully validated: graph is a valid, acyclic DAG
        return True

    def topological_sort(self) -> list[TaskSpec]:
        """Checking Mechanism: Return tasks in valid linear execution order respecting priority."""
        # First ensure the graph is acyclic and valid
        self.validate_dag()

        # Build ID lookup map
        task_map = {t.id: t for t in self.tasks}

        # Track in-degree count for each task
        in_degree: dict[str, int] = {t.id: len(t.depends_on) for t in self.tasks}

        # Collect initial candidate tasks that have 0 prerequisites
        ready_candidates: list[TaskSpec] = [
            task_map[t_id] for t_id, deg in in_degree.items() if deg == 0
        ]
        # Sort initial candidate pool by priority descending (highest priority first)
        ready_candidates.sort(key=lambda t: t.priority, reverse=True)

        # Build reverse adjacency map for fast downstream lookup
        dependents_map: dict[str, list[str]] = collections.defaultdict(list)
        for t in self.tasks:
            for dep_id in t.depends_on:
                dependents_map[dep_id].append(t.id)

        # List storing final ordered sequence of tasks
        sorted_order: list[TaskSpec] = []

        # Process candidate tasks until all tasks are sequenced
        while ready_candidates:
            # Pop highest-priority ready task from candidate list
            curr_task = ready_candidates.pop(0)
            # Append selected task to ordered sequence
            sorted_order.append(curr_task)

            # Reduce in-degree for each downstream dependent
            for downstream_id in dependents_map.get(curr_task.id, []):
                in_degree[downstream_id] -= 1
                # If dependent has no more unfulfilled dependencies, add to ready candidate pool
                if in_degree[downstream_id] == 0:
                    ready_candidates.append(task_map[downstream_id])

            # Re-sort ready candidate pool so highest-priority tasks are always selected next
            ready_candidates.sort(key=lambda t: t.priority, reverse=True)

        # Return full topologically sorted task sequence
        return sorted_order

    def get_ready_tasks(
        self,
        completed_task_ids: set[str],
        active_or_running_ids: set[str] | None = None,
    ) -> list[TaskSpec]:
        """Checking Mechanism: Identify all tasks whose dependencies are completed and ready for dispatch."""
        # Use provided active/running set or default to empty set
        active_ids = active_or_running_ids or set()

        # List accumulating ready tasks
        ready_tasks: list[TaskSpec] = []

        # Evaluate each task in the plan
        for task in self.tasks:
            # Skip if task is already completed or currently running
            if task.id in completed_task_ids or task.id in active_ids:
                continue

            # Check if all required dependencies are present in completed_task_ids
            all_deps_met = all(dep in completed_task_ids for dep in task.depends_on)

            # If all prerequisites are satisfied, task is ready for dispatch
            if all_deps_met:
                ready_tasks.append(task)

        # Sort ready tasks by priority descending so high-priority work dispatches first
        ready_tasks.sort(key=lambda t: t.priority, reverse=True)

        # Return ready tasks list
        return ready_tasks

    def visualize_ascii(self) -> str:
        """Render a clean ASCII diagram of the execution plan."""
        # Build header line with plan ID, phase, and total task count
        lines = [f"=== ExecutionPlan: {self.plan_id} (Phase: {self.phase}, {len(self.tasks)} tasks) ==="]

        # Attempt to order tasks topologically, fallback to raw list on cyclic error
        try:
            ordered_tasks = self.topological_sort()
        except Exception:
            ordered_tasks = self.tasks

        # Format and append each task with order index, ID, description, tool, and dependencies
        for idx, t in enumerate(ordered_tasks, start=1):
            deps_str = f" [needs: {', '.join(t.depends_on)}]" if t.depends_on else " [ROOT]"
            priority_str = f"P:{t.priority}"
            tool_str = f"tool='{t.tool_name or t.kind}'"
            lines.append(f"  ({idx:02d}) [{t.id}] '{t.description or t.kind}' -> {tool_str} | {priority_str}{deps_str}")

        # Join formatted lines into single displayable string
        return "\n".join(lines)
