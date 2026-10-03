from __future__ import annotations

import json
from pathlib import Path
import unittest

from script.orchestration.models import (
    ArtifactRef,
    ExecutionPlan,
    ResourcePoolConfig,
    RetryPolicy,
    TaskExecutionResult,
    TaskSpec,
    TaskState,
    utc_now_iso,
)


class TestOrchestrationModels(unittest.TestCase):
    def test_utc_now_iso(self) -> None:
        ts = utc_now_iso()
        self.assertIsInstance(ts, str)
        self.assertIn("T", ts)

    def test_retry_policy_defaults_and_validation(self) -> None:
        policy = RetryPolicy()
        self.assertEqual(policy.max_attempts, 1)
        self.assertEqual(policy.backoff_seconds, 0.0)
        self.assertIn("timeout", policy.retryable_errors)

        custom = RetryPolicy(max_attempts=3, backoff_seconds=2.5)
        self.assertEqual(custom.max_attempts, 3)
        self.assertEqual(custom.backoff_seconds, 2.5)

    def test_task_spec_validators_and_serialization(self) -> None:
        # Tests deduplication of list strings and resource validation
        spec = TaskSpec(
            id="cut_01",
            phase="editing_execution",
            kind="video_cut",
            tool_name="cut_video",
            description="Cut intro highlight",
            arguments={"start": 0.0, "end": 5.0},
            depends_on=["dl_01", "  dl_01  ", "probe_01"],  # duplicate with whitespace
            resources={"ffmpeg_pool": 1, "invalid_zero": 0, "  ": 2},
            priority=50,
        )
        # Deduplication should produce ["dl_01", "probe_01"]
        self.assertEqual(spec.depends_on, ["dl_01", "probe_01"])
        # Resource normalization should prune 0 and empty keys
        self.assertEqual(spec.resources, {"ffmpeg_pool": 1})
        self.assertEqual(spec.priority, 50)

        # JSON serialization round trip
        payload = spec.model_dump_json()
        restored = TaskSpec.model_validate_json(payload)
        self.assertEqual(restored.id, "cut_01")
        self.assertEqual(restored.tool_name, "cut_video")

    def test_artifact_ref_and_resolved_path(self) -> None:
        art = ArtifactRef(
            id="art_video_01",
            kind="video_file",
            path="temp/highlight.mp4",
            producer_task_id="cut_01",
            phase="editing_execution",
            size_bytes=1048576,
        )
        self.assertEqual(art.id, "art_video_01")
        resolved = art.resolved_path()
        self.assertIsNotNone(resolved)
        self.assertTrue(str(resolved).endswith("highlight.mp4"))

    def test_task_state_and_execution_result(self) -> None:
        state = TaskState(
            task_id="cut_01",
            status="completed",
            attempts=1,
            elapsed_seconds=2.45,
            result={"output_path": "temp/highlight.mp4"},
            artifact_ids=["art_video_01"],
        )
        self.assertEqual(state.status, "completed")
        self.assertEqual(state.elapsed_seconds, 2.45)

        art = ArtifactRef(id="art_1", kind="video", producer_task_id="cut_01", phase="p1")
        exec_res = TaskExecutionResult(data={"success": True}, artifacts=[art])
        self.assertTrue(exec_res.data["success"])
        self.assertEqual(len(exec_res.artifacts), 1)

    def test_resource_pool_config(self) -> None:
        pools = ResourcePoolConfig(
            ffmpeg_pool=4,
            download_pool=2,
            llm_pool=5,
        )
        d = pools.as_dict()
        self.assertEqual(d["ffmpeg_pool"], 4)
        self.assertEqual(d["download_pool"], 2)
        self.assertEqual(d["llm_pool"], 5)
        self.assertEqual(d["export_pool"], 1)

    def test_execution_plan_dag_validation_and_cycles(self) -> None:
        # Missing dependency should raise KeyError
        plan_missing = ExecutionPlan(
            plan_id="plan_bad",
            phase="test",
            tasks=[
                TaskSpec(id="t1", phase="p", kind="k", depends_on=["non_existent_task"])
            ]
        )
        with self.assertRaises(KeyError):
            plan_missing.validate_dag()

        # Circular cycle: A -> B -> A
        plan_cycle = ExecutionPlan(
            plan_id="plan_cycle",
            phase="test",
            tasks=[
                TaskSpec(id="A", phase="p", kind="k", depends_on=["B"]),
                TaskSpec(id="B", phase="p", kind="k", depends_on=["A"]),
            ]
        )
        with self.assertRaises(ValueError) as ctx:
            plan_cycle.validate_dag()
        self.assertIn("Circular dependency cycle detected", str(ctx.exception))

    def test_execution_plan_topological_sort_and_ready_tasks(self) -> None:
        plan = ExecutionPlan(
            plan_id="diamond_plan",
            phase="editing_execution",
            tasks=[
                TaskSpec(id="t1", phase="p", kind="dl", priority=10),
                TaskSpec(id="t2", phase="p", kind="probe", depends_on=["t1"], priority=50),
                TaskSpec(id="t3", phase="p", kind="audio", depends_on=["t1"], priority=20),
                TaskSpec(id="t4", phase="p", kind="merge", depends_on=["t2", "t3"], priority=100),
            ]
        )
        self.assertTrue(plan.validate_dag())
        sorted_tasks = plan.topological_sort()
        ids = [t.id for t in sorted_tasks]

        self.assertEqual(ids[0], "t1")
        # t2 has higher priority (50) than t3 (20), so it should precede t3
        self.assertEqual(ids[1], "t2")
        self.assertEqual(ids[2], "t3")
        self.assertEqual(ids[3], "t4")

        # Ready task discovery
        ready_init = plan.get_ready_tasks(completed_task_ids=set())
        self.assertEqual([t.id for t in ready_init], ["t1"])

        ready_after_t1 = plan.get_ready_tasks(completed_task_ids={"t1"})
        # Both t2 and t3 ready, t2 sorted first by priority (50 > 20)
        self.assertEqual([t.id for t in ready_after_t1], ["t2", "t3"])

        # ASCII visualization
        ascii_text = plan.visualize_ascii()
        self.assertIn("ExecutionPlan: diamond_plan", ascii_text)
        self.assertIn("t1", ascii_text)
        self.assertIn("t4", ascii_text)


if __name__ == "__main__":
    unittest.main()
