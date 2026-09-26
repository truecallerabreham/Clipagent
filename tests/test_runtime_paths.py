from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

# Ensure workspace root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import runtime_paths


class RuntimePathsTests(unittest.TestCase):
    def test_bundle_root_resolves_to_project_directory(self) -> None:
        root = runtime_paths.get_bundle_root()
        self.assertTrue(root.exists(), "Bundle root must exist.")
        self.assertTrue(root.is_dir(), "Bundle root must be a directory.")
        self.assertEqual(root, PROJECT_ROOT)

    def test_runtime_root_is_writable(self) -> None:
        root = runtime_paths.get_runtime_root()
        self.assertTrue(root.exists(), "Runtime root must exist.")
        self.assertTrue(runtime_paths._can_write(root), "Runtime root must be writable.")

    def test_runtime_paths_helpers_compose_correctly(self) -> None:
        temp_dir = runtime_paths.runtime_path("temp")
        self.assertEqual(temp_dir, runtime_paths.get_runtime_root() / "temp")

        resource_dir = runtime_paths.resource_path("app")
        self.assertEqual(resource_dir, runtime_paths.get_bundle_root() / "app")

    def test_ensure_runtime_dirs_creates_required_directories(self) -> None:
        dirs = runtime_paths.ensure_runtime_dirs()
        for name in ("app_state", "jobs", "logs", "temp", "user_temp", "memory_experience"):
            self.assertIn(name, dirs)
            self.assertTrue(dirs[name].exists(), f"Directory {name} must exist on disk.")

    def test_env_file_quoting_and_unquoting(self) -> None:
        quoted = runtime_paths._quote_env_value("hello world\nline 2")
        unquoted = runtime_paths._unquote_env_value(quoted)
        self.assertEqual(unquoted, "hello world\nline 2")

    def test_configure_runtime_environment_runs_cleanly(self) -> None:
        runtime_paths.configure_runtime_environment()
        self.assertIn("CRAYOTTER_BUNDLE_ROOT", os.environ)
        self.assertIn("CRAYOTTER_RUNTIME_ROOT", os.environ)


if __name__ == "__main__":
    unittest.main()
