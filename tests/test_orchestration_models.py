from __future__ import annotations

import json
import unittest

from script.orchestration.models import (
    ArtifactRef,
    ResourceRequirement,
    ResourceType,
    TaskDefinition,
    TaskGraph,
    TaskPriority,
    TaskResult,
    TaskStatus,
)


class TestOrchestrationModels(unittest.TestCase):
    def test_enums_and_priority_ordering(self) -> None:
        self.assertEqual(TaskStatus.READY.value, "ready")
        self.assertEqual(TaskStatus.COMPLETED.value, "completed")
        self.assertEqual(ResourceType.CPU_HEAVY.value, "cpu_heavy")

        # Priority ordering
        self.assertGreater(TaskPriority.CRITICAL, TaskPriority.HIGH)
        self.assertGreater(TaskPriority.HIGH, TaskPriority.NORMAL)
        self.assertGreater(TaskPriority.NORMAL, TaskPriority.LOW)
        self.assertGreater(TaskPriority.LOW, TaskPriority.BACKGROUND)

    def test_resource_requirement_serialization(self) -> None:
        req = ResourceRequirement(
            resource_type=ResourceType.CPU_HEAVY,
            cpu_cores=4,
            memory_mb=2048,
            gpu_vram_mb=0,
            concurrency_key="ffmpeg_encoder",
        )
        d = req.to_dict()
        self.assertEqual(d["resource_type"], "cpu_heavy")
        self.assertEqual(d["cpu_cores"], 4)

        reconstructed = ResourceRequirement.from_dict(d)
        self.assertEqual(reconstructed.resource_type, ResourceType.CPU_HEAVY)
        self.assertEqual(reconstructed.memory_mb, 2048)
        self.assertEqual(reconstructed.concurrency_key, "ffmpeg_encoder")

    def test_artifact_ref_serialization(self) -> None:
        art = ArtifactRef(
            artifact_id="art_123",
            artifact_type="video_file",
            path="temp/video.mp4",
            metadata={"duration": 12.5, "resolution": "1920x1080"},
        )
        d = art.to_dict()
        self.assertEqual(d["artifact_id"], "art_123")
        self.assertEqual(d["metadata"]["duration"], 12.5)

        reconstructed = ArtifactRef.from_dict(d)
        self.assertEqual(reconstructed.artifact_id, "art_123")
        self.assertEqual(reconstructed.path, "temp/video.mp4")

    def test_task_definition_serialization(self) -> None:
        task = TaskDefinition(
            task_id="task_cut_01",
            task_name="Cut Highlight",
            action="cut_video",
            params={"video_path": "clip.mp4", "start_time": 1.0, "end_time": 5.0},
            dependencies=["task_dl_01"],
            priority=TaskPriority.HIGH,
            max_retries=3,
            timeout_seconds=120.0,
            tags=["highlight", "phase2"],
        )
        d = task.to_dict()
        self.assertEqual(d["task_id"], "task_cut_01")
        self.assertEqual(d["priority"], int(TaskPriority.HIGH))

        reconstructed = TaskDefinition.from_dict(d)
        self.assertEqual(reconstructed.task_id, "task_cut_01")
        self.assertEqual(reconstructed.priority, TaskPriority.HIGH)
        self.assertEqual(reconstructed.dependencies, ["task_dl_01"])
        self.assertEqual(reconstructed.tags, ["highlight", "phase2"])

    def test_task_result_serialization(self) -> None:
        res = TaskResult(
            task_id="task_cut_01",
            status=TaskStatus.COMPLETED,
            output={"output_path": "temp/highlight.mp4"},
            output_artifacts=[ArtifactRef(artifact_id="art_cut", artifact_type="video_file")],
            execution_time_seconds=1.456,
        )
        d = res.to_dict()
        self.assertEqual(d["status"], "completed")
        self.assertEqual(d["execution_time_seconds"], 1.456)

        reconstructed = TaskResult.from_dict(d)
        self.assertEqual(reconstructed.status, TaskStatus.COMPLETED)
        self.assertEqual(len(reconstructed.output_artifacts), 1)

    def test_task_graph_duplicate_id_raises_error(self) -> None:
        graph = TaskGraph(name="test_graph")
        t1 = TaskDefinition(task_id="t1", task_name="Task 1", action="action_1")
        t2 = TaskDefinition(task_id="t1", task_name="Duplicate", action="action_2")

        graph.add_task(t1)
        with self.assertRaises(ValueError):
            graph.add_task(t2)

    def test_task_graph_missing_dependency_raises_key_error(self) -> None:
        graph = TaskGraph(name="test_graph")
        t1 = TaskDefinition(task_id="t1", task_name="Task 1", action="action_1", dependencies=["missing_task"])
        graph.add_task(t1)

        with self.assertRaises(KeyError):
            graph.validate_dag()

    def test_task_graph_cycle_detection(self) -> None:
        # Two-node circular cycle: A -> B -> A
        graph = TaskGraph(name="cycle_graph")
        tA = TaskDefinition(task_id="A", task_name="Task A", action="noop", dependencies=["B"])
        tB = TaskDefinition(task_id="B", task_name="Task B", action="noop", dependencies=["A"])
        graph.add_task(tA)
        graph.add_task(tB)

        with self.assertRaises(ValueError) as ctx:
            graph.validate_dag()
        self.assertIn("Circular dependency cycle detected", str(ctx.exception))

    def test_task_graph_topological_sort_and_dependencies(self) -> None:
        # Diamond Workflow:
        #        t1 (Download)
        #        /           \
        #    t2 (Inspect)    t3 (Extract Audio)
        #        \           /
        #       t4 (Assemble)
        graph = TaskGraph(name="diamond_pipeline")
        t1 = TaskDefinition(task_id="t1", task_name="Download", action="download_video")
        t2 = TaskDefinition(task_id="t2", task_name="Inspect", action="inspect_video", dependencies=["t1"])
        t3 = TaskDefinition(task_id="t3", task_name="Extract Audio", action="extract_audio", dependencies=["t1"])
        t4 = TaskDefinition(task_id="t4", task_name="Assemble", action="assemble_video", dependencies=["t2", "t3"])

        for t in (t1, t2, t3, t4):
            graph.add_task(t)

        self.assertTrue(graph.validate_dag())
        sorted_tasks = graph.topological_sort()
        ids = [t.task_id for t in sorted_tasks]

        # Verify dependency ordering
        self.assertEqual(ids[0], "t1")
        self.assertIn("t2", ids[1:3])
        self.assertIn("t3", ids[1:3])
        self.assertEqual(ids[3], "t4")

        # Test dependency queries
        self.assertEqual(graph.get_dependencies("t4"), ["t2", "t3"])
        self.assertEqual(graph.get_dependents("t1"), ["t2", "t3"])

    def test_task_graph_get_ready_tasks_and_priorities(self) -> None:
        graph = TaskGraph(name="priority_pipeline")
        t1 = TaskDefinition(task_id="t1", task_name="Root Normal", action="act", priority=TaskPriority.NORMAL)
        t2 = TaskDefinition(task_id="t2", task_name="Root High", action="act", priority=TaskPriority.HIGH)
        t3 = TaskDefinition(task_id="t3", task_name="Child of T2", action="act", dependencies=["t2"], priority=TaskPriority.CRITICAL)

        for t in (t1, t2, t3):
            graph.add_task(t)

        # Initially, only t1 and t2 (roots) are ready. t2 has higher priority, so it comes first!
        ready = graph.get_ready_tasks(completed_task_ids=set())
        ready_ids = [t.task_id for t in ready]
        self.assertEqual(ready_ids, ["t2", "t1"])

        # When t2 completes, t3 becomes ready (and has CRITICAL priority)
        ready_after_t2 = graph.get_ready_tasks(completed_task_ids={"t2"}, active_or_running_ids={"t1"})
        self.assertEqual([t.task_id for t in ready_after_t2], ["t3"])

    def test_task_graph_json_serialization_and_ascii(self) -> None:
        graph = TaskGraph(name="test_export_graph")
        t1 = TaskDefinition(task_id="t1", task_name="Task 1", action="action_1")
        t2 = TaskDefinition(task_id="t2", task_name="Task 2", action="action_2", dependencies=["t1"])
        graph.add_task(t1)
        graph.add_task(t2)

        # JSON round-trip
        json_str = graph.to_json()
        reconstructed = TaskGraph.from_json(json_str)
        self.assertEqual(reconstructed.name, "test_export_graph")
        self.assertEqual(len(reconstructed._tasks), 2)
        self.assertEqual(reconstructed.get_dependencies("t2"), ["t1"])

        # ASCII visualization
        ascii_tree = graph.visualize_ascii()
        self.assertIn("TaskGraph: test_export_graph", ascii_tree)
        self.assertIn("Task 1", ascii_tree)
        self.assertIn("Task 2", ascii_tree)


if __name__ == "__main__":
    unittest.main()
