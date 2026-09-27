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
from script.tools.merge_videos import merge_videos


def print_step(title: str, explanation: str) -> None:
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"  {explanation}")
    print(f"{'=' * 70}")


def generate_color_clip(target_path: Path, text: str, bgr_color: tuple[int, int, int], duration_seconds: int = 2, fps: int = 30) -> None:
    """Generate a real MP4 clip on disk with custom background color and burned-in text."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    width, height = 640, 360
    total_frames = duration_seconds * fps

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(target_path), fourcc, fps, (width, height))

    for i in range(total_frames):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        frame[:] = bgr_color
        cv2.putText(frame, text, (40, 150), cv2.FONT_HERSHEY_DUPLEX, 0.9, (255, 255, 255), 2)
        cv2.putText(frame, f"Time: {i/fps:.2f}s / {duration_seconds}s", (40, 200), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (230, 230, 230), 1)
        writer.write(frame)

    writer.release()


def run_milestone5_verification() -> bool:
    print("\n" + "#" * 70)
    print("  CLIPAGENT MILESTONE 5 REAL-WORLD VERIFICATION: THE GLUE")
    print("  (Video Concatenation & Multi-Clip Assembly on Real Media)")
    print("#" * 70)

    workspace = _shared.WORKSPACE

    # -------------------------------------------------------------------------
    # STEP 1: Security & Input Validation Defense
    # -------------------------------------------------------------------------
    print_step(
        "STEP 1: Security & Boundary Rejections",
        "Attempts invalid merge requests (single clip and external system paths).",
    )
    # Test single clip rejection
    single_res = merge_videos(["only_one.mp4"])
    print(f"  -> Single clip request: {single_res}")
    assert "At least 2 videos are required" in single_res

    # Test outside path rejection
    unauthorized = "C:/Windows/System32/drivers/etc/hosts"
    blocked_res = merge_videos(["dummy1.mp4", unauthorized])
    print(f"  -> External path request: {blocked_res}")
    assert "Input video is outside WORKSPACE or does not exist" in blocked_res
    print("  [PASS] Invalid merge inputs cleanly rejected!")

    # -------------------------------------------------------------------------
    # STEP 2: Real Multi-Clip Generation on Disk
    # -------------------------------------------------------------------------
    print_step(
        "STEP 2: Physical Media Generation",
        "Generating 2 real, distinct MP4 video files to concatenate.",
    )
    clip_intro = workspace / "scene_intro.mp4"
    clip_outro = workspace / "scene_outro.mp4"

    # Clip 1: 2 seconds, Ocean Blue
    generate_color_clip(clip_intro, text="PART 1: INTRO (2 SECONDS)", bgr_color=(200, 80, 40), duration_seconds=2, fps=30)
    print(f"  -> Created Clip 1: {clip_intro.name} (2.0s, size={clip_intro.stat().st_size:,} bytes)")

    # Clip 2: 3 seconds, Forest Green
    generate_color_clip(clip_outro, text="PART 2: OUTRO (3 SECONDS)", bgr_color=(40, 160, 60), duration_seconds=3, fps=30)
    print(f"  -> Created Clip 2: {clip_outro.name} (3.0s, size={clip_outro.stat().st_size:,} bytes)")

    # -------------------------------------------------------------------------
    # STEP 3: Real Video Concatenation via The Glue (merge_videos)
    # -------------------------------------------------------------------------
    print_step(
        "STEP 3: Multi-Clip Concatenation Execution",
        "Gluing scene_intro.mp4 (2s) and scene_outro.mp4 (3s) into verified_compilation.mp4.",
    )
    merge_raw = merge_videos(
        [clip_intro.name, clip_outro.name],
        output_name="verified_compilation",
    )
    print(f"  -> merge_videos() JSON Response:\n     {merge_raw}")
    merge_data = json.loads(merge_raw)

    assert merge_data["status"] == "success"
    assert merge_data["clip_count"] == 2
    assert merge_data["duration"] == 5.0

    output_path = Path(merge_data["path"])
    assert output_path.exists(), f"Merged file does not exist on disk: {output_path}"
    print(f"  -> Merged file physically exists: {output_path.stat().st_size:,} bytes")

    # -------------------------------------------------------------------------
    # STEP 4: Independent Physical Measurement via The Ruler (Milestone 3)
    # -------------------------------------------------------------------------
    print_step(
        "STEP 4: Output Verification with Milestone 3 Ruler",
        "Measuring the glued output video to verify container continuity.",
    )
    probe_raw = inspect_video_duration(output_path.name)
    probe_data = json.loads(probe_raw)
    print(f"  -> Measured Total Duration: {probe_data['duration_seconds']}s (Expected: 5.0s)")
    print(f"  -> Measured Resolution:     {probe_data['resolution']}")
    print(f"  -> Measured Framerate:      {probe_data['fps']} FPS")

    assert probe_data["duration_seconds"] == 5.0
    assert probe_data["resolution"] == "640x360"
    print("  [PASS] Glued video verified with 100% precision on real disk!")

    print("\n" + "=" * 70)
    print("  MILESTONE 5 REAL-WORLD VERIFICATION COMPLETE!")
    print(f"  Merged Compilation: {output_path}")
    print("  (You can open and play this .mp4 file in Windows Media Player to see both scenes glued together!)")
    print("=" * 70 + "\n")
    return True


if __name__ == "__main__":
    success = run_milestone5_verification()
    sys.exit(0 if success else 1)
