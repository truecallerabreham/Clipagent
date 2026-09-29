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

from script.tools import _shared
from script.tools.export_video import export_video
from script.tools.inspect_video_duration import inspect_video_duration


def print_step(title: str, explanation: str) -> None:
    print(f"\n{'=' * 75}")
    print(f"  {title}")
    print(f"  {explanation}")
    print(f"{'=' * 75}")


def generate_test_video(
    target_path: Path,
    title: str,
    duration_seconds: int = 3,
    fps: int = 30,
) -> None:
    """Generate a real 1280x720 MP4 video on disk with colored gradient and burned-in timecodes."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    width, height = 1280, 720
    total_frames = duration_seconds * fps

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(target_path), fourcc, fps, (width, height))

    for i in range(total_frames):
        # Create an animated color gradient
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        color_b = int(120 + 80 * np.sin(2 * np.pi * i / total_frames))
        color_g = int(140 + 60 * np.cos(2 * np.pi * i / total_frames))
        color_r = int(200)
        frame[:, :] = (color_b, color_g, color_r)

        # Draw a central frame box
        cv2.rectangle(frame, (100, 100), (width - 100, height - 100), (255, 255, 255), 3)

        cv2.putText(
            frame, title, (140, 260), cv2.FONT_HERSHEY_DUPLEX, 1.3, (255, 255, 255), 3
        )
        cv2.putText(
            frame,
            f"Playback: {i/fps:.2f}s / {duration_seconds:.2f}s | Frame {i+1}/{total_frames}",
            (140, 340),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (240, 240, 240),
            2,
        )
        cv2.putText(
            frame,
            "CLIPAGENT MASTER SOURCE (1280x720 16:9)",
            (140, 420),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (220, 255, 220),
            2,
        )
        writer.write(frame)

    writer.release()


def run_milestone9_verification() -> bool:
    print("\n" + "#" * 75)
    print("  CLIPAGENT MILESTONE 9 REAL-WORLD VERIFICATION: THE EXPORT BOX")
    print("  (Release Packaging, Quality Profiles, Aspect Ratios & FastStart)")
    print("#" * 75)

    workspace = _shared.WORKSPACE

    # -------------------------------------------------------------------------
    # STEP 1: Security Perimeter Defense
    # -------------------------------------------------------------------------
    print_step(
        "STEP 1: Security & Boundary Rejections",
        "Attempts to export an external system file outside WORKSPACE.",
    )
    unauthorized = "C:/Windows/System32/drivers/etc/hosts"
    blocked_res = export_video(unauthorized, output_name="malicious_export")
    print(f"  -> External path rejection: {blocked_res}")
    assert "Input video is outside WORKSPACE or does not exist" in blocked_res
    print("  [PASS] External file access cleanly blocked!")

    # -------------------------------------------------------------------------
    # STEP 2: Physical Master Video Generation on Disk
    # -------------------------------------------------------------------------
    print_step(
        "STEP 2: Physical Master Video Generation",
        "Generating a 1280x720 master source video (3.0s, 30 FPS).",
    )
    master_source = workspace / "master_source_16x9.mp4"
    generate_test_video(master_source, title="CLIPAGENT PROJECT SHOWCASE", duration_seconds=3, fps=30)
    print(f"  -> Created Master: {master_source.name} (size: {master_source.stat().st_size:,} bytes)")

    # -------------------------------------------------------------------------
    # STEP 3: High-Quality Master Export with FastStart (+faststart)
    # -------------------------------------------------------------------------
    print_step(
        "STEP 3: High-Quality Master Export (MP4 + FastStart)",
        "Packaging release deliverable with 'high' quality preset and web faststart.",
    )
    export_master_raw = export_video(
        master_source.name,
        output_name="verified_youtube_master",
        preset="high",
        format="mp4",
        faststart=True,
    )
    master_receipt = json.loads(export_master_raw)

    print("  -> Export Receipt:")
    print(f"     Destination:      {master_receipt['export_path']}")
    print(f"     Format:           {master_receipt['format']}")
    print(f"     Preset:           {master_receipt['preset']}")
    print(f"     File Size:        {master_receipt['file_size_human']} ({master_receipt['file_size_bytes']:,} bytes)")
    print(f"     Resolution:       {master_receipt['resolution']}")
    print(f"     Duration:         {master_receipt['duration']}s")
    print(f"     Bitrate:          {master_receipt['bitrate_kbps']} kbps")
    print(f"     FastStart Active: {master_receipt['faststart_enabled']}")

    assert master_receipt["status"] == "success"
    assert master_receipt["faststart_enabled"] is True
    master_file = Path(master_receipt["export_path"])
    assert master_file.exists(), f"Export file missing: {master_file}"
    assert master_file.stat().st_size > 0
    print("  [PASS] High-quality web deliverable successfully packaged with FastStart!")

    # -------------------------------------------------------------------------
    # STEP 4: Social Media Vertical Format Export (TikTok / Reels / Shorts 9:16)
    # -------------------------------------------------------------------------
    print_step(
        "STEP 4: Vertical Format Export (9:16 TikTok / Reels / Shorts)",
        "Reframing 16:9 landscape master to 9:16 vertical video via center crop.",
    )
    export_tiktok_raw = export_video(
        master_source.name,
        output_name="verified_tiktok_vertical",
        aspect_ratio="9:16",
        preset="standard",
    )
    tiktok_receipt = json.loads(export_tiktok_raw)

    print("  -> TikTok / Reels Export Receipt:")
    print(f"     Destination:      {tiktok_receipt['export_path']}")
    print(f"     Aspect Ratio:     {tiktok_receipt['aspect_ratio']}")
    print(f"     Resolution:       {tiktok_receipt['resolution']}")
    print(f"     File Size:        {tiktok_receipt['file_size_human']}")

    assert tiktok_receipt["status"] == "success"
    assert tiktok_receipt["aspect_ratio"] == "9:16"

    # Verify vertical dimensions with independent ruler
    tiktok_file = Path(tiktok_receipt["export_path"])
    assert tiktok_file.exists()
    tiktok_probe = json.loads(inspect_video_duration(str(tiktok_file)))
    # In 9:16 from 720 height, width = 720 * 9/16 = 405 -> 404 or 406 (even)
    print(f"  -> Measured TikTok Resolution: {tiktok_probe['resolution']}")
    w_str, h_str = tiktok_probe["resolution"].split("x")
    assert int(h_str) == 720
    assert 400 <= int(w_str) <= 410  # Vertical phone width
    print("  [PASS] 9:16 vertical crop executed with exact aspect geometry!")

    # -------------------------------------------------------------------------
    # STEP 5: Animated GIF Preview Generation
    # -------------------------------------------------------------------------
    print_step(
        "STEP 5: Animated GIF Preview Generation (2-Pass Palette)",
        "Generating lightweight animated GIF preview with optimized color palette.",
    )
    export_gif_raw = export_video(
        master_source.name,
        output_name="verified_social_preview",
        format="gif",
        fps=12.0,
    )
    gif_receipt = json.loads(export_gif_raw)

    print("  -> GIF Export Receipt:")
    print(f"     Destination:      {gif_receipt['export_path']}")
    print(f"     Format:           {gif_receipt['format']}")
    print(f"     File Size:        {gif_receipt['file_size_human']}")
    print(f"     Duration:         {gif_receipt['duration']}s")
    print(f"     Target FPS:       {gif_receipt['fps']}")

    assert gif_receipt["status"] == "success"
    assert gif_receipt["format"] == "gif"
    gif_file = Path(gif_receipt["export_path"])
    assert gif_file.exists()
    assert gif_file.stat().st_size > 0
    print("  [PASS] Animated GIF preview successfully created and verified!")

    print("\n" + "=" * 75)
    print("  MILESTONE 9 REAL-WORLD VERIFICATION COMPLETE!")
    print(f"  Master Source:    {master_source}")
    print(f"  Export 1 (16:9):  {master_file}")
    print(f"  Export 2 (9:16):  {tiktok_file}")
    print(f"  Export 3 (GIF):   {gif_file}")
    print("  (All deliverables reside safely in temp/exports/ ready for publishing!)")
    print("=" * 75 + "\n")
    return True


if __name__ == "__main__":
    success = run_milestone9_verification()
    sys.exit(0 if success else 1)
