from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import cv2
import numpy as np

from script.tools import _shared
from script.tools.inspect_video_duration import inspect_video_duration
from script.tools.plan_transition_for_clips import plan_transition_for_clips


def print_step(title: str, explanation: str) -> None:
    print(f"\n{'=' * 75}")
    print(f"  {title}")
    print(f"  {explanation}")
    print(f"{'=' * 75}")


def generate_color_scene(
    target_path: Path,
    title: str,
    bgr_color: tuple[int, int, int],
    duration_seconds: int = 3,
    fps: int = 30,
) -> None:
    """Generate a real MP4 scene on disk with a distinct color and burned-in title."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    width, height = 640, 360
    total_frames = duration_seconds * fps

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(target_path), fourcc, fps, (width, height))

    for i in range(total_frames):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        frame[:] = bgr_color
        cv2.putText(
            frame, title, (50, 150), cv2.FONT_HERSHEY_DUPLEX, 0.9, (255, 255, 255), 2
        )
        cv2.putText(
            frame,
            f"Time: {i/fps:.2f}s / {duration_seconds}s  (Frame {i+1}/{total_frames})",
            (50, 210),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (240, 240, 240),
            1,
        )
        writer.write(frame)

    writer.release()


def run_milestone8_verification() -> bool:
    print("\n" + "#" * 75)
    print("  CLIPAGENT MILESTONE 8 REAL-WORLD VERIFICATION: THE TRANSITION PLANNER")
    print("  (Multi-Clip Transition Blueprinting & Timeline Synchronization)")
    print("#" * 75)

    workspace = _shared.WORKSPACE

    # -------------------------------------------------------------------------
    # STEP 1: Security Perimeter Defense
    # -------------------------------------------------------------------------
    print_step(
        "STEP 1: Security & Boundary Rejections",
        "Attempts to plan transitions on external system files outside WORKSPACE.",
    )
    unauthorized = "C:/Windows/System32/drivers/etc/hosts"
    blocked_res = plan_transition_for_clips([unauthorized, "dummy.mp4"])
    print(f"  -> External path rejection: {blocked_res}")
    assert "Clip is outside WORKSPACE or does not exist" in blocked_res
    print("  [PASS] External file access cleanly blocked!")

    # -------------------------------------------------------------------------
    # STEP 2: Physical Media Generation on Disk (3 Scenes)
    # -------------------------------------------------------------------------
    print_step(
        "STEP 2: Physical Media Generation",
        "Generating 3 contrasting scene videos (Gold, Emerald, and Purple, 3.0s each).",
    )
    scene_gold = workspace / "scene_alpha_gold.mp4"
    scene_emerald = workspace / "scene_beta_emerald.mp4"
    scene_purple = workspace / "scene_gamma_purple.mp4"

    generate_color_scene(
        scene_gold,
        title="SCENE 1: SUNSET GOLD",
        bgr_color=(30, 180, 240),
        duration_seconds=3,
        fps=30,
    )
    print(f"  -> Created Scene 1: {scene_gold.name} (3.0s, size={scene_gold.stat().st_size:,} bytes)")

    generate_color_scene(
        scene_emerald,
        title="SCENE 2: EMERALD FOREST",
        bgr_color=(60, 200, 60),
        duration_seconds=3,
        fps=30,
    )
    print(f"  -> Created Scene 2: {scene_emerald.name} (3.0s, size={scene_emerald.stat().st_size:,} bytes)")

    generate_color_scene(
        scene_purple,
        title="SCENE 3: ROYAL PURPLE",
        bgr_color=(200, 40, 150),
        duration_seconds=3,
        fps=30,
    )
    print(f"  -> Created Scene 3: {scene_purple.name} (3.0s, size={scene_purple.stat().st_size:,} bytes)")

    # -------------------------------------------------------------------------
    # STEP 3: Strict Mode Validation & Safe Auto-Adjustment
    # -------------------------------------------------------------------------
    print_step(
        "STEP 3: Transition Duration Constraints Guard",
        "Verifying over-length transition rejection and automatic safe duration scaling.",
    )
    # Request 2.0s transition on 3.0s clips with auto_adjust=False -> should reject (exceeds 45% bound)
    strict_res = plan_transition_for_clips(
        [scene_gold.name, scene_emerald.name],
        default_duration=2.0,
        auto_adjust=False,
    )
    print(f"  -> Strict mode rejection: {strict_res}")
    assert "Transition duration (2.0s) is too long" in strict_res
    print("  [PASS] Strict mode duration bounds validation confirmed!")

    # Now run with auto_adjust=True -> should clamp safely to 45% (1.35s)
    auto_res_raw = plan_transition_for_clips(
        [scene_gold.name, scene_emerald.name],
        default_duration=2.0,
        auto_adjust=True,
    )
    auto_data = json.loads(auto_res_raw)
    assert auto_data["transitions"][0]["adjusted"] is True
    print(f"  -> Auto-adjusted transition duration: {auto_data['transitions'][0]['duration']}s")
    print("  [PASS] Auto-adjust safety scaling confirmed!")

    # -------------------------------------------------------------------------
    # STEP 4: Cinematic Blueprint Calculation (Planning Only)
    # -------------------------------------------------------------------------
    print_step(
        "STEP 4: Cinematic Multi-Clip Blueprint Calculation",
        "Generating structured AI timeline plan for 3 clips with 1.0s transitions.",
    )
    plan_raw = plan_transition_for_clips(
        [scene_gold.name, scene_emerald.name, scene_purple.name],
        style="cinematic",
        default_duration=1.0,
    )
    plan_data = json.loads(plan_raw)

    print("  -> Plan Summary:")
    print(f"     Clips: {plan_data['clip_count']}")
    print(f"     Transitions: {plan_data['transition_count']}")
    print(f"     Raw Duration: {plan_data['total_raw_duration']}s")
    print(f"     Planned Render Duration: {plan_data['total_planned_duration']}s")
    print(f"     Overlap Saved: {plan_data['overlap_duration_saved']}s")

    assert plan_data["status"] == "success"
    assert plan_data["clip_count"] == 3
    assert plan_data["transition_count"] == 2
    assert plan_data["total_raw_duration"] == 9.0
    # 9.0s raw - (1.0s + 1.0s) = 7.0s
    assert plan_data["total_planned_duration"] == 7.0

    # Print timeline layout
    print("\n  -> Timeline Layout:")
    for clip in plan_data["clips"]:
        print(f"     [Clip {clip['index']}] {clip['name']}: {clip['timeline_start']}s -> {clip['timeline_end']}s (dur: {clip['duration']}s)")
    for trans in plan_data["transitions"]:
        print(f"     <Trans {trans['index']}> {trans['from_clip']} -> {trans['to_clip']}: type={trans['transition_type']}, at {trans['timeline_offset']}s, dur={trans['duration']}s")

    assert plan_data["transitions"][0]["timeline_offset"] == 2.0
    assert plan_data["transitions"][1]["timeline_offset"] == 4.0
    print("  [PASS] Timeline coordinates and offset math verified with 100% precision!")

    # -------------------------------------------------------------------------
    # STEP 5: Physical Multi-Clip Sequence Rendering
    # -------------------------------------------------------------------------
    print_step(
        "STEP 5: Real Multi-Clip Video Sequence Rendering",
        "Executing the planned sequence with native FFmpeg to produce verified MP4.",
    )
    render_raw = plan_transition_for_clips(
        [scene_gold.name, scene_emerald.name, scene_purple.name],
        style="action",
        default_duration=0.8,
        render_video=True,
        output_name="verified_planned_action_sequence",
    )
    render_data = json.loads(render_raw)

    assert render_data["status"] == "success"
    output_path = Path(render_data["rendered_video_path"])
    assert output_path.exists(), f"Rendered output missing: {output_path}"
    print(f"  -> Rendered sequence file physically exists: {output_path.name}")
    print(f"     File size: {output_path.stat().st_size:,} bytes")
    print(f"     Reported Rendered Duration: {render_data['rendered_duration']}s")

    # -------------------------------------------------------------------------
    # STEP 6: Independent Physical Measurement with Milestone 3 Ruler
    # -------------------------------------------------------------------------
    print_step(
        "STEP 6: Independent Output Measurement with Milestone 3 Ruler",
        "Measuring the rendered 3-scene sequence with OpenCV ruler.",
    )
    probe_raw = inspect_video_duration(output_path.name)
    probe_data = json.loads(probe_raw)

    print(f"  -> Measured Duration:   {probe_data['duration_seconds']}s (Target: {render_data['total_planned_duration']}s)")
    print(f"  -> Measured Resolution: {probe_data['resolution']}")
    print(f"  -> Measured FPS:        {probe_data['fps']} FPS")

    assert abs(probe_data["duration_seconds"] - render_data["total_planned_duration"]) <= 0.1
    assert probe_data["resolution"] == "640x360"
    print("  [PASS] Physical multi-clip sequence verified on disk with exact timeline alignment!")

    print("\n" + "=" * 75)
    print("  MILESTONE 8 REAL-WORLD VERIFICATION COMPLETE!")
    print(f"  Scene 1:       {scene_gold}")
    print(f"  Scene 2:       {scene_emerald}")
    print(f"  Scene 3:       {scene_purple}")
    print(f"  Final Render:  {output_path}")
    print("  (Play verified_planned_action_sequence.mp4 to see all 3 scenes smoothly transition!)")
    print("=" * 75 + "\n")
    return True


if __name__ == "__main__":
    success = run_milestone8_verification()
    sys.exit(0 if success else 1)
