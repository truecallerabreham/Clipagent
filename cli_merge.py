"""Clipagent Phase 2 Interactive Video Merger (The Glue).

Allows you to manually test Milestone 5 by concatenating any video files.
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
from script.tools.inspect_video_duration import inspect_video_duration
from script.tools.merge_videos import merge_videos


def main() -> None:
    print("\n" + "=" * 65)
    print("  CLIPAGENT MILESTONE 5: INTERACTIVE VIDEO MERGER (THE GLUE)")
    print("=" * 65)
    print(f"Task Workspace (temp):      {_shared.WORKSPACE}")
    print(f"User Workspace (user_temp): {_shared.USER_WORKSPACE}")
    print("-" * 65)

    # Command line argument mode: python cli_merge.py clip1.mp4 clip2.mp4 my_compilation
    if len(sys.argv) >= 3:
        # If the last argument doesn't look like a video file, treat it as output_name
        possible_out = sys.argv[-1]
        if not possible_out.endswith(".mp4") and len(sys.argv) >= 4:
            video_inputs = sys.argv[1:-1]
            output_name = possible_out
        else:
            video_inputs = sys.argv[1:]
            output_name = "merged"
    else:
        # Interactive prompt mode
        print("\nTip: Enter the names of at least 2 videos inside 'temp' or 'user_temp'.")
        print("     Separate filenames with commas or spaces.")
        raw_in = input("\nEnter video filenames to merge: ").strip()
        if not raw_in:
            print("No videos provided. Exiting.")
            return

        # Split by comma or whitespace
        parts = [p.strip().strip("\"'") for p in raw_in.replace(",", " ").split() if p.strip()]
        video_inputs = parts

        output_name = input("Enter output compilation name (optional, default 'merged'): ").strip() or "merged"

    print(f"\n[1] Inspecting {len(video_inputs)} input clips before merging:")
    total_expected = 0.0
    for v in video_inputs:
        probe = inspect_video_duration(v)
        try:
            d = json.loads(probe)
            dur = d.get("duration_seconds", 0.0)
            total_expected += dur
            print(f"  -> {v:25}: {dur:5.2f}s ({d.get('resolution')})")
        except Exception:
            print(f"  -> {v:25}: [Warning: Cannot pre-measure]")

    print(f"\n[2] Gluing {len(video_inputs)} clips into '{output_name}.mp4'...")
    raw_result = merge_videos(video_inputs, output_name=output_name)

    try:
        data = json.loads(raw_result)
        out_path = data.get("path")
        print("\n[SUCCESS] Videos Successfully Glued Together!")
        print(f"  -> Path:       {out_path}")
        print(f"  -> Clips:      {data.get('clip_count')}")
        print(f"  -> Duration:   {data.get('duration')} seconds")
        print(f"  -> Resolution: {data.get('resolution')}")

        # Verify output with Milestone 3 Ruler
        print("\n[3] Verifying glued clip with Milestone 3 Ruler:")
        probe_result = inspect_video_duration(Path(out_path).name)
        probe_data = json.loads(probe_result)
        print(f"  -> Verified Duration:   {probe_data.get('duration_seconds')}s")
        print(f"  -> Verified Resolution: {probe_data.get('resolution')}")
        print(f"  -> Verified FPS:        {probe_data.get('fps')} FPS")
        print(f"\nYou can open and play this merged video in Windows Media Player:")
        print(f"  {out_path}")

    except json.JSONDecodeError:
        print("\n[RESULT / ERROR NOTICE]:")
        print(f"  {raw_result}")

    print("\n" + "=" * 65 + "\n")


if __name__ == "__main__":
    main()
