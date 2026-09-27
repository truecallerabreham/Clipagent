"""Clipagent Phase 2 Interactive Batch Video Cutter (The Batch Scissors).

Allows you to manually test Milestone 6 by slicing multiple highlights from any video.
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
from script.tools.batch_cut_video import batch_cut_video
from script.tools.inspect_video_duration import inspect_video_duration


def main() -> None:
    print("\n" + "=" * 65)
    print("  CLIPAGENT MILESTONE 6: INTERACTIVE BATCH CUTTER (BATCH SCISSORS)")
    print("=" * 65)
    print(f"Task Workspace (temp):      {_shared.WORKSPACE}")
    print(f"User Workspace (user_temp): {_shared.USER_WORKSPACE}")
    print("-" * 65)

    # 1. Ask for video filename
    if len(sys.argv) > 1:
        video_input = sys.argv[1]
    else:
        print("\nTip: Enter the name of a video inside 'temp' or 'user_temp'.")
        video_input = input("Enter source video filename: ").strip()

    if not video_input:
        print("No video provided. Exiting.")
        return

    # Measure source video first
    probe = inspect_video_duration(video_input)
    try:
        data = json.loads(probe)
        duration = data.get("duration_seconds", 0.0)
        print(f"\n-> Source video found: {duration}s ({data.get('resolution')})")
    except Exception:
        print("\n-> Note: Could not pre-measure source video.")
        duration = 9999.0

    # 2. Collect segments from user
    segments = []
    print("\nDefine the segments you want to cut.")
    print("Enter 'done' when you have finished adding intervals.\n")

    clip_count = 1
    while True:
        prompt = f"Clip #{clip_count} start & end seconds (e.g. '2.5 6.0' or 'done'): "
        raw = input(prompt).strip()
        if raw.lower() in {"done", "exit", "q", ""}:
            if not segments:
                print("At least 1 segment is required. Exiting.")
                return
            break

        parts = raw.split()
        if len(parts) < 2:
            print("  [!] Please enter both start and end times separated by space.")
            continue

        try:
            start = float(parts[0])
            end = float(parts[1])
        except ValueError:
            print("  [!] Start and end times must be numbers.")
            continue

        if start < 0 or end <= start or end > duration + 0.1:
            print(f"  [!] Invalid interval: must be between 0s and {duration}s.")
            continue

        name = input(f"Clip #{clip_count} name (optional, press Enter to auto-name): ").strip()
        segments.append({
            "start": start,
            "end": end,
            "output_name": name if name else f"highlight_{clip_count}",
        })
        clip_count += 1

    # 3. Execute batch cutting
    print(f"\n[1] Executing batch cut of {len(segments)} clips in ONE operation...")
    raw_result = batch_cut_video(video_input, segments)

    try:
        res = json.loads(raw_result)
        print("\n[SUCCESS] Batch Slicing Completed!")
        print(f"  -> Total Clips Generated: {res.get('total_clips')}")
        print("-" * 65)

        for clip in res.get("clips", []):
            print(f"  * Clip #{clip.get('clip_index')} [{clip.get('start')}s -> {clip.get('end')}s] ({clip.get('duration')}s):")
            print(f"    Path: {clip.get('path')}")

        print("\nYou can open and play each highlight clip in Windows Media Player!")

    except json.JSONDecodeError:
        print("\n[RESULT / ERROR NOTICE]:")
        print(f"  {raw_result}")

    print("\n" + "=" * 65 + "\n")


if __name__ == "__main__":
    main()
