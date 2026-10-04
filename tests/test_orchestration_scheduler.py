from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from script.orchestration import (
    ArtifactRef,
    ArtifactRegistry,
    ExecutionPlan,
    ResourcePoolConfig,
    ResourceScheduler,
    SchedulerError,
    TaskExecutionResult,
    TaskSpec,
)


class TestResourceScheduler(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)
        self.registry = ArtifactRegistry(self.workspace)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _scheduler(self, **pool_overrides: int) -> ResourceScheduler:
        values = ResourcePoolConfig().model_dump()
        values.update(pool_overrides)
        return ResourceScheduler(
            pools=ResourcePoolConfig(**values),
            workspace=self.workspace,
            artifact_registry=self.registry,
        )

    def test_rejects_cycle(self) -> None:
        """Scheduler must reject plans containing circular dependency deadlocks."""
        plan = ExecutionPlan(
            plan_id="cycle_plan",
            phase="test",
            tasks=[
                TaskSpec(id="a", phase="test", kind="x", depends_on=["b"]),
                TaskSpec(id="b", phase="test", kind="x", depends_on=["a"]),
            ],
        )
        with self.assertRaises(SchedulerError):
            self._scheduler().validate_plan(plan)

    def test_dependency_order_execution(self) -> None:
        """Prerequisites must complete before dependent tasks are dispatched."""
        observed: list[str] = []
        plan = ExecutionPlan(
            plan_id="order_plan",
            phase="test",
            tasks=[
                TaskSpec(id="first", phase="test", kind="download"),
                TaskSpec(id="second", phase="test", kind="cut", depends_on=["first"]),
            ],
        )

        def execute(task: TaskSpec, dependencies):
            if task.id == "second":
                self.assertEqual(dependencies["first"].status, "completed")
            observed.append(task.id)
            return TaskExecutionResult()

        self._scheduler().run(plan, execute)
        self.assertEqual(observed, ["first", "second"])

    def test_resource_pool_bounds_parallelism(self) -> None:
        """Concurrency must never exceed configured resource pool limits."""
        active = 0
        peak = 0
        lock = threading.Lock()
        plan = ExecutionPlan(
            plan_id="pool_plan",
            phase="test",
            tasks=[
                TaskSpec(
                    id=f"dl_task_{i}",
                    phase="test",
                    kind="download",
                    resources={"download_pool": 1},
                )
                for i in range(4)
            ],
        )

        def execute(task: TaskSpec, dependencies):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.05)
            with lock:
                active -= 1
            return TaskExecutionResult()

        # Limit download_pool to 2 concurrent workers
        self._scheduler(download_pool=2).run(plan, execute)
        self.assertEqual(peak, 2)

    def test_conflict_key_mutual_exclusion(self) -> None:
        """Tasks sharing the same conflict key must execute sequentially."""
        active = 0
        peak = 0
        lock = threading.Lock()
        plan = ExecutionPlan(
            plan_id="conflict_plan",
            phase="test",
            tasks=[
                TaskSpec(
                    id=f"writer_{i}",
                    phase="test",
                    kind="render",
                    resources={"ffmpeg_pool": 1},
                    conflict_keys=["mutex:output.mp4"],
                )
                for i in range(2)
            ],
        )

        def execute(task: TaskSpec, dependencies):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.05)
            with lock:
                active -= 1
            return TaskExecutionResult()

        # Despite ffmpeg_pool capacity = 2, conflict key forces serialization (peak = 1)
        self._scheduler(ffmpeg_pool=2).run(plan, execute)
        self.assertEqual(peak, 1)

    def test_resume_reuses_valid_completed_task(self) -> None:
        """Completed tasks with intact disk artifacts should not be re-executed on resume."""
        calls = 0
        output_file = self.workspace / "cut_output.mp4"
        plan = ExecutionPlan(
            plan_id="resume_plan",
            phase="test",
            tasks=[TaskSpec(id="task_cut", phase="test", kind="cut")],
        )

        def execute(task: TaskSpec, dependencies):
            nonlocal calls
            calls += 1
            output_file.write_bytes(b"[VIDEO_OUTPUT_DATA]")
            return TaskExecutionResult(
                artifacts=[
                    ArtifactRef(
                        id="art_cut",
                        kind="video_clip",
                        path=str(output_file),
                        producer_task_id=task.id,
                        phase=task.phase,
                    )
                ]
            )

        scheduler = self._scheduler()
        scheduler.run(plan, execute)
        self.assertEqual(calls, 1)

        # Second run with resume=True should reuse completed task and NOT execute again
        scheduler.run(plan, execute, resume=True)
        self.assertEqual(calls, 1)

    def test_tampered_artifact_causes_reexecution(self) -> None:
        """If an artifact is tampered or deleted, task must be automatically re-executed."""
        calls = 0
        output_file = self.workspace / "cut_output.mp4"
        plan = ExecutionPlan(
            plan_id="tamper_plan",
            phase="test",
            tasks=[TaskSpec(id="task_cut", phase="test", kind="cut")],
        )

        def execute(task: TaskSpec, dependencies):
            nonlocal calls
            calls += 1
            output_file.write_bytes(b"[ORIGINAL_VIDEO_DATA]")
            return TaskExecutionResult(
                artifacts=[
                    ArtifactRef(
                        id="art_cut",
                        kind="video_clip",
                        path=str(output_file),
                        producer_task_id=task.id,
                        phase=task.phase,
                    )
                ]
            )

        scheduler = self._scheduler()
        scheduler.run(plan, execute)
        self.assertEqual(calls, 1)

        # Tamper with file
        output_file.write_bytes(b"[CORRUPTED_TAMPERED_DATA]")
        scheduler.run(plan, execute, resume=True)
        self.assertEqual(calls, 2)

    def test_retry_on_transient_error(self) -> None:
        """Task with retry policy should re-attempt execution on transient errors."""
        attempts = 0
        plan = ExecutionPlan(
            plan_id="retry_plan",
            phase="test",
            tasks=[
                TaskSpec(
                    id="flaky_task",
                    phase="test",
                    kind="api_call",
                    retry={"max_attempts": 3, "backoff_seconds": 0.01, "retryable_errors": ["rate limit"]},
                )
            ],
        )

        def execute(task: TaskSpec, dependencies):
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise RuntimeError("API error: 429 rate limit exceeded")
            return TaskExecutionResult(data={"status": "recovered"})

        scheduler = self._scheduler()
        states = scheduler.run(plan, execute)
        self.assertEqual(attempts, 3)
        self.assertEqual(states["flaky_task"].status, "completed")
        self.assertEqual(states["flaky_task"].result, {"status": "recovered"})


if __name__ == "__main__":
    unittest.main()
