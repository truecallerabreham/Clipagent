"""Clipagent Phase 2 Interactive Video Transition Tool (The Crossfade).

Allows you to manually test Milestone 7 by blending any two videos with cinematic transitions.
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
from script.tools.add_transition import VALID_TRANSITIONS, add_transition
from script.tools.inspect_video_duration import inspect_video_duration


def main() -> None:
    print("\n" + "=" * 65)
    print("  CLIPAGENT MILESTONE 7: INTERACTIVE VIDEO TRANSITIONS (THE CROSSFADE)")
    print("=" * 65)
    print(f"Task Workspace (temp):      {_shared.WORKSPACE}")
    print(f"User Workspace (user_temp): {_shared.USER_WORKSPACE}")
    print("-" * 65)

    if len(sys.argv) >= 3:
        v1 = sys.argv[1]
        v2 = sys.argv[2]
        t_type = sys.argv[3] if len(sys.argv) >= 4 else "fade"
        try:
            t_dur = float(sys.argv[4]) if len(sys.argv) >= 5 else 1.0
        except ValueError:
            t_dur = 1.0
        out_name = sys.argv[5] if len(sys.argv) >= 6 else "transition"
    else:
        print("\nTip: Enter the names of 2 videos inside 'temp' or 'user_temp'.")
        v1 = input("Enter video 1 (outgoing scene): ").strip()
        v2 = input("Enter video 2 (incoming scene): ").strip()
        if not v1 or not v2:
            print("Both video filenames are required. Exiting.")
            return

        print("\nAvailable transition styles:")
        print("  fade, wipeleft, wiperight, slideleft, slideright, dissolve, pixelize")
        t_type = input("Enter transition style (default 'fade'): ").strip() or "fade"

        dur_str = input("Enter transition duration (seconds, default 1.0): ").strip() or "1.0"
        try:
            t_dur = float(dur_str)
        except ValueError:
            print("Invalid duration number, defaulting to 1.0s.")
            t_dur = 1.0

        out_name = input("Enter output clip name (default 'transition'): ").strip() or "transition"

    # Pre-measure input videos
    print("\n[1] Pre-measuring input clips:")
    for v in (v1, v2):
        probe = inspect_video_duration(v)
        try:
            d = json.loads(probe)
            print(f"  -> {v:25}: {d.get('duration_seconds')}s ({d.get('resolution')})")
        except Exception:
            print(f"  -> {v:25}: [Could not pre-measure]")

    print(f"\n[2] Applying '{t_type}' transition ({t_dur}s) between {v1} and {v2}...")
    raw_result = add_transition(
        v1,
        v2,
        transition_type=t_type,
        transition_duration=t_dur,
        output_name=out_name,
    )

    try:
        data = json.loads(raw_result)
        out_path = data.get("path")
        print("\n[SUCCESS] Transition Video Created!")
        print(f"  -> Path:        {out_path}")
        print(f"  -> Total Length:{data.get('duration')} seconds")
        print(f"  -> Style:       {data.get('transition')} ({data.get('transition_duration')}s)")

        # Verify output with Milestone 3 Ruler
        print("\n[3] Verifying transition clip with Milestone 3 Ruler:")
        probe_result = inspect_video_duration(Path(out_path).name)
        probe_data = json.loads(probe_result)
        print(f"  -> Verified Duration:   {probe_data.get('duration_seconds')}s")
        print(f"  -> Verified Resolution: {probe_data.get('resolution')}")
        print(f"  -> Verified FPS:        {probe_data.get('fps')} FPS")
        print(f"\nYou can open and play this transition in Windows Media Player:")
        print(f"  {out_path}")

    except json.JSONDecodeError:
        print("\n[RESULT / ERROR NOTICE]:")
        print(f"  {raw_result}")

    print("\n" + "=" * 65 + "\n")


if __name__ == "__main__":
    main()
