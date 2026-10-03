"""Interactive CLI for Milestone 12: The Task Recipe & DAG Engine.

Enables interactive exploration of task specifications (TaskSpec), DAG validation,
cycle detection, topological sorting, and ExecutionPlan JSON blueprints.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from script.orchestration.models import ExecutionPlan, TaskSpec


def build_sample_production_plan() -> ExecutionPlan:
    """Construct a realistic 7-stage autonomous video production ExecutionPlan."""
    return ExecutionPlan(
        plan_id="plan_clipagent_auto_producer",
        phase="editing_execution",
        goal="Autonomous Explainer Video Assembly",
        tasks=[
            TaskSpec(
                id="dl_01",
                phase="material_preparation",
                kind="download",
                tool_name="download_material_video",
                description="Download Source Footage",
                resources={"download_pool": 1},
                priority=10,
            ),
            TaskSpec(
                id="probe_02",
                phase="material_preparation",
                kind="inspect",
                tool_name="inspect_media_consistency",
                description="Probe Media Consistency",
                depends_on=["dl_01"],
                resources={"video_analysis_pool": 1},
                priority=50,
            ),
            TaskSpec(
                id="std_03",
                phase="material_preparation",
                kind="standardize",
                tool_name="standardize_media_clips",
                description="Standardize Video to 1080p",
                depends_on=["probe_02"],
                resources={"ffmpeg_pool": 1},
                priority=50,
            ),
            TaskSpec(
                id="audio_04",
                phase="editing_research",
                kind="extract_audio",
                tool_name="extract_audio",
                description="Extract Audio Track",
                depends_on=["std_03"],
                resources={"ffmpeg_pool": 1},
                priority=20,
            ),
            TaskSpec(
                id="whisper_05",
                phase="editing_research",
                kind="transcribe",
                tool_name="transcribe_speech",
                description="Whisper Speech-to-Text",
                depends_on=["audio_04"],
                resources={"llm_pool": 1},
                priority=30,
            ),
            TaskSpec(
                id="cut_06",
                phase="editing_execution",
                kind="batch_cut",
                tool_name="batch_cut_video",
                description="Cut Highlights",
                depends_on=["std_03"],
                resources={"ffmpeg_pool": 1},
                priority=40,
            ),
            TaskSpec(
                id="merge_07",
                phase="editing_execution",
                kind="merge",
                tool_name="merge_videos",
                description="Merge Final Cut with Subtitles",
                depends_on=["whisper_05", "cut_06"],
                resources={"ffmpeg_pool": 1, "export_pool": 1},
                priority=100,
            ),
        ]
    )


def main() -> None:
    print("\n" + "=" * 75)
    print("  CLIPAGENT MILESTONE 12: THE TASK RECIPE & DAG ENGINE (CLI)")
    print("  (Reference-Aligned ExecutionPlan, Cycle Defense & TaskSpec Dispatch)")
    print("=" * 75)

    plan = build_sample_production_plan()

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
            print("\n" + plan.visualize_ascii())

        elif choice == "2":
            print("\nTopological Sort Order (Honoring Dependencies & Priority):")
            sorted_tasks = plan.topological_sort()
            for idx, t in enumerate(sorted_tasks, start=1):
                deps = f"[needs: {', '.join(t.depends_on)}]" if t.depends_on else "[ROOT]"
                print(f"  ({idx}) {t.id:<15} | Priority: {t.priority:<3} | Tool: {t.tool_name:<28} {deps}")

        elif choice == "3":
            print("\n--- Step-by-Step Simulated Worker Dispatch ---")
            completed_tasks: set[str] = set()
            step = 1

            while len(completed_tasks) < len(plan.tasks):
                ready = plan.get_ready_tasks(completed_tasks)
                print(f"\n[Step {step}] Completed: {sorted(list(completed_tasks)) or 'None'}")
                print(f"         Available Ready Tasks ({len(ready)}):")
                for r in ready:
                    res_str = f"Res:{r.resources}" if r.resources else "Res:none"
                    print(f"           -> [{r.id}] '{r.description or r.kind}' (P:{r.priority}, {res_str})")

                # Dispatch highest priority task
                dispatched = ready[0]
                print(f"         ==> Dispatching [{dispatched.id}] '{dispatched.description}' to worker...")
                completed_tasks.add(dispatched.id)
                print(f"         ==> Task [{dispatched.id}] finished with status COMPLETED!")
                step += 1

            print("\n[SUCCESS] All 7 pipeline tasks executed to 100% completion with zero race conditions!")

        elif choice == "4":
            print("\n--- Testing DAG Cycle Defense Engine ---")
            bad_plan = ExecutionPlan(
                plan_id="plan_bad_cycle",
                phase="test",
                tasks=[
                    TaskSpec(id="A", phase="p", kind="k", depends_on=["C"]),
                    TaskSpec(id="B", phase="p", kind="k", depends_on=["A"]),
                    TaskSpec(id="C", phase="p", kind="k", depends_on=["B"]),
                ]
            )

            print("Constructed intentional circular loop: A -> B -> C -> A")
            print("Running bad_plan.validate_dag()...")
            try:
                bad_plan.validate_dag()
                print("ERROR: Cycle was not caught!")
            except ValueError as err:
                print(f"[CAUGHT EXPECTED REJECTION]: {err}")
                print("Cycle defense successfully verified!")

        elif choice == "5":
            out_file = Path("temp") / "pipeline_blueprint.json"
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
            print(f"\n[SUCCESS] Pipeline blueprint saved to: {out_file.resolve()}")
            print(f"File size: {out_file.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
