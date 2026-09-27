from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from script.tools import _shared
from script.tools.inspect_video_duration import inspect_video_duration


def print_step(title: str) -> None:
    print(f"\n{'=' * 65}")
    print(f"  {title}")
    print(f"{'=' * 65}")


def run_milestone3_verification() -> bool:
    print("\n[CLIPAGENT] Running Real Verification for Milestone 3: The Stopwatch & Ruler")
    print(f"Working Directory: {Path.cwd()}")

    workspace = _shared.WORKSPACE
    workspace.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------------------
    # STEP 1: Security Perimeter Defense
    # -------------------------------------------------------------------------
    print_step("Step 1: Security Perimeter Defense (Reject External & Ghost Files)")
    # Test an unauthorized external file
    with tempfile.TemporaryDirectory() as tmp_dir:
        external_file = Path(tmp_dir) / "sensitive_file.mp4"
        external_file.write_text("fake video content", encoding="utf-8")
        result_ext = inspect_video_duration(str(external_file))
        print(f"  -> Testing external file outside workspace: {external_file}")
        print(f"  -> Response: {result_ext}")
        assert "Inspection failed: File does not exist or is outside WORKSPACE" in result_ext

    # Test a non-existent file inside workspace
    ghost_file = "non_existent_clip_12345.mp4"
    result_ghost = inspect_video_duration(ghost_file)
    print(f"  -> Testing non-existent file: {ghost_file}")
    print(f"  -> Response: {result_ghost}")
    assert "Inspection failed: File does not exist or is outside WORKSPACE" in result_ghost
    print("  [PASS] Perimeter security guard effectively rejects invalid files!")

    # -------------------------------------------------------------------------
    # STEP 2: Multi-Format Path Resolution on Disk
    # -------------------------------------------------------------------------
    print_step("Step 2: Resolving Multiple Path Formats (Filename, Absolute, file:// URI)")
    sample_file = workspace / "sample_inspection_video.mp4"
    sample_file.write_bytes(b"\x00" * 256)

    # Verify resolution with different input formats using mock metadata
    mock_meta = {
        "duration_seconds": 45.67,
        "fps": 30.0,
        "resolution": "1920x1080",
        "width": 1920,
        "height": 1080,
    }

    with patch("script.tools.inspect_video_duration._get_video_meta", return_value=mock_meta):
        # 1. Bare filename format
        res1 = inspect_video_duration("sample_inspection_video.mp4")
        data1 = json.loads(res1)
        print(f"  -> Bare filename response: duration={data1['duration_seconds']}s, res={data1['resolution']}")
        assert data1["status"] == "success"
        assert data1["duration_seconds"] == 45.67

        # 2. Absolute filesystem path
        res2 = inspect_video_duration(str(sample_file))
        data2 = json.loads(res2)
        print(f"  -> Absolute path response:  duration={data2['duration_seconds']}s, fps={data2['fps']}")
        assert data2["status"] == "success"
        assert data2["width"] == 1920

        # 3. file:// URL format
        res3 = inspect_video_duration(sample_file.as_uri())
        data3 = json.loads(res3)
        print(f"  -> file:// URI response:    duration={data3['duration_seconds']}s, path={data3['path']}")
        assert data3["status"] == "success"
        assert data3["height"] == 1080

    print("  [PASS] All path representations correctly resolve within workspace!")

    # -------------------------------------------------------------------------
    # STEP 3: Agent Self-Healing Error Handling
    # -------------------------------------------------------------------------
    print_step("Step 3: Agent Self-Healing Resilience (Graceful Error Return)")
    with patch("script.tools.inspect_video_duration._get_video_meta") as bad_meta:
        bad_meta.side_effect = RuntimeError("Corrupted MOOV atom in MP4 header")
        error_result = inspect_video_duration("sample_inspection_video.mp4")
        print(f"  -> Simulated engine failure output: {error_result}")
        assert error_result.startswith("Duration inspection error: Corrupted MOOV atom in MP4 header")
        print("  [PASS] Tool returns actionable error string instead of crashing process!")

    # Clean up test file
    sample_file.unlink(missing_ok=True)

    print("\n" + "=" * 65)
    print("  ALL MILESTONE 3 REAL CHECKS PASSED SUCCESSFULLY!")
    print("=" * 65 + "\n")
    return True


if __name__ == "__main__":
    success = run_milestone3_verification()
    sys.exit(0 if success else 1)
