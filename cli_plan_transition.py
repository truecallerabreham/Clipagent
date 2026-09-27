"""Interactive CLI for Milestone 8: The Transition Planner.

Enables interactive testing of multi-clip transition planning, timeline calculation,
and optional native FFmpeg rendering across video clips in the workspace.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from script.tools import _shared
from script.tools.plan_transition_for_clips import STYLE_PRESETS, plan_transition_for_clips


def list_workspace_videos() -> list[Path]:
    """Scan WORKSPACE directory for available MP4 video files."""
    workspace = _shared.WORKSPACE
    if not workspace.exists():
        return []
    valid_exts = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
    return sorted(
        [f for f in workspace.iterdir() if f.is_file() and f.suffix.lower() in valid_exts and not f.name.startswith("_temp_")],
        key=lambda x: x.name.lower(),
    )


def main() -> None:
    print("\n" + "=" * 75)
    print("  CLIPAGENT MILESTONE 8: THE TRANSITION PLANNER (CLI)")
    print("  (Multi-Clip Transition Blueprinting & Timeline Synchronization)")
    print("=" * 75)

    workspace_videos = list_workspace_videos()

    print(f"\nWorkspace Folder: {_shared.WORKSPACE}")
    if workspace_videos:
        print("Available videos in workspace:")
        for idx, vid in enumerate(workspace_videos, start=1):
            size_mb = vid.stat().st_size / (1024 * 1024)
            print(f"  [{idx}] {vid.name:<35} ({size_mb:.2f} MB)")
    else:
        print("  (No video files currently in workspace. Run tests/verify_milestone8.py first to create sample scenes!)")

    print("\nSelect clips to sequence:")
    print("  Enter comma-separated numbers (e.g., '1, 2, 3') or filenames.")
    user_input = input("  > ").strip()
    if not user_input:
        print("No clips selected. Exiting.")
        return

    # Parse user selection
    selected_clips: list[str] = []
    for token in user_input.split(","):
        token = token.strip()
        if not token:
            continue
        if token.isdigit() and workspace_videos:
            idx = int(token) - 1
            if 0 <= idx < len(workspace_videos):
                selected_clips.append(workspace_videos[idx].name)
            else:
                print(f"Invalid index: {token}")
                return
        else:
            selected_clips.append(token)

    if not selected_clips:
        print("No valid clips specified. Exiting.")
        return

    print(f"\nSelected {len(selected_clips)} clips in sequence: {selected_clips}")

    # Select style
    print("\nChoose Transition Style Preset:")
    styles = list(STYLE_PRESETS.keys()) + ["custom"]
    for i, s in enumerate(styles, 1):
        desc = STYLE_PRESETS.get(s, {}).get("description", "Specify your own transition type")
        print(f"  [{i}] {s:<10} - {desc}")

    style_choice = input(f"Select style [1-{len(styles)}] (default 1 - cinematic): ").strip()
    selected_style = "cinematic"
    if style_choice.isdigit():
        s_idx = int(style_choice) - 1
        if 0 <= s_idx < len(styles):
            selected_style = styles[s_idx]

    default_trans = "fade"
    if selected_style == "custom":
        default_trans = input("Enter default transition type (e.g. fade, wipeleft, dissolve) [fade]: ").strip() or "fade"

    # Select duration
    dur_input = input("\nEnter transition overlap duration in seconds [default: 1.0]: ").strip()
    duration = 1.0
    if dur_input:
        try:
            duration = float(dur_input)
        except ValueError:
            print("Invalid duration, using default 1.0s.")

    # Render option
    print("\nOperation Mode:")
    print("  [1] Blueprint only (Calculate and display timeline without rendering)")
    print("  [2] Render video (Physically render multi-clip transition video via native FFmpeg)")
    mode_choice = input("Select mode [1/2] (default 1): ").strip() or "1"
    render_video = (mode_choice == "2")

    output_name = "planned_sequence"
    if render_video:
        output_name = input("Enter output video name (without .mp4) [planned_sequence]: ").strip() or "planned_sequence"

    print("\nComputing transition plan...")
    plan_json = plan_transition_for_clips(
        selected_clips,
        style=selected_style,
        default_transition=default_trans,
        default_duration=duration,
        auto_adjust=True,
        render_video=render_video,
        output_name=output_name,
    )

    try:
        data = json.loads(plan_json)
        print("\n" + "=" * 75)
        print("  STRUCTURED TRANSITION BLUEPRINT")
        print("=" * 75)
        print(f"  Style Preset:             {data.get('style')}")
        print(f"  Total Clips:              {data.get('clip_count')}")
        print(f"  Planned Transitions:      {data.get('transition_count')}")
        print(f"  Raw Duration (Sum):       {data.get('total_raw_duration')}s")
        print(f"  Final Planned Duration:   {data.get('total_planned_duration')}s")
        print(f"  Overlap Duration Saved:   {data.get('overlap_duration_saved')}s")

        print("\n  --- Timeline Alignment ---")
        for c in data.get("clips", []):
            print(f"    [Clip {c['index']}] {c['name']:<25} | {c['timeline_start']:>5.2f}s -> {c['timeline_end']:>5.2f}s | dur: {c['duration']:>4.2f}s | {c['resolution']}")

        print("\n  --- Planned Transitions ---")
        for t in data.get("transitions", []):
            adj_str = f" [ADJUSTED: {t['adjustment_reason']}]" if t.get("adjusted") else ""
            print(f"    <Trans {t['index']}> {t['from_clip']} -> {t['to_clip']}: type={t['transition_type']}, at {t['timeline_offset']:.2f}s, dur={t['duration']:.2f}s{adj_str}")

        print("\n  --- Diagnostics & Checks ---")
        for d in data.get("diagnostics", []):
            print(f"    * {d}")

        if render_video and data.get("rendered_video_path"):
            print("\n  " + "-" * 71)
            print(f"  [SUCCESS] Rendered sequence video physically created:")
            print(f"    File:     {data.get('rendered_video_name')}")
            print(f"    Path:     {data.get('rendered_video_path')}")
            print(f"    Duration: {data.get('rendered_duration')}s")
            print("  " + "-" * 71)

        print("\n" + "=" * 75)

    except json.JSONDecodeError:
        print(f"\nResult / Error:\n{plan_json}")


if __name__ == "__main__":
    main()
