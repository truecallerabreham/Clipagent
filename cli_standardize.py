"""Interactive CLI for Milestone 11: The Standardizer.

Conforms heterogeneous video clips into uniform, concat-ready assets
with matching resolution, constant framerate, yuv420p pixel format,
and 48kHz stereo AAC audio tracks.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from script.media_consistency.render import standardize_media_clips
from script.tools import _shared


def list_workspace_videos() -> list[Path]:
    """Scan WORKSPACE directory for available source MP4 video files."""
    workspace = _shared.WORKSPACE
    if not workspace.exists():
        return []
    valid_exts = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
    return sorted(
        [
            f for f in workspace.iterdir()
            if f.is_file() and f.suffix.lower() in valid_exts and not f.name.startswith("_temp_")
        ],
        key=lambda x: x.name.lower(),
    )


def main() -> None:
    print("\n" + "=" * 75)
    print("  CLIPAGENT MILESTONE 11: THE STANDARDIZER (CLI)")
    print("  (Physical Media Conforming & Concat-Ready Stream Standardization)")
    print("=" * 75)

    workspace_videos = list_workspace_videos()

    print(f"\nWorkspace Folder: {_shared.WORKSPACE}")
    if workspace_videos:
        print("Available source videos in workspace:")
        for idx, vid in enumerate(workspace_videos, start=1):
            size_mb = vid.stat().st_size / (1024 * 1024)
            print(f"  [{idx}] {vid.name:<35} ({size_mb:.2f} MB)")
    else:
        print("  (No video files currently in workspace. Run tests/verify_milestone11.py first to create sample clips!)")

    print("\nSelect clips to standardize:")
    print("  Enter comma-separated numbers (e.g. '1, 2, 3'), filenames, or 'all'.")
    user_input = input("  > ").strip()
    if not user_input:
        print("No clips selected. Exiting.")
        return

    selected_clips: list[str] = []
    if user_input.lower() == "all" and workspace_videos:
        selected_clips = [v.name for v in workspace_videos]
    else:
        for token in user_input.split(","):
            token = token.strip()
            if not token:
                continue
            if token.isdigit() and workspace_videos:
                idx = int(token) - 1
                if 0 <= idx < len(workspace_videos):
                    selected_clips.append(workspace_videos[idx].name)
                else:
                    print(f"Invalid index: {token}")
                    return
            else:
                selected_clips.append(token)

    if not selected_clips:
        print("No valid clips specified. Exiting.")
        return

    print(f"\nSelected {len(selected_clips)} clips: {selected_clips}")

    target_res = input("\nEnter target master resolution (e.g. 1920x1080) [Enter to auto-derive]: ").strip() or None
    target_fps_str = input("Enter target master frame rate (e.g. 30.0) [Enter to auto-derive]: ").strip() or None
    target_fps = float(target_fps_str) if target_fps_str else None

    subfolder = input("Enter destination subfolder [default: standardized]: ").strip() or "standardized"

    print("\nExecuting physical standardization and post-audit with native FFmpeg...")
    receipt_raw = standardize_media_clips(
        selected_clips,
        target_resolution=target_res,
        target_fps=target_fps,
        output_subfolder=subfolder,
    )

    try:
        receipt = json.loads(receipt_raw)
        print("\n" + "=" * 75)
        print("  STANDARDIZATION RECEIPT & QUALITY AUDIT")
        print("=" * 75)
        print(f"  Status:                   {receipt.get('status')}")
        print(f"  Total Processed Clips:    {receipt.get('standardized_clips_count')}")
        print(f"  Output Directory:         {receipt.get('output_directory')}")
        print(f"  Post-Audit Concat-Ready:  {'YES (100% Concat-Ready!)' if receipt.get('is_concat_ready') else 'NO'}")
        print(f"  Post-Audit Consistent:    {'YES' if receipt.get('post_audit_consistent') else 'NO'}")

        discrepancies = receipt.get("post_audit_discrepancies", [])
        if discrepancies:
            print("\n  Remaining Discrepancies:")
            for d in discrepancies:
                print(f"    [!] {d}")
        else:
            print("\n  [VERIFIED] Zero remaining discrepancies! All files are perfectly normalized.")

        std = receipt.get("master_standard", {})
        if std:
            print("\n  --- Master Target Profile ---")
            print(f"    Resolution:   {std.get('resolution')}")
            print(f"    Frame Rate:   {std.get('fps')} FPS")
            print(f"    Audio Track:  {std.get('sample_rate')} Hz, {std.get('channel_layout')} ({std.get('audio_codec')})")
            print(f"    Pixel Format: {std.get('pix_fmt')}")

        clips = receipt.get("standardized_clips", [])
        if clips:
            print("\n  --- Conformed Clip Manifest ---")
            for c in clips:
                reenc = "Transcoded" if c.get("was_reencoded") else "Stream-Copied"
                print(f"    * {c.get('standardized_name'):<30} | {c.get('resolution')} | {c.get('fps')} FPS | Audio: {c.get('has_audio')} | {reenc} | {c.get('file_size_human')}")

        print("\n" + "=" * 75)
        print(f"\n[SUCCESS] Standardized clips are ready in: {receipt.get('output_directory')}\n")

    except json.JSONDecodeError:
        print(f"\nResult / Error:\n{receipt_raw}")


if __name__ == "__main__":
    main()
