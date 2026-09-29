"""Interactive CLI for Milestone 9: The Export Box.

Enables interactive testing of video exporting, quality presets, social aspect ratio
formatting (16:9, 9:16, 1:1), web faststart optimization, and animated GIF generation.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from script.tools import _shared
from script.tools.export_video import EXPORT_PRESETS, VALID_ASPECT_RATIOS, VALID_FORMATS, export_video


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
    print("  CLIPAGENT MILESTONE 9: THE EXPORT BOX (CLI)")
    print("  (Release Packaging, Quality Presets, Aspect Ratios & FastStart)")
    print("=" * 75)

    workspace_videos = list_workspace_videos()

    print(f"\nWorkspace Folder: {_shared.WORKSPACE}")
    if workspace_videos:
        print("Available source videos in workspace:")
        for idx, vid in enumerate(workspace_videos, start=1):
            size_mb = vid.stat().st_size / (1024 * 1024)
            print(f"  [{idx}] {vid.name:<35} ({size_mb:.2f} MB)")
    else:
        print("  (No video files currently in workspace. Run tests/verify_milestone9.py first to create a master video!)")

    print("\nSelect video to export:")
    user_input = input("  Enter number or filename > ").strip()
    if not user_input:
        print("No video selected. Exiting.")
        return

    selected_video: str = ""
    if user_input.isdigit() and workspace_videos:
        idx = int(user_input) - 1
        if 0 <= idx < len(workspace_videos):
            selected_video = workspace_videos[idx].name
        else:
            print(f"Invalid index: {user_input}")
            return
    else:
        selected_video = user_input

    print(f"\nSelected source video: {selected_video}")

    # Format selection
    print("\nChoose Export Container Format:")
    format_options = ["mp4", "mov", "mkv", "webm", "gif"]
    print("  [1] mp4   - Standard H.264 + AAC with FastStart web streaming (Recommended)")
    print("  [2] mov   - QuickTime MOV container")
    print("  [3] mkv   - Matroska container")
    print("  [4] webm  - VP9 web container")
    print("  [5] gif   - High-fidelity animated GIF preview (2-pass palette)")
    fmt_choice = input("Select format [1-5] (default 1 - mp4): ").strip() or "1"
    chosen_format = "mp4"
    if fmt_choice.isdigit():
        f_idx = int(fmt_choice) - 1
        if 0 <= f_idx < len(format_options):
            chosen_format = format_options[f_idx]

    # Aspect ratio selection (if not GIF)
    chosen_aspect = "source"
    if chosen_format != "gif":
        print("\nChoose Aspect Ratio Framing:")
        print("  [1] source - Keep original resolution and framing")
        print("  [2] 16:9   - Widescreen landscape (YouTube, TV, Desktop)")
        print("  [3] 9:16   - Vertical portrait (TikTok, Instagram Reels, YouTube Shorts)")
        print("  [4] 1:1    - Square framing (Instagram feed posts)")
        ar_choice = input("Select aspect ratio [1-4] (default 1 - source): ").strip() or "1"
        ar_map = {"1": "source", "2": "16:9", "3": "9:16", "4": "1:1"}
        chosen_aspect = ar_map.get(ar_choice, "source")

    # Quality preset selection
    chosen_preset = "high"
    if chosen_format != "gif":
        print("\nChoose Quality Profile Preset:")
        print("  [1] high     - Master quality (CRF 18, 320k audio)")
        print("  [2] standard - Web balanced (CRF 23, 192k audio)")
        print("  [3] mobile   - Compressed for mobile (CRF 28, max 720p, 128k audio)")
        print("  [4] lossless - Archival near-lossless (CRF 14)")
        p_choice = input("Select preset [1-4] (default 1 - high): ").strip() or "1"
        p_map = {"1": "high", "2": "standard", "3": "mobile", "4": "lossless"}
        chosen_preset = p_map.get(p_choice, "high")
    else:
        chosen_preset = "gif"

    # FastStart option
    faststart = True
    if chosen_format in {"mp4", "mov"}:
        fs_input = input("\nEnable Web FastStart (+faststart) for instant browser playback? [Y/n]: ").strip().lower()
        faststart = (fs_input not in {"n", "no", "false"})

    # Output filename
    stem = Path(selected_video).stem
    default_out = f"{stem}_exported"
    out_input = input(f"\nEnter output filename (without extension) [default: {default_out}]: ").strip()
    chosen_output_name = out_input or default_out

    print("\nExporting and packaging video with native FFmpeg...")
    receipt_raw = export_video(
        selected_video,
        output_name=chosen_output_name,
        preset=chosen_preset,
        aspect_ratio=chosen_aspect,
        format=chosen_format,
        faststart=faststart,
    )

    try:
        receipt = json.loads(receipt_raw)
        print("\n" + "=" * 75)
        print("  STRUCTURED EXPORT RECEIPT")
        print("=" * 75)
        print(f"  Status:             {receipt.get('status')}")
        print(f"  Source Input:       {receipt.get('input_file')}")
        print(f"  Export File Name:   {receipt.get('export_name')}")
        print(f"  Export Destination: {receipt.get('export_path')}")
        print(f"  Container Format:   {receipt.get('format')}")
        print(f"  Quality Preset:     {receipt.get('preset')}")
        print(f"  Aspect Ratio:       {receipt.get('aspect_ratio')}")
        print(f"  File Size:          {receipt.get('file_size_human')} ({receipt.get('file_size_bytes'):,} bytes)")
        print(f"  Measured Duration:  {receipt.get('duration')}s")
        print(f"  Output Resolution:  {receipt.get('resolution')}")
        print(f"  Output Framerate:   {receipt.get('fps')} FPS")
        print(f"  Average Bitrate:    {receipt.get('bitrate_kbps')} kbps")
        print(f"  FastStart Enabled:  {receipt.get('faststart_enabled')}")
        print(f"  Audio Track:        {receipt.get('has_audio')}")
        print("=" * 75)
        print(f"\n[SUCCESS] Deliverable is ready at: {receipt.get('export_path')}\n")

    except json.JSONDecodeError:
        print(f"\nResult / Error:\n{receipt_raw}")


if __name__ == "__main__":
    main()
