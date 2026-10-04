from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Any, Callable

from .artifacts import ArtifactRegistry
from .models import (
    ExecutionPlan,
    ResourcePoolConfig,
    TaskExecutionResult,
    TaskSpec,
    TaskState,
    utc_now_iso,
)


class SchedulerError(RuntimeError):
    """Raised when an execution plan is invalid or encounters an unrecoverable failure."""
    pass


TaskExecutor = Callable[[TaskSpec, dict[str, TaskState]], TaskExecutionResult | dict[str, Any]]
EventSink = Callable[[str, dict[str, Any]], None]
SafePointCallback = Callable[[dict[str, Any]], None]


# ==============================================================================
# RESOURCE SCHEDULER ("The Kitchen Head Chef / Factory Conductor")
# ==============================================================================
# Manages multi-threaded task execution. Dispatches jobs when their prerequisites
# are finished, ensures FFmpeg and API limits are respected, and saves progress.
# ==============================================================================
class ResourceScheduler:
    """Dispatches tasks concurrently while enforcing resource caps and safety locks."""

    RESOURCE_ORDER = (
        "search_pool",
        "download_pool",
        "video_analysis_pool",
        "llm_pool",
        "ffmpeg_pool",
        "tts_pool",
        "export_pool",
    )

    def __init__(
        self,
        *,
        pools: ResourcePoolConfig,
        workspace: Path,
        artifact_registry: ArtifactRegistry,
        event_sink: EventSink | None = None,
        cancel_requested: Callable[[], bool] | None = None,
        safe_point: SafePointCallback | None = None,
    ) -> None:
        self.pools = pools.as_dict()
        self.workspace = workspace.resolve(strict=False)
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.registry = artifact_registry
        self.event_sink = event_sink
        self.cancel_requested = cancel_requested or (lambda: False)
        self.safe_point = safe_point

        self.state_dir = self.workspace / ".clipagent"
        self.state_dir.mkdir(parents=True, exist_ok=True)

        self._state_lock = threading.RLock()
        self._resource_in_use = {name: 0 for name in self.pools}
        self._conflicts_in_use: set[str] = set()

    def run(
        self,
        plan: ExecutionPlan,
        executor: TaskExecutor,
        *,
        resume: bool = True,
        allow_partial_failure: bool = False,
    ) -> dict[str, TaskState]:
        """Run all tasks in the plan until complete, reusing previous work if possible."""
        self.validate_plan(plan)

        plan_path = self.state_dir / f"{plan.plan_id}.plan.json"
        state_path = self.state_dir / f"{plan.plan_id}.state.json"
        self._atomic_json_write(plan_path, plan.model_dump())

        states = self._load_states(plan, state_path) if resume else self._new_states(plan)

        # Check for completed tasks that can be safely reused
        completed: set[str] = set()
        for task in plan.tasks:
            state = states[task.id]
            if state.status == "skipped":
                completed.add(task.id)
            elif (
                state.status == "completed"
                and all(dep in completed for dep in task.depends_on)
                and self._reuse_completed_task(task, state, states)
            ):
                completed.add(task.id)
            elif state.status == "completed":
                state.status = "pending"
                state.error = "A dependency changed or is no longer reusable."

        failed: set[str] = {t_id for t_id, s in states.items() if s.status == "failed"}
        running: dict[Future[Any], TaskSpec] = {}
        ready_emitted: set[str] = set()
        max_workers = max(1, sum(self.pools.values()))

        self._emit("task_plan_started", {"plan_id": plan.plan_id, "phase": plan.phase, "task_count": len(plan.tasks)})

        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix=f"{plan.phase}-task") as pool:
            while len(completed) + len(failed) < len(plan.tasks):
                if self.cancel_requested():
                    for fut in running:
                        fut.cancel()
                    raise SchedulerError(f"Execution plan cancelled: {plan.plan_id}")

                made_progress = False

                # Evaluate tasks by highest priority first
                for task in sorted(plan.tasks, key=lambda t: t.priority, reverse=True):
                    state = states[task.id]

                    if task.id in completed or task.id in failed or state.status == "running":
                        continue

                    # If an upstream dependency failed, this task cannot run
                    if any(dep in failed for dep in task.depends_on):
                        state.status = "failed"
                        state.error = "Dependency failed."
                        state.completed_at = utc_now_iso()
                        failed.add(task.id)
                        self._checkpoint(state_path, states)
                        continue

                    # Wait until all dependencies are completed
                    if not all(dep in completed for dep in task.depends_on):
                        continue

                    # Skip optional tasks if time budget is exhausted
                    remaining = self._remaining_seconds(plan)
                    if task.optional and remaining is not None and (remaining <= 0 or task.estimated_seconds > remaining):
                        state.status = "skipped"
                        state.error = "Skipped because execution budget is exhausted."
                        state.completed_at = utc_now_iso()
                        completed.add(task.id)
                        self._checkpoint(state_path, states)
                        self._emit("optional_task_skipped", {"plan_id": plan.plan_id, "task_id": task.id})
                        made_progress = True
                        continue

                    if task.id not in ready_emitted:
                        ready_emitted.add(task.id)
                        self._emit("task_ready", {"plan_id": plan.plan_id, "task_id": task.id})

                    # If previous run output is already valid on disk, reuse it
                    if self._reuse_completed_task(task, state, states):
                        completed.add(task.id)
                        self._checkpoint(state_path, states)
                        self._emit("task_reused", {"plan_id": plan.plan_id, "task_id": task.id})
                        made_progress = True
                        continue

                    # Acquire resource capacity (e.g. ffmpeg slot) and file conflict lock
                    if not self._try_acquire(task):
                        continue

                    # Launch worker thread
                    state.status = "running"
                    state.task_fingerprint = self._task_fingerprint(task)
                    state.dependency_fingerprints = {dep: states[dep].task_fingerprint for dep in task.depends_on}
                    state.attempts += 1
                    state.started_at = utc_now_iso()
                    state.error = ""
                    self._checkpoint(state_path, states)
                    self._emit("task_started", {"plan_id": plan.plan_id, "task_id": task.id})

                    dep_states = {dep: states[dep].model_copy(deep=True) for dep in task.depends_on}
                    future = pool.submit(executor, task, dep_states)
                    setattr(future, "_clipagent_started_monotonic", time.monotonic())
                    running[future] = task
                    made_progress = True

                # If no tasks are running and no progress was made, detect deadlock
                if not running:
                    self._run_safe_point(plan, completed, states)
                    if len(completed) + len(failed) >= len(plan.tasks):
                        break
                    if not made_progress:
                        pending = [t.id for t in plan.tasks if t.id not in completed and t.id not in failed]
                        raise SchedulerError(f"No schedulable tasks remain in {plan.plan_id}: {pending}")
                    continue

                # Wait for at least one worker to finish
                done, _ = wait(tuple(running), return_when=FIRST_COMPLETED)
                for future in done:
                    task = running.pop(future)
                    state = states[task.id]
                    self._release(task)

                    started_mono = getattr(future, "_clipagent_started_monotonic", None)
                    if started_mono is not None:
                        state.elapsed_seconds = max(0.0, time.monotonic() - float(started_mono))

                    try:
                        raw = future.result()
                        res = raw if isinstance(raw, TaskExecutionResult) else TaskExecutionResult.model_validate(raw)

                        if task.timeout_seconds and state.elapsed_seconds > task.timeout_seconds:
                            raise TimeoutError(f"Task timeout after {state.elapsed_seconds:.2f}s (limit {task.timeout_seconds}s)")

                        state.status = "completed"
                        state.result = res.data
                        state.completed_at = utc_now_iso()
                        state.artifact_ids = []

                        # Register generated outputs in the ledger
                        for art in res.artifacts:
                            reg_art = self.registry.register(
                                artifact_id=art.id,
                                kind=art.kind,
                                producer_task_id=task.id,
                                phase=task.phase,
                                path=art.path,
                                metadata=art.metadata,
                            )
                            if reg_art.path and not reg_art.valid:
                                raise SchedulerError(f"Task {task.id} declared missing artifact: {reg_art.path}")
                            state.artifact_ids.append(reg_art.id)

                        completed.add(task.id)
                        self._emit("task_completed", {"plan_id": plan.plan_id, "task_id": task.id})

                    except Exception as exc:
                        err_msg = str(exc)
                        if self._should_retry(task, state, err_msg):
                            state.status = "pending"
                            state.error = err_msg
                            self._emit("task_retrying", {"plan_id": plan.plan_id, "task_id": task.id, "attempt": state.attempts})
                            if task.retry.backoff_seconds:
                                time.sleep(task.retry.backoff_seconds * state.attempts)
                        else:
                            state.status = "failed"
                            state.error = err_msg
                            state.completed_at = utc_now_iso()
                            failed.add(task.id)
                            self._emit("task_failed", {"plan_id": plan.plan_id, "task_id": task.id, "error": err_msg[:300]})

                    self._checkpoint(state_path, states)

                if not running:
                    self._run_safe_point(plan, completed, states)

        if failed and not allow_partial_failure:
            details = "; ".join(f"{t_id}: {states[t_id].error}" for t_id in sorted(failed))
            raise SchedulerError(f"Execution plan failed: {details}")

        self._emit("task_plan_completed", {"plan_id": plan.plan_id, "phase": plan.phase})
        return states

    def _run_safe_point(self, plan: ExecutionPlan, completed: set[str], states: dict[str, TaskState]) -> None:
        if self.safe_point is None:
            return
        pending = [t.id for t in plan.tasks if t.id not in completed and states[t.id].status not in {"failed", "skipped"}]
        self.safe_point({"plan_id": plan.plan_id, "phase": plan.phase, "completed": sorted(completed), "pending": pending})

    def validate_plan(self, plan: ExecutionPlan) -> None:
        """Verify plan has no duplicate IDs, missing prerequisites, or dependency cycles."""
        ids = [t.id for t in plan.tasks]
        if len(ids) != len(set(ids)):
            raise SchedulerError("Execution plan contains duplicate task ids.")

        known = set(ids)
        for t in plan.tasks:
            unknown = [dep for dep in t.depends_on if dep not in known]
            if unknown:
                raise SchedulerError(f"Task {t.id} has unknown dependencies: {unknown}")
            for r, amt in t.resources.items():
                if r not in self.pools:
                    raise SchedulerError(f"Task {t.id} requests unknown resource: {r}")
                if amt > self.pools[r]:
                    raise SchedulerError(f"Task {t.id} requests {amt} {r}, pool capacity is {self.pools[r]}")

        # Cycle detection
        visiting: set[str] = set()
        visited: set[str] = set()
        deps = {t.id: t.depends_on for t in plan.tasks}

        def visit(t_id: str) -> None:
            if t_id in visiting:
                raise SchedulerError(f"Execution plan contains a dependency cycle at {t_id}.")
            if t_id in visited:
                return
            visiting.add(t_id)
            for d in deps[t_id]:
                visit(d)
            visiting.remove(t_id)
            visited.add(t_id)

        for t_id in ids:
            visit(t_id)

    def resource_snapshot(self) -> dict[str, dict[str, int]]:
        with self._state_lock:
            return {r: {"capacity": self.pools[r], "in_use": self._resource_in_use[r]} for r in self.RESOURCE_ORDER}

    @staticmethod
    def _remaining_seconds(plan: ExecutionPlan) -> float | None:
        return float(plan.deadline_at_epoch) - time.time() if plan.deadline_at_epoch else None

    def _try_acquire(self, task: TaskSpec) -> bool:
        with self._state_lock:
            if any(k in self._conflicts_in_use for k in task.conflict_keys):
                return False
            for r in self.RESOURCE_ORDER:
                req = int(task.resources.get(r, 0))
                if req and self._resource_in_use[r] + req > self.pools[r]:
                    return False
            for r in self.RESOURCE_ORDER:
                self._resource_in_use[r] += int(task.resources.get(r, 0))
            self._conflicts_in_use.update(task.conflict_keys)
            return True

    def _release(self, task: TaskSpec) -> None:
        with self._state_lock:
            for r in self.RESOURCE_ORDER:
                self._resource_in_use[r] = max(0, self._resource_in_use[r] - int(task.resources.get(r, 0)))
            for k in task.conflict_keys:
                self._conflicts_in_use.discard(k)

    def _reuse_completed_task(self, task: TaskSpec, state: TaskState, states: dict[str, TaskState]) -> bool:
        if state.status != "completed":
            return False
        if state.task_fingerprint != self._task_fingerprint(task):
            state.status = "pending"
            return False
        expected_deps = {dep: states[dep].task_fingerprint for dep in task.depends_on}
        if state.dependency_fingerprints != expected_deps:
            state.status = "pending"
            return False
        arts = [self.registry.get(a_id) for a_id in state.artifact_ids]
        if state.artifact_ids and not all(a is not None and a.valid for a in arts):
            state.status = "pending"
            return False
        return True

    @staticmethod
    def _should_retry(task: TaskSpec, state: TaskState, message: str) -> bool:
        if state.attempts >= task.retry.max_attempts:
            return False
        lowered = message.lower()
        return any(m.lower() in lowered for m in task.retry.retryable_errors)

    @staticmethod
    def _task_fingerprint(task: TaskSpec) -> str:
        payload = task.model_dump()
        return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()

    def _load_states(self, plan: ExecutionPlan, state_path: Path) -> dict[str, TaskState]:
        states = self._new_states(plan)
        if not state_path.exists():
            return states
        try:
            payload = json.loads(state_path.read_text(encoding="utf-8"))
            for t_id, raw in payload.get("tasks", {}).items():
                if t_id in states:
                    s = TaskState.model_validate(raw)
                    if s.status == "running":
                        s.status = "pending"
                    states[t_id] = s
        except Exception:
            return self._new_states(plan)
        return states

    @staticmethod
    def _new_states(plan: ExecutionPlan) -> dict[str, TaskState]:
        return {t.id: TaskState(task_id=t.id) for t in plan.tasks}

    def _checkpoint(self, path: Path, states: dict[str, TaskState]) -> None:
        self._atomic_json_write(
            path,
            {"version": 1, "updated_at": utc_now_iso(), "tasks": {t_id: s.model_dump() for t_id, s in states.items()}},
        )

    @staticmethod
    def _atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        last_error: OSError | None = None
        for attempt in range(6):
            try:
                os.replace(temp_path, path)
                return
            except OSError as exc:
                last_error = exc
                if getattr(exc, "winerror", None) not in {5, 32, 33} and not isinstance(exc, PermissionError):
                    raise
                time.sleep(0.05 * (2 ** attempt))
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        if last_error is not None:
            raise last_error

    def _emit(self, event_type: str, payload: dict[str, Any]) -> None:
        if self.event_sink is not None:
            self.event_sink(event_type, payload)
