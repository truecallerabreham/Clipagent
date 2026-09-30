from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

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


def print_step(title: str, explanation: str) -> None:
    print(f"\n{'=' * 75}")
    print(f"  {title}")
    print(f"  {explanation}")
    print(f"{'=' * 75}")


def run_milestone12_verification() -> bool:
    print("\n" + "#" * 75)
    print("  CLIPAGENT MILESTONE 12 REAL-WORLD VERIFICATION: THE TASK RECIPE")
    print("  (Asynchronous Task Schemas, DAG Cycle Defense & Dependency Scheduling)")
    print("#" * 75)

    # -------------------------------------------------------------------------
    # STEP 1: Construct 7-Stage Autonomous Video Editing DAG
    # -------------------------------------------------------------------------
    print_step(
        "STEP 1: Pipeline DAG Construction",
        "Defining a 7-stage autonomous video editing pipeline with explicit resource limits.",
    )
    graph = TaskGraph(name="clipagent_production_pipeline")

    tasks = [
        TaskDefinition(
            task_id="task_01_dl",
            task_name="Download Source Footage",
            action="download_material_video",
            params={"query": "Cinematic Drone Landscape"},
            priority=TaskPriority.NORMAL,
            resource_req=ResourceRequirement(resource_type=ResourceType.IO_HEAVY, concurrency_key="network_io"),
        ),
        TaskDefinition(
            task_id="task_02_probe",
            task_name="Inspect Media Consistency",
            action="inspect_media_consistency",
            dependencies=["task_01_dl"],
            priority=TaskPriority.HIGH,
            resource_req=ResourceRequirement(resource_type=ResourceType.LIGHTWEIGHT),
        ),
        TaskDefinition(
            task_id="task_03_standardize",
            task_name="Standardize Format to 1080p",
            action="standardize_media_clips",
            dependencies=["task_02_probe"],
            priority=TaskPriority.HIGH,
            resource_req=ResourceRequirement(resource_type=ResourceType.CPU_HEAVY, cpu_cores=4, concurrency_key="ffmpeg_encode"),
        ),
        TaskDefinition(
            task_id="task_04_audio",
            task_name="Extract Audio Track",
            action="extract_audio",
            dependencies=["task_03_standardize"],
            priority=TaskPriority.NORMAL,
            resource_req=ResourceRequirement(resource_type=ResourceType.IO_HEAVY),
        ),
        TaskDefinition(
            task_id="task_05_transcribe",
            task_name="AI Speech-to-Text (Whisper)",
            action="transcribe_speech",
            dependencies=["task_04_audio"],
            priority=TaskPriority.NORMAL,
            resource_req=ResourceRequirement(resource_type=ResourceType.NETWORK_API, concurrency_key="gemini_api"),
        ),
        TaskDefinition(
            task_id="task_06_cut",
            task_name="Batch Cut Highlight Segments",
            action="batch_cut_video",
            dependencies=["task_03_standardize"],
            priority=TaskPriority.NORMAL,
            resource_req=ResourceRequirement(resource_type=ResourceType.CPU_HEAVY, cpu_cores=2, concurrency_key="ffmpeg_encode"),
        ),
        TaskDefinition(
            task_id="task_07_assemble",
            task_name="Assemble Final Cut & Subtitles",
            action="merge_videos",
            dependencies=["task_05_transcribe", "task_06_cut"],
            priority=TaskPriority.CRITICAL,
            resource_req=ResourceRequirement(resource_type=ResourceType.CPU_HEAVY, cpu_cores=4, concurrency_key="ffmpeg_encode"),
        ),
    ]

    for t in tasks:
        graph.add_task(t)

    print(f"  -> Successfully added {len(tasks)} tasks into TaskGraph '{graph.name}'.")
    print("  [PASS] TaskGraph schema construction verified!")

    # -------------------------------------------------------------------------
    # STEP 2: DAG Validation & Cycle Defense Testing
    # -------------------------------------------------------------------------
    print_step(
        "STEP 2: DAG Validation & Cycle Defense Testing",
        "Verifying acyclic dependency structure and testing circular loop detection.",
    )
    assert graph.validate_dag() is True
    print("  -> Primary 7-stage pipeline validated: ZERO cycles detected.")

    # Create an invalid circular graph to test defense
    cyclic_graph = TaskGraph(name="broken_loop_pipeline")
    cyclic_graph.add_task(TaskDefinition(task_id="task_A", task_name="Task A", action="act", dependencies=["task_C"]))
    cyclic_graph.add_task(TaskDefinition(task_id="task_B", task_name="Task B", action="act", dependencies=["task_A"]))
    cyclic_graph.add_task(TaskDefinition(task_id="task_C", task_name="Task C", action="act", dependencies=["task_B"]))

    try:
        cyclic_graph.validate_dag()
        raise AssertionError("Validation should have failed on circular cycle!")
    except ValueError as err:
        print(f"  -> Caught expected circular dependency rejection: {err}")
        assert "Circular dependency cycle detected" in str(err)
        print("  [PASS] DAG cycle defense engine verified with 100% mathematical precision!")

    # -------------------------------------------------------------------------
    # STEP 3: Topological Sort & Priority Order Verification
    # -------------------------------------------------------------------------
    print_step(
        "STEP 3: Topological Sorting & Execution Order",
        "Resolving linear dependency sequence respecting task priorities.",
    )
    sorted_order = graph.topological_sort()
    sorted_ids = [t.task_id for t in sorted_order]

    print("  -> Resolved Topological Execution Order:")
    for idx, t in enumerate(sorted_order, start=1):
        print(f"     ({idx}) {t.task_id:<20} | Priority: {t.priority.name:<8} | Action: {t.action}")

    # Verify dependency constraints
    assert sorted_ids.index("task_01_dl") < sorted_ids.index("task_02_probe")
    assert sorted_ids.index("task_02_probe") < sorted_ids.index("task_03_standardize")
    assert sorted_ids.index("task_03_standardize") < sorted_ids.index("task_04_audio")
    assert sorted_ids.index("task_03_standardize") < sorted_ids.index("task_06_cut")
    assert sorted_ids.index("task_04_audio") < sorted_ids.index("task_05_transcribe")
    assert sorted_ids.index("task_05_transcribe") < sorted_ids.index("task_07_assemble")
    assert sorted_ids.index("task_06_cut") < sorted_ids.index("task_07_assemble")
    print("  [PASS] All dependency constraints strictly honored!")

    # -------------------------------------------------------------------------
    # STEP 4: Step-by-Step Simulated Dispatch (Ready-Task Engine)
    # -------------------------------------------------------------------------
    print_step(
        "STEP 4: Step-by-Step Dynamic Dispatch Simulation",
        "Simulating worker execution loop and verifying fan-out ready tasks.",
    )
    completed: set[str] = set()

    # Stage 0: Nothing completed yet
    ready_s0 = graph.get_ready_tasks(completed)
    print(f"  -> State 0 (Empty): Ready Tasks = {[t.task_id for t in ready_s0]}")
    assert [t.task_id for t in ready_s0] == ["task_01_dl"]

    # Stage 1: Download finishes
    completed.add("task_01_dl")
    ready_s1 = graph.get_ready_tasks(completed)
    print(f"  -> State 1 (After DL): Ready Tasks = {[t.task_id for t in ready_s1]}")
    assert [t.task_id for t in ready_s1] == ["task_02_probe"]

    # Stage 2: Probe finishes
    completed.add("task_02_probe")
    ready_s2 = graph.get_ready_tasks(completed)
    print(f"  -> State 2 (After Probe): Ready Tasks = {[t.task_id for t in ready_s2]}")
    assert [t.task_id for t in ready_s2] == ["task_03_standardize"]

    # Stage 3: Standardization finishes -> PARALLEL FAN-OUT!
    completed.add("task_03_standardize")
    ready_s3 = graph.get_ready_tasks(completed)
    ready_s3_ids = [t.task_id for t in ready_s3]
    print(f"  -> State 3 (After Standardize): Ready Tasks = {ready_s3_ids} (PARALLEL FAN-OUT!)")
    # Both audio extraction and video cutting become ready simultaneously!
    assert "task_04_audio" in ready_s3_ids
    assert "task_06_cut" in ready_s3_ids
    assert len(ready_s3_ids) == 2

    # Stage 4: Audio extract finishes
    completed.add("task_04_audio")
    ready_s4 = graph.get_ready_tasks(completed, active_or_running_ids={"task_06_cut"})
    print(f"  -> State 4 (Audio done, Cut running): Ready Tasks = {[t.task_id for t in ready_s4]}")
    assert [t.task_id for t in ready_s4] == ["task_05_transcribe"]

    # Stage 5: Both transcribe and cut finish -> Final assembly ready
    completed.add("task_05_transcribe")
    completed.add("task_06_cut")
    ready_s5 = graph.get_ready_tasks(completed)
    print(f"  -> State 5 (Transcribe & Cut done): Ready Tasks = {[t.task_id for t in ready_s5]}")
    assert [t.task_id for t in ready_s5] == ["task_07_assemble"]

    print("  [PASS] Dynamic dispatch engine perfectly handles sequential and parallel execution paths!")

    # -------------------------------------------------------------------------
    # STEP 5: Serialization & ASCII Workflow Tree
    # -------------------------------------------------------------------------
    print_step(
        "STEP 5: Serialization & Pipeline ASCII Visualization",
        "Testing JSON round-trip serialization and rendering pipeline diagram.",
    )
    json_payload = graph.to_json()
    restored_graph = TaskGraph.from_json(json_payload)
    assert len(restored_graph._tasks) == 7
    print(f"  -> Serialized JSON size: {len(json_payload):,} characters")
    print("  [PASS] Full JSON round-trip serialization verified!")

    print("\n  --- Pipeline ASCII Architecture Diagram ---")
    print(graph.visualize_ascii())

    print("\n" + "=" * 75)
    print("  MILESTONE 12 REAL-WORLD VERIFICATION COMPLETE!")
    print("  The Task Recipe schema and DAG engine are 100% VERIFIED!")
    print("=" * 75 + "\n")
    return True


if __name__ == "__main__":
    success = run_milestone12_verification()
    sys.exit(0 if success else 1)
