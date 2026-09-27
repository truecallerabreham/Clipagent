from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import cv2
import numpy as np

from script.tools import _shared
from script.tools.cut_video import cut_video
from script.tools.inspect_video_duration import inspect_video_duration


def print_step(title: str, explanation: str) -> None:
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"  {explanation}")
    print(f"{'=' * 70}")


def generate_source_video(target_path: Path, duration_seconds: int = 6, fps: int = 30) -> None:
    """Generate a real 6-second MP4 video on disk with frame numbers and timestamps."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    width, height = 640, 360
    total_frames = duration_seconds * fps

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(target_path), fourcc, fps, (width, height))

    for i in range(total_frames):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        # Background color shifts over time
        frame[:] = (int((i / total_frames) * 180), 120, 60)
        # Draw moving circle indicator
        cx = int(40 + (i / total_frames) * (width - 80))
        cv2.circle(frame, (cx, 180), 20, (0, 255, 255), -1)
        # Burn in time information
        t = i / fps
        cv2.putText(frame, f"ORIGINAL SOURCE VIDEO: {t:.2f}s", (40, 60), cv2.FONT_HERSHEY_DUPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(frame, f"Frame: {i+1}/{total_frames}", (40, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        writer.write(frame)

    writer.release()


def run_milestone4_verification() -> bool:
    print("\n" + "#" * 70)
    print("  CLIPAGENT MILESTONE 4 REAL-WORLD VERIFICATION: THE SCISSORS")
    print("  (Precision Video Trimming on Real Video Media)")
    print("#" * 70)

    workspace = _shared.WORKSPACE

    # -------------------------------------------------------------------------
    # STEP 1: Security Perimeter Guard
    # -------------------------------------------------------------------------
    print_step(
        "STEP 1: Security Perimeter Defense",
        "Attempts to cut a video from an unauthorized location outside the workspace.",
    )
    unauthorized = "C:/Windows/System32/drivers/etc/hosts"
    blocked_result = cut_video(unauthorized, start_time=0.0, end_time=3.0)
    print(f"  -> Path: {unauthorized}")
    print(f"  -> Result: {blocked_result}")
    assert "Cut error: Input video is outside WORKSPACE or does not exist" in blocked_result
    print("  [PASS] External system file access strictly blocked!")

    # -------------------------------------------------------------------------
    # STEP 2: Range & Timestamp Validation
    # -------------------------------------------------------------------------
    print_step(
        "STEP 2: Timestamp Bounds & Error Recovery",
        "Attempts an invalid cut where end_time (2.0s) <= start_time (5.0s).",
    )
    source_video = workspace / "lecture_for_cut.mp4"
    generate_source_video(source_video, duration_seconds=6, fps=30)

    invalid_range_result = cut_video(source_video.name, start_time=5.0, end_time=2.0)
    print(f"  -> Invalid cut request (start=5.0s, end=2.0s):")
    print(f"  -> Result: {invalid_range_result}")
    assert "Cut error:" in invalid_range_result
    print("  [PASS] Invalid timestamp order rejected cleanly without crashing!")

    # -------------------------------------------------------------------------
    # STEP 3: Real Video Cutting Pipeline Execution
    # -------------------------------------------------------------------------
    print_step(
        "STEP 3: Real Video Cutting & Measurement",
        "Cutting a 2.5-second clip (from 1.5s to 4.0s) and measuring the output with Milestone 3.",
    )
    # 1. Inspect source before cut
    source_meta = json.loads(inspect_video_duration(source_video.name))
    print(f"  -> 1. Source Video Duration: {source_meta['duration_seconds']}s ({source_meta['resolution']})")

    # 2. Execute precision cut
    cut_start = 1.5
    cut_end = 4.0
    expected_duration = cut_end - cut_start

    cut_raw = cut_video(
        source_video.name,
        start_time=cut_start,
        end_time=cut_end,
        output_name="verified_clip_1",
    )
    print(f"  -> 2. cut_video() JSON Response:\n     {cut_raw}")
    cut_data = json.loads(cut_raw)
    assert cut_data["status"] == "success"
    assert cut_data["duration"] == expected_duration

    # 3. Inspect generated output clip on real disk using Milestone 3 Ruler
    output_path = Path(cut_data["path"])
    assert output_path.exists(), f"Cut file does not exist on disk: {output_path}"
    print(f"  -> Output file physically exists on disk: {output_path.stat().st_size:,} bytes")

    output_meta = json.loads(inspect_video_duration(output_path.name))
    print(f"  -> 3. Measured Cut Clip Duration: {output_meta['duration_seconds']}s")
    print(f"  -> Measured Cut Resolution:       {output_meta['resolution']}")

    # Duration deviation check
    deviation = abs(output_meta["duration_seconds"] - expected_duration)
    print(f"  -> Duration timing deviation:      {deviation:.2f}s (Within target tolerance)")
    assert deviation <= 0.2, f"Cut duration deviated too far: {deviation}s"

    print("  [PASS] Real video trimmed and measured with 100% success!")

    print("\n" + "=" * 70)
    print("  MILESTONE 4 REAL-WORLD VERIFICATION COMPLETE!")
    print(f"  Source Video: {source_video}")
    print(f"  Cut Clip:     {output_path}")
    print("  (You can open both .mp4 files in Windows Media Player to see the cut!)")
    print("=" * 70 + "\n")
    return True


if __name__ == "__main__":
    success = run_milestone4_verification()
    sys.exit(0 if success else 1)
