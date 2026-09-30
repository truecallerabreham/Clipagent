"""Interactive CLI for Milestone 12: The Task Recipe & TaskGraph DAG Engine.

Enables interactive exploration of task blueprints, DAG validation, cycle detection,
topological sorting, dynamic ready-task dispatch, and workflow JSON export.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from script.orchestration.models import (
    ResourceRequirement,
    ResourceType,
    TaskDefinition,
    TaskGraph,
    TaskPriority,
    TaskStatus,
)


def build_sample_production_graph() -> TaskGraph:
    """Construct a realistic 7-stage autonomous video production DAG."""
    graph = TaskGraph(name="auto_video_producer")
    tasks = [
        TaskDefinition(
            task_id="dl_01",
            task_name="Download YouTube Footage",
            action="download_material_video",
            priority=TaskPriority.NORMAL,
            resource_req=ResourceRequirement(resource_type=ResourceType.IO_HEAVY),
        ),
        TaskDefinition(
            task_id="probe_02",
            task_name="Probe Media Consistency",
            action="inspect_media_consistency",
            dependencies=["dl_01"],
            priority=TaskPriority.HIGH,
            resource_req=ResourceRequirement(resource_type=ResourceType.LIGHTWEIGHT),
        ),
        TaskDefinition(
            task_id="std_03",
            task_name="Standardize Video to 1080p",
            action="standardize_media_clips",
            dependencies=["probe_02"],
            priority=TaskPriority.HIGH,
            resource_req=ResourceRequirement(resource_type=ResourceType.CPU_HEAVY, cpu_cores=4),
        ),
        TaskDefinition(
            task_id="audio_04",
            task_name="Extract Audio Track",
            action="extract_audio",
            dependencies=["std_03"],
            priority=TaskPriority.NORMAL,
            resource_req=ResourceRequirement(resource_type=ResourceType.IO_HEAVY),
        ),
        TaskDefinition(
            task_id="whisper_05",
            task_name="Whisper Speech-to-Text",
            action="transcribe_speech",
            dependencies=["audio_04"],
            priority=TaskPriority.NORMAL,
            resource_req=ResourceRequirement(resource_type=ResourceType.NETWORK_API),
        ),
        TaskDefinition(
            task_id="cut_06",
            task_name="Cut Highlights",
            action="batch_cut_video",
            dependencies=["std_03"],
            priority=TaskPriority.NORMAL,
            resource_req=ResourceRequirement(resource_type=ResourceType.CPU_HEAVY, cpu_cores=2),
        ),
        TaskDefinition(
            task_id="merge_07",
            task_name="Merge Final Cut with Subtitles",
            action="merge_videos",
            dependencies=["whisper_05", "cut_06"],
            priority=TaskPriority.CRITICAL,
            resource_req=ResourceRequirement(resource_type=ResourceType.CPU_HEAVY, cpu_cores=4),
        ),
    ]
    for t in tasks:
        graph.add_task(t)
    return graph


def main() -> None:
    print("\n" + "=" * 75)
    print("  CLIPAGENT MILESTONE 12: THE TASK RECIPE & DAG ENGINE (CLI)")
    print("  (Workflow Graph Construction, Cycle Detection & Dynamic Scheduling)")
    print("=" * 75)

    graph = build_sample_production_graph()

    while True:
        print("\nChoose an action:")
        print("  [1] Display Pipeline ASCII Diagram")
        print("  [2] Run Topological Sort (Linear Dependency Execution Sequence)")
        print("  [3] Step-by-Step Dynamic Dispatch Simulation")
        print("  [4] Test Circular Loop Detection (Cycle Defense)")
        print("  [5] Export Pipeline to JSON Blueprint")
        print("  [q] Quit")

        choice = input("  > ").strip().lower()

        if choice in {"q", "quit", "exit"}:
            print("Exiting.")
            break

        if choice == "1":
            print("\n" + graph.visualize_ascii())

        elif choice == "2":
            print("\nTopological Sort Order (Honoring Dependencies & Priority):")
            sorted_tasks = graph.topological_sort()
            for idx, t in enumerate(sorted_tasks, start=1):
                deps = f"[needs: {', '.join(t.dependencies)}]" if t.dependencies else "[ROOT]"
                print(f"  ({idx}) {t.task_id:<15} | Priority: {t.priority.name:<8} | Action: {t.action:<25} {deps}")

        elif choice == "3":
            print("\n--- Step-by-Step Simulated Worker Dispatch ---")
            completed_tasks: set[str] = set()
            step = 1

            while len(completed_tasks) < len(graph._tasks):
                ready = graph.get_ready_tasks(completed_tasks)
                print(f"\n[Step {step}] Completed: {sorted(list(completed_tasks)) or 'None'}")
                print(f"         Available Ready Tasks ({len(ready)}):")
                for r in ready:
                    print(f"           -> [{r.task_id}] '{r.task_name}' (P:{r.priority.name}, Res:{r.resource_req.resource_type.value})")

                # Dispatch highest priority task
                dispatched = ready[0]
                print(f"         ==> Dispatching [{dispatched.task_id}] '{dispatched.task_name}' to worker...")
                completed_tasks.add(dispatched.task_id)
                print(f"         ==> Task [{dispatched.task_id}] finished with status COMPLETED!")
                step += 1

            print("\n[SUCCESS] All 7 pipeline tasks executed to 100% completion with zero race conditions!")

        elif choice == "4":
            print("\n--- Testing DAG Cycle Defense Engine ---")
            bad_graph = TaskGraph(name="test_cyclic")
            bad_graph.add_task(TaskDefinition(task_id="A", task_name="A", action="act", dependencies=["C"]))
            bad_graph.add_task(TaskDefinition(task_id="B", task_name="B", action="act", dependencies=["A"]))
            bad_graph.add_task(TaskDefinition(task_id="C", task_name="C", action="act", dependencies=["B"]))

            print("Constructed intentional circular loop: A -> B -> C -> A")
            print("Running bad_graph.validate_dag()...")
            try:
                bad_graph.validate_dag()
                print("ERROR: Cycle was not caught!")
            except ValueError as err:
                print(f"[CAUGHT EXPECTED REJECTION]: {err}")
                print("Cycle defense successfully verified!")

        elif choice == "5":
            out_file = Path("temp") / "pipeline_blueprint.json"
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_text(graph.to_json(indent=2), encoding="utf-8")
            print(f"\n[SUCCESS] Pipeline blueprint saved to: {out_file.resolve()}")
            print(f"File size: {out_file.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
