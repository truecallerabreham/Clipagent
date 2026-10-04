"""Interactive CLI for Milestone 12: The Task Recipe (ExecutionPlan & TaskSpec).

Enables interactive exploration of task specifications (TaskSpec), ExecutionPlan blueprints,
resource requirements, dependencies, and JSON serialization.
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
            TaskSpec(id="dl_01", phase="prep", kind="download", tool_name="download_material_video", description="Download Source Footage", resources={"download_pool": 1}, priority=10),
            TaskSpec(id="probe_02", phase="prep", kind="inspect", tool_name="inspect_media_consistency", description="Probe Media Consistency", depends_on=["dl_01"], resources={"video_analysis_pool": 1}, priority=50),
            TaskSpec(id="std_03", phase="prep", kind="standardize", tool_name="standardize_media_clips", description="Standardize Video to 1080p", depends_on=["probe_02"], resources={"ffmpeg_pool": 1}, priority=50),
            TaskSpec(id="audio_04", phase="research", kind="extract_audio", tool_name="extract_audio", description="Extract Audio Track", depends_on=["std_03"], resources={"ffmpeg_pool": 1}, priority=20),
            TaskSpec(id="whisper_05", phase="research", kind="transcribe", tool_name="transcribe_speech", description="Whisper Speech-to-Text", depends_on=["audio_04"], resources={"llm_pool": 1}, priority=30),
            TaskSpec(id="cut_06", phase="execution", kind="batch_cut", tool_name="batch_cut_video", description="Cut Highlights", depends_on=["std_03"], resources={"ffmpeg_pool": 1}, priority=40),
            TaskSpec(id="merge_07", phase="execution", kind="merge", tool_name="merge_videos", description="Merge Final Cut with Subtitles", depends_on=["whisper_05", "cut_06"], resources={"ffmpeg_pool": 1, "export_pool": 1}, priority=100),
        ],
    )


def main() -> None:
    print("\n" + "=" * 75)
    print("  CLIPAGENT MILESTONE 12: THE TASK RECIPE (CLI)")
    print("  (Reference-Aligned ExecutionPlan & TaskSpec Models)")
    print("=" * 75)

    plan = build_sample_production_plan()

    while True:
        print("\nChoose an action:")
        print("  [1] List all tasks in the execution plan")
        print("  [2] Inspect a task's full configuration (arguments, resources, retries)")
        print("  [3] Export plan to JSON blueprint (temp/pipeline_blueprint.json)")
        print("  [4] Load and restore plan from JSON")
        print("  [0] Exit")

        choice = input("  > ").strip().lower()

        if choice in {"0", "q", "quit", "exit"}:
            print("Exiting.")
            break

        if choice == "1":
            print(f"\n--- ExecutionPlan: '{plan.plan_id}' ({len(plan.tasks)} tasks) ---")
            for idx, t in enumerate(plan.tasks, start=1):
                deps = f"[needs: {', '.join(t.depends_on)}]" if t.depends_on else "[ROOT]"
                res = f"Res:{t.resources}" if t.resources else "Res:none"
                print(f"  ({idx}) {t.id:<14} | Tool: {t.tool_name:<26} | P:{t.priority:<3} | {res:<20} {deps}")

        elif choice == "2":
            print("\nEnter task ID to inspect (e.g. 'merge_07'):")
            t_id = input("  ID > ").strip()
            found = next((t for t in plan.tasks if t.id == t_id), None)
            if not found:
                print(f"Task '{t_id}' not found.")
            else:
                print(f"\n--- Task Spec: {found.id} ---")
                print(json.dumps(found.model_dump(), indent=2))

        elif choice == "3":
            out_file = Path("temp") / "pipeline_blueprint.json"
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
            print(f"\n[SUCCESS] Pipeline blueprint saved to: {out_file.resolve()}")
            print(f"File size: {out_file.stat().st_size:,} bytes")

        elif choice == "4":
            raw_json = plan.model_dump_json(indent=2)
            restored = ExecutionPlan.model_validate_json(raw_json)
            print(f"\n[SUCCESS] Successfully parsed and restored ExecutionPlan '{restored.plan_id}' with {len(restored.tasks)} tasks!")


if __name__ == "__main__":
    main()
