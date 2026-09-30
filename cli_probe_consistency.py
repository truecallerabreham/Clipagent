"""Interactive CLI for Milestone 10: The Video Inspector (Media Consistency Probe).

Audits media consistency across video clips in the workspace, detects format
discrepancies (resolution, framerate, audio tracks, rotation), and generates
an actionable standardization recipe.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from script.media_consistency.probe import inspect_media_consistency
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
    print("  CLIPAGENT MILESTONE 10: THE VIDEO INSPECTOR (CLI)")
    print("  (Forensic Multi-Stream Probing & Media Consistency Audit)")
    print("=" * 75)

    workspace_videos = list_workspace_videos()

    print(f"\nWorkspace Folder: {_shared.WORKSPACE}")
    if workspace_videos:
        print("Available videos in workspace:")
        for idx, vid in enumerate(workspace_videos, start=1):
            size_mb = vid.stat().st_size / (1024 * 1024)
            print(f"  [{idx}] {vid.name:<35} ({size_mb:.2f} MB)")
    else:
        print("  (No video files currently in workspace. Run tests/verify_milestone10.py first to create sample clips!)")

    print("\nSelect clips to audit for consistency:")
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

    print("\nRunning forensic media consistency audit...")
    report_raw = inspect_media_consistency(
        selected_clips,
        target_resolution=target_res,
        target_fps=target_fps,
    )

    try:
        report = json.loads(report_raw)
        print("\n" + "=" * 75)
        print("  MEDIA CONSISTENCY AUDIT REPORT")
        print("=" * 75)
        print(f"  Total Clips Audited:  {report.get('clip_count')}")
        print(f"  Is Format Consistent: {'YES (All streams match)' if report.get('is_consistent') else 'NO (Mismatches detected)'}")
        print(f"  Is Concat-Ready:      {'YES (Stream copy supported)' if report.get('is_concat_ready') else 'NO (Re-encode/Conforming required)'}")

        discrepancies = report.get("discrepancies", [])
        if discrepancies:
            print("\n  --- Detected Incompatibilities ---")
            for d in discrepancies:
                print(f"    [!] {d}")
        else:
            print("\n  [PASS] Zero discrepancies detected! All clips share identical media profiles.")

        std = report.get("recommended_standard", {})
        if std:
            print("\n  --- Recommended Master Standard ---")
            print(f"    Target Resolution:   {std.get('resolution')}")
            print(f"    Target Frame Rate:   {std.get('fps')} FPS")
            print(f"    Target Video Codec:  {std.get('video_codec')} ({std.get('pix_fmt')})")
            print(f"    Target Audio Codec:  {std.get('audio_codec')} ({std.get('sample_rate')} Hz, {std.get('channel_layout')})")

        recipes = report.get("recipes", [])
        if recipes:
            print("\n  --- Per-Clip Standardization Recipes ---")
            for r in recipes:
                print(f"\n    File: {r.get('file_name')}")
                print(f"      Needs Re-encode:    {r.get('needs_reencode')}")
                if r.get("needs_scale"):
                    print(f"      Needs Scale:        YES -> Scale to {std.get('resolution')}")
                if r.get("needs_fps_conforming"):
                    print(f"      Needs FPS Conform:  YES -> Resample to {std.get('fps')} FPS")
                if r.get("needs_audio_resample"):
                    print(f"      Needs Audio Fix:    YES -> Resample to {std.get('sample_rate')} Hz")
                if r.get("needs_synthetic_audio"):
                    print(f"      Needs Audio Fix:    YES -> Synthesize silent stereo audio track")
                if r.get("needs_rotation_fix"):
                    print(f"      Needs Rotation Fix: YES -> Transpose to 0 deg")

                vf = r.get("suggested_video_filter")
                if vf:
                    print(f"      Suggested Video Filter: -vf \"{vf}\"")
                af = r.get("suggested_audio_filter")
                if af:
                    print(f"      Suggested Audio Filter: -af \"{af}\"")

        print("\n" + "=" * 75)

    except json.JSONDecodeError:
        print(f"\nResult / Error:\n{report_raw}")


if __name__ == "__main__":
    main()
