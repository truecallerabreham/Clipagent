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
from script.tools.add_transition import add_transition
from script.tools.inspect_video_duration import inspect_video_duration


def print_step(title: str, explanation: str) -> None:
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"  {explanation}")
    print(f"{'=' * 70}")


def generate_color_scene(target_path: Path, title: str, bgr_color: tuple[int, int, int], duration_seconds: int = 3, fps: int = 30) -> None:
    """Generate a real MP4 scene on disk with a distinct color and burned-in title."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    width, height = 640, 360
    total_frames = duration_seconds * fps

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(target_path), fourcc, fps, (width, height))

    for i in range(total_frames):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        frame[:] = bgr_color
        cv2.putText(frame, title, (50, 160), cv2.FONT_HERSHEY_DUPLEX, 1.0, (255, 255, 255), 2)
        cv2.putText(frame, f"Time: {i/fps:.2f}s / {duration_seconds}s", (50, 210), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (240, 240, 240), 1)
        writer.write(frame)

    writer.release()


def run_milestone7_verification() -> bool:
    print("\n" + "#" * 70)
    print("  CLIPAGENT MILESTONE 7 REAL-WORLD VERIFICATION: THE CROSSFADE")
    print("  (Cinematic Video Transitions via FFmpeg xfade)")
    print("#" * 70)

    workspace = _shared.WORKSPACE

    # -------------------------------------------------------------------------
    # STEP 1: Security Perimeter Defense
    # -------------------------------------------------------------------------
    print_step(
        "STEP 1: Security & Boundary Rejections",
        "Attempts invalid transition requests (external system paths).",
    )
    unauthorized = "C:/Windows/System32/drivers/etc/hosts"
    blocked_res = add_transition(unauthorized, "dummy.mp4")
    print(f"  -> External path rejection: {blocked_res}")
    assert "Video 1 is outside WORKSPACE or does not exist" in blocked_res
    print("  [PASS] External file access cleanly blocked!")

    # -------------------------------------------------------------------------
    # STEP 2: Physical Scene Video Generation on Disk
    # -------------------------------------------------------------------------
    print_step(
        "STEP 2: Physical Media Generation",
        "Generating 2 visually contrasting scene videos (Red and Cyan, 3.0s each).",
    )
    scene_red = workspace / "scene_crimson_red.mp4"
    scene_cyan = workspace / "scene_ocean_cyan.mp4"

    generate_color_scene(scene_red, title="SCENE 1: CRIMSON RED", bgr_color=(30, 30, 210), duration_seconds=3, fps=30)
    print(f"  -> Created Scene 1: {scene_red.name} (3.0s, size={scene_red.stat().st_size:,} bytes)")

    generate_color_scene(scene_cyan, title="SCENE 2: OCEAN CYAN", bgr_color=(210, 210, 30), duration_seconds=3, fps=30)
    print(f"  -> Created Scene 2: {scene_cyan.name} (3.0s, size={scene_cyan.stat().st_size:,} bytes)")

    # Test duration bound validation
    invalid_dur_res = add_transition(scene_red.name, scene_cyan.name, transition_duration=4.5)
    print(f"  -> Over-length transition rejection (4.5s on 3.0s clip): {invalid_dur_res}")
    assert "must be shorter than video1 duration" in invalid_dur_res
    print("  [PASS] Transition duration bounds validation verified!")

    # -------------------------------------------------------------------------
    # STEP 3: Real Video Transition Execution via add_transition
    # -------------------------------------------------------------------------
    print_step(
        "STEP 3: Real Transition Execution (1.0s Crossfade Dissolve)",
        "Blending Scene 1 (Red) into Scene 2 (Cyan) with a 1.0-second dissolve.",
    )
    trans_raw = add_transition(
        scene_red.name,
        scene_cyan.name,
        transition_type="fade",
        transition_duration=1.0,
        output_name="verified_cinematic_fade",
    )
    print(f"  -> add_transition() JSON Response:\n     {trans_raw}")
    trans_data = json.loads(trans_raw)

    assert trans_data["status"] == "success"
    assert trans_data["transition"] == "fade"
    # Expected duration: 3.0s + 3.0s - 1.0s overlap = 5.0s
    assert trans_data["duration"] == 5.0

    output_path = Path(trans_data["path"])
    assert output_path.exists(), f"Transition file not found on disk: {output_path}"
    print(f"  -> Transition clip physically exists: {output_path.stat().st_size:,} bytes")

    # -------------------------------------------------------------------------
    # STEP 4: Independent Physical Measurement with Milestone 3 Ruler
    # -------------------------------------------------------------------------
    print_step(
        "STEP 4: Output Measurement with Milestone 3 Ruler",
        "Measuring the transition video to verify exact timing and resolution.",
    )
    probe_raw = inspect_video_duration(output_path.name)
    probe_data = json.loads(probe_raw)
    print(f"  -> Measured Duration:   {probe_data['duration_seconds']}s (Target: 5.0s)")
    print(f"  -> Measured Resolution: {probe_data['resolution']}")
    print(f"  -> Measured FPS:        {probe_data['fps']} FPS")

    assert probe_data["duration_seconds"] == 5.0
    assert probe_data["resolution"] == "640x360"
    print("  [PASS] Cinematic transition clip verified on physical disk with 100% precision!")

    print("\n" + "=" * 70)
    print("  MILESTONE 7 REAL-WORLD VERIFICATION COMPLETE!")
    print(f"  Scene 1:     {scene_red}")
    print(f"  Scene 2:     {scene_cyan}")
    print(f"  Transition:  {output_path}")
    print("  (You can open and play verified_cinematic_fade.mp4 to see the smooth red-to-cyan crossfade!)")
    print("=" * 70 + "\n")
    return True


if __name__ == "__main__":
    success = run_milestone7_verification()
    sys.exit(0 if success else 1)
