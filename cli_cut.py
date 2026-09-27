"""Clipagent Phase 2 Interactive Video Cutter.

Allows you to manually test Milestone 4 (The Scissors) by trimming any video file.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from script.tools import _shared
from script.tools.cut_video import cut_video
from script.tools.inspect_video_duration import inspect_video_duration


def main() -> None:
    print("\n" + "=" * 65)
    print("  CLIPAGENT MILESTONE 4: INTERACTIVE VIDEO CUTTER (THE SCISSORS)")
    print("=" * 65)
    print(f"Task Workspace (temp):      {_shared.WORKSPACE}")
    print(f"User Workspace (user_temp): {_shared.USER_WORKSPACE}")
    print("-" * 65)

    # Command line argument mode: python cli_cut.py my_video.mp4 2.0 5.5 my_highlight
    if len(sys.argv) >= 4:
        video_input = sys.argv[1]
        try:
            start_time = float(sys.argv[2])
            end_time = float(sys.argv[3])
        except ValueError:
            print("Error: start_time and end_time must be numbers (seconds).")
            return
        output_name = sys.argv[4] if len(sys.argv) >= 5 else ""
    else:
        # Interactive prompt mode
        print("\nTip: Enter the name of a video inside 'temp' or 'user_temp'.")
        video_input = input("Enter video filename or path: ").strip()
        if not video_input:
            print("No video provided. Exiting.")
            return

        # First measure the source video so user knows the total length
        source_probe = inspect_video_duration(video_input)
        try:
            source_data = json.loads(source_probe)
            print(f"-> Source video detected: {source_data['duration_seconds']}s ({source_data['resolution']})")
        except Exception:
            pass

        try:
            start_str = input("Enter cut start time (seconds, e.g. 1.5): ").strip()
            start_time = float(start_str)
            end_str = input("Enter cut end time   (seconds, e.g. 4.0): ").strip()
            end_time = float(end_str)
        except ValueError:
            print("Invalid time input. Please provide numbers.")
            return

        output_name = input("Enter output clip name (optional, press Enter to auto-generate): ").strip()

    print(f"\n[1] Executing cut: {video_input} [{start_time}s -> {end_time}s]...")
    raw_result = cut_video(video_input, start_time=start_time, end_time=end_time, output_name=output_name)

    try:
        data = json.loads(raw_result)
        out_path = data.get("path")
        print("\n[SUCCESS] Cut Clip Created!")
        print(f"  -> Path:     {out_path}")
        print(f"  -> Duration: {data.get('duration')} seconds")

        # Verify the new clip with Milestone 3's ruler
        print("\n[2] Verifying cut clip with Milestone 3 Ruler:")
        probe_result = inspect_video_duration(Path(out_path).name)
        probe_data = json.loads(probe_result)
        print(f"  -> Verified Duration:   {probe_data.get('duration_seconds')}s")
        print(f"  -> Verified Resolution: {probe_data.get('resolution')}")
        print(f"  -> Verified FPS:        {probe_data.get('fps')} FPS")
        print(f"\nYou can open and play this clip in Windows Media Player:")
        print(f"  {out_path}")

    except json.JSONDecodeError:
        print("\n[RESULT / ERROR NOTICE]:")
        print(f"  {raw_result}")

    print("\n" + "=" * 65 + "\n")


if __name__ == "__main__":
    main()
