from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import runtime_paths


def print_step(title: str) -> None:
    print(f"\n{'=' * 65}")
    print(f"  {title}")
    print(f"{'=' * 65}")


def run_milestone1_verification() -> bool:
    print("\n[CLIPAGENT] Running Real Verification for Milestone 1: The Folder Map")
    print(f"Working Directory: {Path.cwd()}")

    # -------------------------------------------------------------------------
    # STEP 1: Empirical Write Probe on Real Disk
    # -------------------------------------------------------------------------
    print_step("Step 1: Testing Real Disk Write Probe (_can_write)")
    with tempfile.TemporaryDirectory() as tmp_dir:
        writable_path = Path(tmp_dir)
        can_write_result = runtime_paths._can_write(writable_path)
        print(f"  -> Testing writable directory: {writable_path}")
        print(f"  -> _can_write() result: {can_write_result}")
        assert can_write_result is True, "Expected temp directory to be writable"

    # Also test an impossible path (like non-existent drive Z:\invalid)
    invalid_path = Path("Z:\\non_existent_drive_folder_12345")
    invalid_result = runtime_paths._can_write(invalid_path)
    print(f"  -> Testing invalid non-existent path: {invalid_path}")
    print(f"  -> _can_write() result: {invalid_result}")
    assert invalid_result is False, "Expected non-existent drive path to return False"
    print("  [PASS] Real disk write probe behaves correctly!")

    # -------------------------------------------------------------------------
    # STEP 2: Real Runtime Roots and Directory Creation
    # -------------------------------------------------------------------------
    print_step("Step 2: Resolving Bundle & Runtime Roots and Creating Directories")
    bundle_root = runtime_paths.get_bundle_root()
    runtime_root = runtime_paths.get_runtime_root()
    print(f"  -> Bundle Root (code/assets):  {bundle_root}")
    print(f"  -> Runtime Root (data/temp):  {runtime_root}")

    assert bundle_root.exists(), f"Bundle root does not exist: {bundle_root}"
    assert runtime_root.exists(), f"Runtime root does not exist: {runtime_root}"

    dirs = runtime_paths.ensure_runtime_dirs()
    print(f"  -> Ensuring required runtime directories:")
    for name, path in dirs.items():
        print(f"     - {name:18} -> {path}")
        assert path.exists(), f"Required directory {name} was not created: {path}"
        assert path.is_dir(), f"Expected {path} to be a directory"

    # Real file write test inside runtime temp directory
    test_temp_file = runtime_paths.runtime_path("temp", "milestone1_real_test.txt")
    test_temp_file.write_text("Real filesystem verification test content", encoding="utf-8")
    assert test_temp_file.exists(), "Failed to write real test file into temp directory"
    read_back = test_temp_file.read_text(encoding="utf-8")
    assert read_back == "Real filesystem verification test content"
    test_temp_file.unlink(missing_ok=True)
    print("  [PASS] All runtime directories verified and writable on real disk!")

    # -------------------------------------------------------------------------
    # STEP 3: Real .env File Serialization Lifecycle
    # -------------------------------------------------------------------------
    print_step("Step 3: Real .env Parsing, Quoting, Writing, and Loading")
    test_env_key = "CLIPAGENT_VERIFICATION_TEST_KEY"
    test_env_val = "secret_value_with_newlines\nsecond_line and quotes: \"hello\""

    print(f"  -> Writing test key to runtime .env: {test_env_key}")
    runtime_paths.write_runtime_env_file({test_env_key: test_env_val})

    # Read back directly from disk
    parsed_env = runtime_paths.read_runtime_env_file()
    print(f"  -> Read back from disk successfully. Contains key: {test_env_key in parsed_env}")
    assert parsed_env.get(test_env_key) == test_env_val, (
        f"Value mismatch! Expected {repr(test_env_val)}, got {repr(parsed_env.get(test_env_key))}"
    )

    # Load into os.environ
    runtime_paths.load_runtime_env_file(override=True)
    assert os.environ.get(test_env_key) == test_env_val
    print(f"  -> Verified os.environ[{test_env_key}] == {repr(os.environ.get(test_env_key))}")

    # Clean up test key from .env file and os.environ
    runtime_paths.write_runtime_env_file({test_env_key: None})
    os.environ.pop(test_env_key, None)
    cleaned_env = runtime_paths.read_runtime_env_file()
    assert test_env_key not in cleaned_env, "Failed to clean test key from .env"
    print("  [PASS] Zero-dependency .env lifecycle verified with real disk I/O!")

    # -------------------------------------------------------------------------
    # STEP 4: Real Binary Discovery & Environment Configuration
    # -------------------------------------------------------------------------
    print_step("Step 4: Real Binary Search & Runtime Environment Bootstrap")
    python_binary = runtime_paths.resolve_binary("python", "python3")
    print(f"  -> Resolved system Python binary: {python_binary}")
    assert python_binary is not None, "Failed to resolve system python binary"

    ffmpeg_binary = runtime_paths.resolve_binary("ffmpeg", "ffmpeg.exe")
    print(f"  -> Resolved FFmpeg binary: {ffmpeg_binary}")

    # Run full bootstrap
    runtime_paths.configure_runtime_environment()
    assert "CLIPAGENT_BUNDLE_ROOT" in os.environ
    assert "CLIPAGENT_RUNTIME_ROOT" in os.environ
    print(f"  -> CLIPAGENT_BUNDLE_ROOT:  {os.environ['CLIPAGENT_BUNDLE_ROOT']}")
    print(f"  -> CLIPAGENT_RUNTIME_ROOT: {os.environ['CLIPAGENT_RUNTIME_ROOT']}")
    print("  [PASS] Central runtime bootstrap completed cleanly!")

    print("\n" + "=" * 65)
    print("  ALL MILESTONE 1 REAL CHECKS PASSED SUCCESSFULLY (100% DISK VERIFIED)!")
    print("=" * 65 + "\n")
    return True


if __name__ == "__main__":
    success = run_milestone1_verification()
    sys.exit(0 if success else 1)
