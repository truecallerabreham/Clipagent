from __future__ import annotations

import unittest
from pathlib import Path

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
        spec = TaskSpec(
            id="cut_01",
            phase="editing_execution",
            kind="video_cut",
            tool_name="cut_video",
            description="Cut intro highlight",
            arguments={"start": 0.0, "end": 5.0},
            depends_on=["dl_01", "  dl_01  ", "probe_01"],
            resources={"ffmpeg_pool": 1, "invalid_zero": 0, "  ": 2},
            priority=50,
        )
        self.assertEqual(spec.depends_on, ["dl_01", "probe_01"])
        self.assertEqual(spec.resources, {"ffmpeg_pool": 1})
        self.assertEqual(spec.priority, 50)

        # JSON round-trip
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

    def test_execution_plan_serialization(self) -> None:
        plan = ExecutionPlan(
            plan_id="plan_01",
            phase="editing_execution",
            goal="Assemble 60s Reel",
            tasks=[
                TaskSpec(id="t1", phase="prep", kind="download"),
                TaskSpec(id="t2", phase="edit", kind="cut", depends_on=["t1"]),
            ],
        )
        self.assertEqual(plan.plan_id, "plan_01")
        self.assertEqual(len(plan.tasks), 2)

        # JSON round-trip
        payload = plan.model_dump_json()
        restored = ExecutionPlan.model_validate_json(payload)
        self.assertEqual(restored.plan_id, "plan_01")
        self.assertEqual(len(restored.tasks), 2)
        self.assertEqual(restored.tasks[1].depends_on, ["t1"])


if __name__ == "__main__":
    unittest.main()

