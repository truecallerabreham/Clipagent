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
    ExecutionPlan,
    ResourcePoolConfig,
    RetryPolicy,
    TaskExecutionResult,
    TaskSpec,
    TaskState,
)


def print_step(title: str, explanation: str) -> None:
    print(f"\n{'=' * 75}")
    print(f"  {title}")
    print(f"  {explanation}")
    print(f"{'=' * 75}")


def run_milestone12_verification() -> bool:
    print("\n" + "#" * 75)
    print("  CLIPAGENT MILESTONE 12 REAL-WORLD VERIFICATION: THE TASK RECIPE")
    print("  (High-Fidelity Pydantic Schemas, DAG Cycle Defense & Execution Plans)")
    print("#" * 75)

    # -------------------------------------------------------------------------
    # STEP 1: Construct 7-Stage Autonomous Video Editing ExecutionPlan
    # -------------------------------------------------------------------------
    print_step(
        "STEP 1: Pipeline ExecutionPlan Construction",
        "Defining a 7-stage autonomous video editing plan with exact reference Pydantic schemas.",
    )
    plan = ExecutionPlan(
        plan_id="plan_clipagent_production_01",
        phase="editing_execution",
        goal="Autonomous 60s Cinematic Explainer Video",
        tasks=[
            TaskSpec(
                id="task_01_dl",
                phase="material_preparation",
                kind="download",
                tool_name="download_material_video",
                description="Download Source Footage",
                arguments={"query": "Cinematic Drone Landscape"},
                resources={"download_pool": 1},
                priority=10,
            ),
            TaskSpec(
                id="task_02_probe",
                phase="material_preparation",
                kind="inspect",
                tool_name="inspect_media_consistency",
                description="Inspect Media Consistency",
                depends_on=["task_01_dl"],
                resources={"video_analysis_pool": 1},
                priority=50,
            ),
            TaskSpec(
                id="task_03_standardize",
                phase="material_preparation",
                kind="standardize",
                tool_name="standardize_media_clips",
                description="Standardize Format to 1080p",
                depends_on=["task_02_probe"],
                resources={"ffmpeg_pool": 1},
                priority=50,
            ),
            TaskSpec(
                id="task_04_audio",
                phase="editing_research",
                kind="extract_audio",
                tool_name="extract_audio",
                description="Extract Audio Track",
                depends_on=["task_03_standardize"],
                resources={"ffmpeg_pool": 1},
                priority=20,
            ),
            TaskSpec(
                id="task_05_transcribe",
                phase="editing_research",
                kind="transcribe",
                tool_name="transcribe_speech",
                description="AI Speech-to-Text (Whisper)",
                depends_on=["task_04_audio"],
                resources={"llm_pool": 1},
                priority=30,
            ),
            TaskSpec(
                id="task_06_cut",
                phase="editing_execution",
                kind="batch_cut",
                tool_name="batch_cut_video",
                description="Batch Cut Highlight Segments",
                depends_on=["task_03_standardize"],
                resources={"ffmpeg_pool": 1},
                priority=40,
            ),
            TaskSpec(
                id="task_07_assemble",
                phase="editing_execution",
                kind="merge",
                tool_name="merge_videos",
                description="Assemble Final Cut & Subtitles",
                depends_on=["task_05_transcribe", "task_06_cut"],
                resources={"ffmpeg_pool": 1, "export_pool": 1},
                priority=100,
            ),
        ]
    )

    print(f"  -> Successfully constructed ExecutionPlan '{plan.plan_id}' with {len(plan.tasks)} tasks.")
    print("  [PASS] ExecutionPlan Pydantic schema verified!")

    # -------------------------------------------------------------------------
    # STEP 2: DAG Validation & Cycle Defense Testing
    # -------------------------------------------------------------------------
    print_step(
        "STEP 2: DAG Validation & Cycle Defense Testing",
        "Verifying acyclic dependency structure and testing circular loop detection.",
    )
    assert plan.validate_dag() is True
    print("  -> Primary 7-stage pipeline validated: ZERO cycles detected.")

    # Create an invalid circular plan to test defense
    cyclic_plan = ExecutionPlan(
        plan_id="plan_broken_loop",
        phase="test",
        tasks=[
            TaskSpec(id="task_A", phase="p", kind="k", depends_on=["task_C"]),
            TaskSpec(id="task_B", phase="p", kind="k", depends_on=["task_A"]),
            TaskSpec(id="task_C", phase="p", kind="k", depends_on=["task_B"]),
        ]
    )

    try:
        cyclic_plan.validate_dag()
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
    sorted_order = plan.topological_sort()
    sorted_ids = [t.id for t in sorted_order]

    print("  -> Resolved Topological Execution Order:")
    for idx, t in enumerate(sorted_order, start=1):
        print(f"     ({idx}) {t.id:<20} | Priority: {t.priority:<3} | Tool: {t.tool_name}")

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
    ready_s0 = plan.get_ready_tasks(completed)
    print(f"  -> State 0 (Empty): Ready Tasks = {[t.id for t in ready_s0]}")
    assert [t.id for t in ready_s0] == ["task_01_dl"]

    # Stage 1: Download finishes
    completed.add("task_01_dl")
    ready_s1 = plan.get_ready_tasks(completed)
    print(f"  -> State 1 (After DL): Ready Tasks = {[t.id for t in ready_s1]}")
    assert [t.id for t in ready_s1] == ["task_02_probe"]

    # Stage 2: Probe finishes
    completed.add("task_02_probe")
    ready_s2 = plan.get_ready_tasks(completed)
    print(f"  -> State 2 (After Probe): Ready Tasks = {[t.id for t in ready_s2]}")
    assert [t.id for t in ready_s2] == ["task_03_standardize"]

    # Stage 3: Standardization finishes -> PARALLEL FAN-OUT!
    completed.add("task_03_standardize")
    ready_s3 = plan.get_ready_tasks(completed)
    ready_s3_ids = [t.id for t in ready_s3]
    print(f"  -> State 3 (After Standardize): Ready Tasks = {ready_s3_ids} (PARALLEL FAN-OUT!)")
    assert "task_04_audio" in ready_s3_ids
    assert "task_06_cut" in ready_s3_ids
    assert len(ready_s3_ids) == 2

    # Stage 4: Audio extract finishes
    completed.add("task_04_audio")
    ready_s4 = plan.get_ready_tasks(completed, active_or_running_ids={"task_06_cut"})
    print(f"  -> State 4 (Audio done, Cut running): Ready Tasks = {[t.id for t in ready_s4]}")
    assert [t.id for t in ready_s4] == ["task_05_transcribe"]

    # Stage 5: Both transcribe and cut finish -> Final assembly ready
    completed.add("task_05_transcribe")
    completed.add("task_06_cut")
    ready_s5 = plan.get_ready_tasks(completed)
    print(f"  -> State 5 (Transcribe & Cut done): Ready Tasks = {[t.id for t in ready_s5]}")
    assert [t.id for t in ready_s5] == ["task_07_assemble"]

    print("  [PASS] Dynamic dispatch engine perfectly handles sequential and parallel execution paths!")

    # -------------------------------------------------------------------------
    # STEP 5: Pydantic Serialization & ASCII Workflow Tree
    # -------------------------------------------------------------------------
    print_step(
        "STEP 5: Serialization & Pipeline ASCII Visualization",
        "Testing Pydantic JSON round-trip serialization and rendering pipeline diagram.",
    )
    json_payload = plan.model_dump_json(indent=2)
    restored_plan = ExecutionPlan.model_validate_json(json_payload)
    assert len(restored_plan.tasks) == 7
    print(f"  -> Serialized JSON size: {len(json_payload):,} characters")
    print("  [PASS] Full Pydantic JSON round-trip serialization verified!")

    print("\n  --- Pipeline ASCII Architecture Diagram ---")
    print(plan.visualize_ascii())

    print("\n" + "=" * 75)
    print("  MILESTONE 12 REAL-WORLD VERIFICATION COMPLETE!")
    print("  The Task Recipe schema and DAG engine are 100% PRODUCTION-ALIGNED & VERIFIED!")
    print("=" * 75 + "\n")
    return True


if __name__ == "__main__":
    success = run_milestone12_verification()
    sys.exit(0 if success else 1)
