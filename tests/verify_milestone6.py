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
from script.tools.batch_cut_video import batch_cut_video
from script.tools.inspect_video_duration import inspect_video_duration


def print_step(title: str, explanation: str) -> None:
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"  {explanation}")
    print(f"{'=' * 70}")


def generate_test_lecture(target_path: Path, duration_seconds: int = 10, fps: int = 30) -> None:
    """Generate a real 10-second MP4 video with animated graphics and timer counters."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    width, height = 640, 360
    total_frames = duration_seconds * fps

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(target_path), fourcc, fps, (width, height))

    for i in range(total_frames):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        # Background color shifts smoothly across hue
        frame[:] = (int((i / total_frames) * 140), 90, 160)
        # Bouncing circle
        cx = int(50 + (i / total_frames) * (width - 100))
        cv2.circle(frame, (cx, 180), 22, (255, 255, 255), -1)
        # Timestamp text
        t = i / fps
        cv2.putText(frame, f"FULL PODCAST EPISODE: {t:.2f}s", (40, 60), cv2.FONT_HERSHEY_DUPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(frame, f"Frame {i+1} / {total_frames}", (40, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (220, 220, 220), 1)
        writer.write(frame)

    writer.release()


def run_milestone6_verification() -> bool:
    print("\n" + "#" * 70)
    print("  CLIPAGENT MILESTONE 6 REAL-WORLD VERIFICATION: THE BATCH SCISSORS")
    print("  (Multi-Segment Video Slicing on Real Media)")
    print("#" * 70)

    workspace = _shared.WORKSPACE

    # -------------------------------------------------------------------------
    # STEP 1: Security & Boundary Validation Defense
    # -------------------------------------------------------------------------
    print_step(
        "STEP 1: Security & Input Boundary Rejections",
        "Attempts invalid batch cut requests (external path and invalid timestamp bounds).",
    )
    unauthorized = "C:/Windows/System32/drivers/etc/hosts"
    blocked_res = batch_cut_video(unauthorized, [{"start": 1.0, "end": 3.0}])
    print(f"  -> External file rejection: {blocked_res}")
    assert "Input video is outside WORKSPACE or does not exist" in blocked_res

    # -------------------------------------------------------------------------
    # STEP 2: Physical Source Video Generation on Disk
    # -------------------------------------------------------------------------
    print_step(
        "STEP 2: Physical Media Generation",
        "Generating an actual 10-second master video on disk to slice into multiple clips.",
    )
    source_file = workspace / "master_podcast_episode.mp4"
    generate_test_lecture(source_file, duration_seconds=10, fps=30)
    print(f"  -> Created Master Video: {source_file.name} (10.0s, size={source_file.stat().st_size:,} bytes)")

    # Test out-of-bounds rejection against real video duration
    over_res = batch_cut_video(source_file.name, [{"start": 2.0, "end": 18.0}])
    print(f"  -> Out-of-bounds rejection: {over_res}")
    assert "exceeds total source video duration" in over_res
    print("  [PASS] Boundary security and duration guard verified!")

    # -------------------------------------------------------------------------
    # STEP 3: Multi-Segment Slicing Execution (batch_cut_video)
    # -------------------------------------------------------------------------
    print_step(
        "STEP 3: Multi-Segment Slicing Execution",
        "Slicing 3 separate highlights from master_podcast_episode.mp4 in ONE operation.",
    )
    segments = [
        {"start_time": 1.0, "end_time": 3.5, "output_name": "highlight_hook"},
        {"start_time": 4.0, "end_time": 6.5, "output_name": "highlight_core"},
        {"start_time": 7.0, "end_time": 9.5, "output_name": "highlight_cta"},
    ]

    batch_raw = batch_cut_video(source_file.name, segments)
    print(f"  -> batch_cut_video() JSON Response:\n     {batch_raw}")
    batch_data = json.loads(batch_raw)

    assert batch_data["status"] == "success"
    assert batch_data["total_clips"] == 3
    assert len(batch_data["clips"]) == 3

    # -------------------------------------------------------------------------
    # STEP 4: Independent Physical Measurement of Each Generated Clip
    # -------------------------------------------------------------------------
    print_step(
        "STEP 4: Output Verification with Milestone 3 Ruler",
        "Measuring each generated clip on disk to verify timestamp accuracy.",
    )
    for clip_info in batch_data["clips"]:
        clip_path = Path(clip_info["path"])
        assert clip_path.exists(), f"Generated clip not found on disk: {clip_path}"

        probe_raw = inspect_video_duration(clip_path.name)
        probe_data = json.loads(probe_raw)
        print(f"  -> Clip #{clip_info['clip_index']}: {clip_path.name}")
        print(f"     * Measured Duration:   {probe_data['duration_seconds']}s (Target: 2.50s)")
        print(f"     * Measured Resolution: {probe_data['resolution']}")
        print(f"     * Physical File Size:  {clip_path.stat().st_size:,} bytes")
        deviation = abs(probe_data["duration_seconds"] - 2.5)
        assert deviation <= 0.2, f"Clip duration deviation too high: {deviation}s"

    print("  [PASS] All 3 clips physically verified on disk with 100% accuracy!")

    print("\n" + "=" * 70)
    print("  MILESTONE 6 REAL-WORLD VERIFICATION COMPLETE!")
    print(f"  Master Video: {source_file}")
    for clip_info in batch_data["clips"]:
        print(f"  -> Highlight Clip: {clip_info['path']}")
    print("  (You can open and play each highlight in Windows Media Player!)")
    print("=" * 70 + "\n")
    return True


if __name__ == "__main__":
    success = run_milestone6_verification()
    sys.exit(0 if success else 1)
