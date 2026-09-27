"""Clipagent Phase 1 Interactive Video Inspector.

Allows you to manually test Phase 1 with any video file of your choice.
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


def main() -> None:
    print("\n" + "=" * 65)
    print("  CLIPAGENT PHASE 1: INTERACTIVE VIDEO INSPECTOR")
    print("=" * 65)
    print(f"Task Workspace (temp):      {_shared.WORKSPACE}")
    print(f"User Workspace (user_temp): {_shared.USER_WORKSPACE}")
    print("-" * 65)

    # If the user passed a path in the command line (e.g. python cli_inspect.py my_video.mp4)
    if len(sys.argv) > 1:
        video_input = sys.argv[1]
    else:
        # Prompt the user for input
        print("\nTip: You can place any .mp4 video into the 'temp' or 'user_temp' folder,")
        print("     or enter an absolute path to test the security boundary.")
        video_input = input("\nEnter video filename or path: ").strip()

    if not video_input:
        print("No video provided. Exiting.")
        return

    print(f"\n[1] Inspecting: '{video_input}'...")
    raw_result = inspect_video_duration(video_input)

    # Check if the result is valid JSON (success) or an error string
    try:
        data = json.loads(raw_result)
        print("\n[SUCCESS] Metadata Extracted:")
        print(f"  -> Path:       {data.get('path')}")
        print(f"  -> Duration:   {data.get('duration_seconds')} seconds")
        print(f"  -> Resolution: {data.get('resolution')} (width={data.get('width')}, height={data.get('height')})")
        print(f"  -> Frame Rate: {data.get('fps')} FPS")
        print("\nRaw JSON for AI Agent:")
        print(f"  {raw_result}")
    except json.JSONDecodeError:
        print("\n[RESULT / SECURITY NOTICE]:")
        print(f"  {raw_result}")

    print("\n" + "=" * 65 + "\n")


if __name__ == "__main__":
    main()
