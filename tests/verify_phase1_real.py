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

from app.runtime_paths import configure_runtime_environment, get_bundle_root, get_runtime_root
from script.tools import _shared
from script.tools.inspect_video_duration import inspect_video_duration


def print_step(title: str, explanation: str) -> None:
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"  {explanation}")
    print(f"{'=' * 70}")


def generate_real_video(target_path: Path, duration_seconds: int = 4, fps: int = 30) -> None:
    """Generate a real, playable MP4 video file on disk using OpenCV."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    width, height = 640, 360
    total_frames = duration_seconds * fps

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(target_path), fourcc, fps, (width, height))

    print(f"  -> Generating {total_frames} real video frames ({duration_seconds}s @ {fps}fps)...")
    for i in range(total_frames):
        # Create an animated canvas: shifting background gradient
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        color_r = int((i / total_frames) * 200)
        color_g = int(80 + (i / total_frames) * 100)
        color_b = int(220 - (i / total_frames) * 150)
        frame[:] = (color_b, color_g, color_r)

        # Draw a moving progress circle (bouncing across screen)
        circle_x = int(50 + (i / total_frames) * (width - 100))
        circle_y = int(height / 2 + 40 * np.sin(i * 0.2))
        cv2.circle(frame, (circle_x, circle_y), 24, (255, 255, 255), -1)

        # Burn-in timestamp text on the video frames
        current_time = i / fps
        cv2.putText(
            frame,
            "CLIPAGENT REAL VIDEO DEMO",
            (40, 60),
            cv2.FONT_HERSHEY_DUPLEX,
            0.8,
            (255, 255, 255),
            2,
        )
        cv2.putText(
            frame,
            f"Timestamp: {current_time:.2f}s / {duration_seconds:.2f}s",
            (40, 110),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (240, 240, 240),
            1,
        )
        cv2.putText(
            frame,
            f"Frame: {i+1} of {total_frames}",
            (40, 140),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (200, 200, 200),
            1,
        )
        writer.write(frame)

    writer.release()
    print(f"  -> Real MP4 successfully encoded and written to disk!")
    print(f"  -> File size: {target_path.stat().st_size:,} bytes")


def run_phase1_real_world_demo() -> bool:
    print("\n" + "#" * 70)
    print("  CLIPAGENT PHASE 1 REAL-WORLD ACTION VERIFICATION")
    print("  (Milestones 1 -> 2 -> 3 Fully Connected & Executed on Real Media)")
    print("#" * 70)

    # -------------------------------------------------------------------------
    # PART 1: Milestone 1 in Action (The Folder Map)
    # -------------------------------------------------------------------------
    print_step(
        "PART 1: Milestone 1 in Action (The Folder Map)",
        "Bootstrapping runtime environment, ensuring folders, and verifying write access.",
    )
    configure_runtime_environment()
    bundle_root = get_bundle_root()
    runtime_root = get_runtime_root()
    workspace = _shared.WORKSPACE

    print(f"  -> Bundle Root (Read-only source): {bundle_root}")
    print(f"  -> Runtime Root (Writable data):   {runtime_root}")
    print(f"  -> Task Workspace (Video renders): {workspace}")
    assert workspace.exists() and workspace.is_dir()
    print("  [PASS] Runtime paths and directories verified on real filesystem!")

    # -------------------------------------------------------------------------
    # PART 2: Milestone 2 in Action (The Silent Helper & Security Perimeter)
    # -------------------------------------------------------------------------
    print_step(
        "PART 2: Milestone 2 in Action (Silent Helper & Perimeter Guard)",
        "Testing stealth subprocess execution and active boundary security.",
    )
    # 1. Silent subprocess execution
    proc = _shared.run_subprocess([sys.executable, "-c", "import sys; print('Stealth Subprocess OK')"], capture_output=True, text=True)
    print(f"  -> Silent Subprocess result: {proc.stdout.strip()}")
    assert proc.returncode == 0

    # 2. Perimeter rejection of external system file
    forbidden_file = "C:/Windows/System32/drivers/etc/hosts"
    blocked_result = inspect_video_duration(forbidden_file)
    print(f"  -> Attempt to access external path ({forbidden_file}):")
    print(f"     Engine output: {blocked_result}")
    assert "Inspection failed: File does not exist or is outside WORKSPACE" in blocked_result
    print("  [PASS] Silent subprocess ran cleanly and external security violation blocked!")

    # -------------------------------------------------------------------------
    # PART 3: Milestone 3 in Action (The Stopwatch & Ruler on REAL Video)
    # -------------------------------------------------------------------------
    print_step(
        "PART 3: Milestone 3 in Action (The Stopwatch & Ruler)",
        "Generating an actual playable MP4 video on disk and measuring its real properties.",
    )
    real_video_path = workspace / "phase1_real_lecture.mp4"
    target_duration = 4
    target_fps = 30

    # Actually generate real video bytes on disk
    generate_real_video(real_video_path, duration_seconds=target_duration, fps=target_fps)

    # Now run Milestone 3's inspect_video_duration on this real video file!
    print("\n  -> Calling inspect_video_duration('phase1_real_lecture.mp4')...")
    inspection_raw_json = inspect_video_duration(real_video_path.name)
    print(f"  -> Raw JSON returned to AI Agent:\n     {inspection_raw_json}")

    # Parse and assert on real data
    data = json.loads(inspection_raw_json)
    print(f"\n  -> Extracted Video Metrics:")
    print(f"     - Status:            {data.get('status')}")
    print(f"     - Duration:          {data.get('duration_seconds')} seconds")
    print(f"     - Resolution:        {data.get('resolution')} (width={data.get('width')}, height={data.get('height')})")
    print(f"     - Frames Per Second: {data.get('fps')} FPS")

    assert data.get("status") == "success", "Inspection failed!"
    assert data.get("duration_seconds") == float(target_duration), f"Duration mismatch: {data.get('duration_seconds')} != {target_duration}"
    assert data.get("fps") == float(target_fps), f"FPS mismatch: {data.get('fps')} != {target_fps}"
    assert data.get("resolution") == "640x360", f"Resolution mismatch: {data.get('resolution')} != 640x360"
    print("  [PASS] Real video measurements match ground truth with 100% accuracy!")

    print("\n" + "=" * 70)
    print("  PHASE 1 REAL-WORLD DEMONSTRATION COMPLETE: 100% VERIFIED!")
    print(f"  Playable video saved at: {real_video_path}")
    print("  (You can open and play this .mp4 file in Windows Media Player!)")
    print("=" * 70 + "\n")
    return True


if __name__ == "__main__":
    success = run_phase1_real_world_demo()
    sys.exit(0 if success else 1)
