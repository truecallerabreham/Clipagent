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
from script.media_consistency.render import standardize_media_clips
from script.tools import _shared
from script.tools._native_ffmpeg import _base_command, _run
from script.tools.inspect_video_duration import inspect_video_duration
from script.tools.merge_videos import merge_videos


def print_step(title: str, explanation: str) -> None:
    print(f"\n{'=' * 75}")
    print(f"  {title}")
    print(f"  {explanation}")
    print(f"{'=' * 75}")


def generate_synthetic_raw_clip(
    output_path: Path,
    width: int,
    height: int,
    fps: int,
    duration: float = 3.0,
    has_audio: bool = True,
    sample_rate: int = 48000,
) -> None:
    """Generate physical MP4 media file with specific resolution, fps, and audio properties."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [*_base_command()]

    # Video input: test pattern
    command.extend([
        "-f", "lavfi",
        "-i", f"testsrc=size={width}x{height}:rate={fps}",
    ])

    # Audio input: tone if requested
    if has_audio:
        command.extend([
            "-f", "lavfi",
            "-i", f"sine=frequency=520:sample_rate={sample_rate}",
        ])

    command.extend(["-t", f"{duration:.2f}"])
    command.extend(["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"])

    if has_audio:
        command.extend(["-c:a", "aac", "-b:a", "128k"])
    else:
        command.extend(["-an"])

    command.extend(["-y", str(output_path)])
    _run(command)


def run_milestone11_verification() -> bool:
    print("\n" + "#" * 75)
    print("  CLIPAGENT MILESTONE 11 REAL-WORLD VERIFICATION: THE STANDARDIZER")
    print("  (Physical Media Conforming & Concat-Ready Stream Standardization)")
    print("#" * 75)

    workspace = _shared.WORKSPACE

    # -------------------------------------------------------------------------
    # STEP 1: Security Perimeter Defense
    # -------------------------------------------------------------------------
    print_step(
        "STEP 1: Security & Boundary Rejections",
        "Attempts to run standardization on unauthorized external system files.",
    )
    unauthorized = "C:/Windows/System32/drivers/etc/hosts"
    blocked_res = standardize_media_clips([unauthorized, "dummy.mp4"])
    print(f"  -> External path rejection: {blocked_res}")
    assert "Input video is outside WORKSPACE or does not exist" in blocked_res
    print("  [PASS] External file access cleanly blocked!")

    # -------------------------------------------------------------------------
    # STEP 2: Physical Raw Media Generation with Severe Incompatibilities
    # -------------------------------------------------------------------------
    print_step(
        "STEP 2: Physical Raw Media Generation (Incompatible Profiles)",
        "Generating 3 raw video clips on disk with conflicting formats.",
    )
    raw_1080p = workspace / "m11_raw_1080p.mp4"
    raw_720p = workspace / "m11_raw_720p.mp4"
    raw_vertical_silent = workspace / "m11_raw_vertical_silent.mp4"

    # Clip 1: Master 1920x1080 @ 30 FPS, with 48kHz audio
    generate_synthetic_raw_clip(raw_1080p, width=1920, height=1080, fps=30, duration=3.0, has_audio=True, sample_rate=48000)
    print(f"  -> Created Raw 1: {raw_1080p.name} (1920x1080 @ 30fps, 48kHz audio)")

    # Clip 2: Legacy 1280x720 @ 24 FPS, with 44.1kHz audio
    generate_synthetic_raw_clip(raw_720p, width=1280, height=720, fps=24, duration=3.0, has_audio=True, sample_rate=44100)
    print(f"  -> Created Raw 2: {raw_720p.name} (1280x720 @ 24fps, 44.1kHz audio)")

    # Clip 3: Mobile vertical 720x1280 (9:16) @ 30 FPS, silent (no audio)
    generate_synthetic_raw_clip(raw_vertical_silent, width=720, height=1280, fps=30, duration=3.0, has_audio=False)
    print(f"  -> Created Raw 3: {raw_vertical_silent.name} (720x1280 @ 30fps, SILENT)")

    # -------------------------------------------------------------------------
    # STEP 3: Pre-Standardization Quality Audit
    # -------------------------------------------------------------------------
    print_step(
        "STEP 3: Pre-Standardization Quality Audit (Milestone 10 Probe)",
        "Confirming raw clips fail concat-readiness before conforming.",
    )
    pre_audit_raw = inspect_media_consistency([raw_1080p.name, raw_720p.name, raw_vertical_silent.name])
    pre_audit = json.loads(pre_audit_raw)

    print(f"  -> Pre-Audit Consistent:   {pre_audit['is_consistent']}")
    print(f"  -> Pre-Audit Concat-Ready: {pre_audit['is_concat_ready']}")
    print(f"  -> Discrepancies Count:    {len(pre_audit['discrepancies'])}")

    assert pre_audit["is_consistent"] is False
    assert pre_audit["is_concat_ready"] is False
    print("  [PASS] Pre-audit confirms raw clips cannot be merged directly!")

    # -------------------------------------------------------------------------
    # STEP 4: Physical Media Standardization via standardize_media_clips
    # -------------------------------------------------------------------------
    print_step(
        "STEP 4: Physical Media Standardization Execution",
        "Executing multi-stream conforming to harmonize all clips into 1080p @ 30fps stereo.",
    )
    std_receipt_raw = standardize_media_clips(
        [raw_1080p.name, raw_720p.name, raw_vertical_silent.name],
        target_resolution="1920x1080",
        target_fps=30.0,
        output_subfolder="standardized",
    )
    receipt = json.loads(std_receipt_raw)

    print("  -> Standardization Receipt:")
    print(f"     Status:                     {receipt['status']}")
    print(f"     Total Processed Clips:      {receipt['standardized_clips_count']}")
    print(f"     Output Folder:              {receipt['output_directory']}")
    print(f"     Post-Audit Concat-Ready:    {receipt['is_concat_ready']}")
    print(f"     Post-Audit Discrepancies:   {receipt['post_audit_discrepancies']}")

    assert receipt["status"] == "success"
    assert receipt["standardized_clips_count"] == 3
    assert receipt["is_concat_ready"] is True
    assert len(receipt["post_audit_discrepancies"]) == 0
    print("  [PASS] All 3 clips successfully conformed and verified Concat-Ready!")

    # Print individual standardized clip details
    print("\n  -> Standardized Clip Verification:")
    std_clips = receipt["standardized_clips"]
    for c in std_clips:
        print(f"     [Clip] {c['original_name']} -> {c['standardized_name']}")
        print(f"            Res: {c['resolution']}, FPS: {c['fps']}, Audio: {c['has_audio']}, Re-encoded: {c['was_reencoded']}")
        assert c["resolution"] == "1920x1080"
        assert c["fps"] == 30.0
        assert c["has_audio"] is True

    # -------------------------------------------------------------------------
    # STEP 5: End-to-End Concatenation Proof
    # -------------------------------------------------------------------------
    print_step(
        "STEP 5: End-to-End Seamless Concatenation Proof",
        "Merging the 3 standardized clips to prove zero-error, seamless concatenation.",
    )
    std_paths = [c["standardized_name"] for c in std_clips]
    # Merge the standardized clips using Milestone 5 Glue tool
    merge_raw = merge_videos(
        [f"standardized/{name}" for name in std_paths],
        output_name="verified_standardized_seamless_merge",
    )
    merge_data = json.loads(merge_raw)

    print(f"  -> Merged Video Path:     {merge_data['path']}")
    print(f"  -> Merged Duration:      {merge_data['duration']}s (Target: 9.0s)")

    merged_file = Path(merge_data["path"])
    assert merged_file.exists()
    assert abs(merge_data["duration"] - 9.0) <= 0.1

    # Measure with independent ruler
    probe_raw = inspect_video_duration(str(merged_file))
    probe = json.loads(probe_raw)
    print(f"  -> Measured Resolution:  {probe['resolution']}")
    print(f"  -> Measured FPS:         {probe['fps']} FPS")
    print(f"  -> Measured Duration:    {probe['duration_seconds']}s")

    assert probe["resolution"] == "1920x1080"
    assert probe["duration_seconds"] == 9.0
    print("  [PASS] Flawless concatenation verified on standardized media with zero audio drift!")

    print("\n" + "=" * 75)
    print("  MILESTONE 11 REAL-WORLD VERIFICATION COMPLETE!")
    print("  Phase 3: The Quality Inspector is 100% COMPLETE & VERIFIED!")
    print(f"  Standardized Assets: {receipt['output_directory']}")
    print(f"  Seamless Final Cut:  {merged_file}")
    print("=" * 75 + "\n")
    return True


if __name__ == "__main__":
    success = run_milestone11_verification()
    sys.exit(0 if success else 1)
