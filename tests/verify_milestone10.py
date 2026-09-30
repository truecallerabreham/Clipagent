from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from script.media_consistency.probe import inspect_media_consistency, probe_media_deep
from script.tools import _shared
from script.tools._native_ffmpeg import _base_command, _run


def print_step(title: str, explanation: str) -> None:
    print(f"\n{'=' * 75}")
    print(f"  {title}")
    print(f"  {explanation}")
    print(f"{'=' * 75}")


def generate_synthetic_media_clip(
    output_path: Path,
    width: int,
    height: int,
    fps: int,
    duration: float = 3.0,
    has_audio: bool = True,
    sample_rate: int = 48000,
) -> None:
    """Generate physical MP4 media file with precise resolution, framerate, and audio track via FFmpeg."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [*_base_command()]

    # Video input: test source pattern
    command.extend([
        "-f", "lavfi",
        "-i", f"testsrc=size={width}x{height}:rate={fps}",
    ])

    # Audio input: synthetic tone if requested
    if has_audio:
        command.extend([
            "-f", "lavfi",
            "-i", f"sine=frequency=440:sample_rate={sample_rate}",
        ])

    command.extend(["-t", f"{duration:.2f}"])
    command.extend(["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"])

    if has_audio:
        command.extend(["-c:a", "aac", "-b:a", "128k"])
    else:
        command.extend(["-an"])

    command.extend(["-y", str(output_path)])
    _run(command)


def run_milestone10_verification() -> bool:
    print("\n" + "#" * 75)
    print("  CLIPAGENT MILESTONE 10 REAL-WORLD VERIFICATION: THE VIDEO INSPECTOR")
    print("  (Multi-Stream Forensic Probing, Consistency Audit & Standardization Recipes)")
    print("#" * 75)

    workspace = _shared.WORKSPACE

    # -------------------------------------------------------------------------
    # STEP 1: Security Perimeter Defense
    # -------------------------------------------------------------------------
    print_step(
        "STEP 1: Security & Boundary Rejections",
        "Attempts to run forensic audit on unauthorized system files outside WORKSPACE.",
    )
    unauthorized = "C:/Windows/System32/drivers/etc/hosts"
    blocked_res = inspect_media_consistency([unauthorized, "dummy.mp4"])
    print(f"  -> External path rejection: {blocked_res}")
    assert "Video is outside WORKSPACE or does not exist" in blocked_res
    print("  [PASS] External file inspection cleanly blocked!")

    # -------------------------------------------------------------------------
    # STEP 2: Physical Media Generation with Deliberate Format Mismatches
    # -------------------------------------------------------------------------
    print_step(
        "STEP 2: Physical Media Generation (Mismatched Stream Profiles)",
        "Generating 3 clips on disk with differing resolutions, framerates, and audio.",
    )
    clip_1080p = workspace / "raw_scene_1080p.mp4"
    clip_720p = workspace / "raw_scene_720p.mp4"
    clip_vertical_silent = workspace / "raw_scene_vertical_silent.mp4"

    # Clip 1: Master 1920x1080 @ 30 FPS, with 48kHz audio
    generate_synthetic_media_clip(clip_1080p, width=1920, height=1080, fps=30, duration=3.0, has_audio=True, sample_rate=48000)
    print(f"  -> Created Clip 1: {clip_1080p.name} (1920x1080 @ 30fps, 48kHz audio, {clip_1080p.stat().st_size:,} bytes)")

    # Clip 2: Legacy 1280x720 @ 24 FPS, with 44.1kHz audio
    generate_synthetic_media_clip(clip_720p, width=1280, height=720, fps=24, duration=3.0, has_audio=True, sample_rate=44100)
    print(f"  -> Created Clip 2: {clip_720p.name} (1280x720 @ 24fps, 44.1kHz audio, {clip_720p.stat().st_size:,} bytes)")

    # Clip 3: Mobile 720x1280 (9:16) @ 30 FPS, silent (no audio)
    generate_synthetic_media_clip(clip_vertical_silent, width=720, height=1280, fps=30, duration=3.0, has_audio=False)
    print(f"  -> Created Clip 3: {clip_vertical_silent.name} (720x1280 @ 30fps, silent, {clip_vertical_silent.stat().st_size:,} bytes)")

    # -------------------------------------------------------------------------
    # STEP 3: Deep Single-Clip Forensic Inspection
    # -------------------------------------------------------------------------
    print_step(
        "STEP 3: Forensic Single-Clip Deep Inspection",
        "Inspecting multi-stream properties of physical media files.",
    )
    insp1 = probe_media_deep(clip_1080p)
    print(f"  -> Deep Inspection of {clip_1080p.name}:")
    print(f"     Resolution:   {insp1.resolution} ({insp1.aspect_ratio})")
    print(f"     Frame Rate:   {insp1.fps} FPS (VFR: {insp1.is_vfr})")
    print(f"     Video Codec:  {insp1.video_codec} ({insp1.pix_fmt})")
    print(f"     Audio Codec:  {insp1.audio_codec} ({insp1.sample_rate} Hz, {insp1.channel_layout})")
    print(f"     Bitrate:      {insp1.bitrate_kbps} kbps")

    assert insp1.width == 1920 and insp1.height == 1080
    assert insp1.has_audio is True
    assert insp1.sample_rate == 48000
    print("  [PASS] Stream metadata extracted with forensic accuracy!")

    # -------------------------------------------------------------------------
    # STEP 4: Project-Level Consistency Audit (Discrepancy Engine)
    # -------------------------------------------------------------------------
    print_step(
        "STEP 4: Project-Level Consistency Audit",
        "Scanning the 3 mismatched clips to detect incompatibilities and concat-readiness.",
    )
    report_raw = inspect_media_consistency([
        clip_1080p.name,
        clip_720p.name,
        clip_vertical_silent.name,
    ])
    report = json.loads(report_raw)

    print("  -> Audit Verdict:")
    print(f"     Total Clips:     {report['clip_count']}")
    print(f"     Is Consistent:   {report['is_consistent']}")
    print(f"     Is Concat-Ready: {report['is_concat_ready']}")

    print("\n  -> Detected Discrepancies:")
    for d in report["discrepancies"]:
        print(f"     [!] {d}")

    assert report["is_consistent"] is False
    assert report["is_concat_ready"] is False
    assert len(report["discrepancies"]) >= 3
    print("  [PASS] All format discrepancies correctly flagged!")

    # -------------------------------------------------------------------------
    # STEP 5: Standardization Recipe Verification
    # -------------------------------------------------------------------------
    print_step(
        "STEP 5: Standardization Recipe Analysis",
        "Inspecting the computed conforming recipe for each clip.",
    )
    std = report["recommended_standard"]
    print(f"  -> Recommended Master Target: {std['resolution']} @ {std['fps']} FPS, {std['sample_rate']}Hz {std['channel_layout']}")

    for recipe in report["recipes"]:
        print(f"\n  -> Recipe for {recipe['file_name']}:")
        print(f"     Needs Re-encode:    {recipe['needs_reencode']}")
        print(f"     Needs Scale:        {recipe['needs_scale']}")
        print(f"     Needs FPS Conform:  {recipe['needs_fps_conforming']}")
        print(f"     Synthetic Audio:    {recipe['needs_synthetic_audio']}")
        print(f"     Video Filter:       {recipe['suggested_video_filter']}")
        print(f"     Audio Filter:       {recipe['suggested_audio_filter']}")

    # Verify Clip 1 needs no scaling
    assert report["recipes"][0]["needs_scale"] is False
    # Verify Clip 2 needs scale and fps conforming
    assert report["recipes"][1]["needs_scale"] is True
    assert report["recipes"][1]["needs_fps_conforming"] is True
    # Verify Clip 3 needs synthetic audio
    assert report["recipes"][2]["needs_synthetic_audio"] is True
    assert report["recipes"][2]["needs_scale"] is True
    print("  [PASS] Exact conforming recipes generated for Phase 3 Standardizer!")

    # -------------------------------------------------------------------------
    # STEP 6: Concat-Ready Baseline Verification
    # -------------------------------------------------------------------------
    print_step(
        "STEP 6: Concat-Ready Baseline Check",
        "Verifying that identical clips report 100% consistent and concat-ready.",
    )
    clean_report_raw = inspect_media_consistency([clip_1080p.name, clip_1080p.name])
    clean_report = json.loads(clean_report_raw)

    print(f"  -> Identical Clips Is Consistent:   {clean_report['is_consistent']}")
    print(f"  -> Identical Clips Is Concat-Ready: {clean_report['is_concat_ready']}")
    print(f"  -> Discrepancy Count:               {len(clean_report['discrepancies'])}")

    assert clean_report["is_consistent"] is True
    assert clean_report["is_concat_ready"] is True
    assert len(clean_report["discrepancies"]) == 0
    print("  [PASS] Concat-ready detection verified!")

    print("\n" + "=" * 75)
    print("  MILESTONE 10 REAL-WORLD VERIFICATION COMPLETE!")
    print(f"  Clip 1 (1080p):   {clip_1080p}")
    print(f"  Clip 2 (720p):    {clip_720p}")
    print(f"  Clip 3 (Silent):  {clip_vertical_silent}")
    print("  (Quality Inspector probe is verified and ready for Milestone 11 Standardizer!)")
    print("=" * 75 + "\n")
    return True


if __name__ == "__main__":
    success = run_milestone10_verification()
    sys.exit(0 if success else 1)
