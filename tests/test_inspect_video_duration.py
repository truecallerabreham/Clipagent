from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import script.tools._shared as shared
from script.tools.inspect_video_duration import inspect_video_duration


class InspectVideoDurationTests(unittest.TestCase):
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

    def test_file_outside_workspace_rejected(self) -> None:
        outside_file = Path(self.temp_dir.name) / "outside.mp4"
        outside_file.write_text("dummy", encoding="utf-8")

        result = inspect_video_duration(str(outside_file))
        self.assertIn("检测失败: 文件不存在或不在WORKSPACE", result)

    def test_nonexistent_file_rejected(self) -> None:
        ghost_file = self.workspace / "ghost.mp4"
        result = inspect_video_duration(str(ghost_file))
        self.assertIn("检测失败: 文件不存在或不在WORKSPACE", result)

    @patch("script.tools.inspect_video_duration._get_video_meta")
    def test_valid_video_in_workspace_returns_json_metadata(self, mock_get_meta) -> None:
        mock_get_meta.return_value = {
            "duration_seconds": 12.34,
            "fps": 30.0,
            "resolution": "1920x1080",
            "width": 1920,
            "height": 1080,
        }

        test_video = self.workspace / "sample.mp4"
        test_video.write_bytes(b"\x00" * 64)

        result_raw = inspect_video_duration(str(test_video))
        data = json.loads(result_raw)

        self.assertEqual(data["status"], "success")
        self.assertEqual(data["duration_seconds"], 12.34)
        self.assertEqual(data["fps"], 30.0)
        self.assertEqual(data["resolution"], "1920x1080")
        self.assertEqual(data["width"], 1920)
        self.assertEqual(data["height"], 1080)
        self.assertEqual(Path(data["path"]), test_video.resolve())

    @patch("script.tools.inspect_video_duration._get_video_meta")
    def test_file_url_input_resolved(self, mock_get_meta) -> None:
        mock_get_meta.return_value = {
            "duration_seconds": 5.0,
            "fps": 24.0,
            "resolution": "1280x720",
            "width": 1280,
            "height": 720,
        }

        test_video = self.workspace / "clip_a.mp4"
        test_video.write_bytes(b"\x00" * 32)
        url_input = test_video.resolve().as_uri()

        result_raw = inspect_video_duration(url_input)
        data = json.loads(result_raw)

        self.assertEqual(data["status"], "success")
        self.assertEqual(data["duration_seconds"], 5.0)

    @patch("script.tools.inspect_video_duration._get_video_meta")
    def test_error_handling_when_meta_fails(self, mock_get_meta) -> None:
        mock_get_meta.side_effect = RuntimeError("Corrupted video container")

        test_video = self.workspace / "corrupt.mp4"
        test_video.write_bytes(b"\x00" * 16)

        result = inspect_video_duration(str(test_video))
        self.assertTrue(result.startswith("时长检测出错: Corrupted video container"))

    def test_safe_output_video_path(self) -> None:
        safe_path = shared._safe_output_video_path("my/weird*name??clip.mov")
        self.assertEqual(safe_path.suffix, ".mp4")
        self.assertEqual(safe_path.parent, self.workspace)
        self.assertNotIn("?", safe_path.name)
        self.assertNotIn("*", safe_path.name)


if __name__ == "__main__":
    unittest.main()
