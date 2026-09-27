from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import script.tools._shared as shared
from script.tools.merge_videos import merge_videos


class MergeVideosTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name) / "workspace"
        self.user_workspace = Path(self.temp_dir.name) / "user_workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.user_workspace.mkdir(parents=True, exist_ok=True)

        self._orig_workspace = shared.WORKSPACE
        self._orig_user_workspace = shared.USER_WORKSPACE
        shared.WORKSPACE = self.workspace
        shared.USER_WORKSPACE = self.user_workspace

    def tearDown(self) -> None:
        shared.WORKSPACE = self._orig_workspace
        shared.USER_WORKSPACE = self._orig_user_workspace
        self.temp_dir.cleanup()

    def test_empty_or_invalid_list_rejected(self) -> None:
        result_empty = merge_videos([])
        self.assertIn("video_paths must be a non-empty list", result_empty)

        result_single = merge_videos(["clip1.mp4"])
        self.assertIn("At least 2 videos are required", result_single)

    def test_file_outside_workspace_rejected(self) -> None:
        outside_file = Path(self.temp_dir.name) / "external_source.mp4"
        outside_file.write_text("data", encoding="utf-8")
        valid_file = self.workspace / "valid.mp4"
        valid_file.write_bytes(b"\x00" * 32)

        result = merge_videos([str(valid_file), str(outside_file)])
        self.assertIn("Merge error: Input video is outside WORKSPACE or does not exist", result)

    def test_nonexistent_file_rejected(self) -> None:
        valid_file = self.workspace / "clip1.mp4"
        valid_file.write_bytes(b"\x00" * 32)
        missing_file = self.workspace / "missing.mp4"

        result = merge_videos([str(valid_file), str(missing_file)])
        self.assertIn("Merge error: Input video is outside WORKSPACE or does not exist", result)

    @patch("script.tools.merge_videos.merge_videos_native")
    def test_successful_native_merge(self, mock_merge_native) -> None:
        mock_merge_native.return_value = (15.5, 2, (1920, 1080))

        c1 = self.workspace / "c1.mp4"
        c2 = self.workspace / "c2.mp4"
        c1.write_bytes(b"\x00" * 32)
        c2.write_bytes(b"\x00" * 32)

        result_raw = merge_videos([c1.name, c2.name], output_name="my_compilation")
        data = json.loads(result_raw)

        self.assertEqual(data["status"], "success")
        self.assertEqual(data["duration"], 15.5)
        self.assertEqual(data["clip_count"], 2)
        self.assertEqual(data["resolution"], "1920x1080")
        self.assertTrue(data["path"].endswith("my_compilation.mp4"))
        mock_merge_native.assert_called_once()

    @patch("script.tools.merge_videos.merge_videos_native")
    def test_custom_output_name_sanitized(self, mock_merge_native) -> None:
        mock_merge_native.return_value = (10.0, 2, (1280, 720))

        c1 = self.workspace / "part1.mp4"
        c2 = self.workspace / "part2.mp4"
        c1.write_bytes(b"\x00" * 32)
        c2.write_bytes(b"\x00" * 32)

        result_raw = merge_videos([c1.name, c2.name], output_name="scene 1: combined*final")
        data = json.loads(result_raw)

        out_name = Path(data["path"]).name
        self.assertNotIn(":", out_name)
        self.assertNotIn("*", out_name)
        self.assertTrue(out_name.endswith(".mp4"))


if __name__ == "__main__":
    unittest.main()
