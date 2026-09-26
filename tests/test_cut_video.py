from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import script.tools._shared as shared
from script.tools.cut_video import cut_video


class CutVideoTests(unittest.TestCase):
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
        outside_file = Path(self.temp_dir.name) / "external_source.mp4"
        outside_file.write_text("data", encoding="utf-8")

        result = cut_video(str(outside_file), start_time=0.0, end_time=5.0)
        self.assertIn("剪辑出错: 输入视频不在WORKSPACE或不存在", result)

    def test_nonexistent_file_rejected(self) -> None:
        missing_file = self.workspace / "missing_video.mp4"
        result = cut_video(str(missing_file), start_time=1.0, end_time=4.0)
        self.assertIn("剪辑出错: 输入视频不在WORKSPACE或不存在", result)

    @patch("script.tools.cut_video.cut_video_native")
    def test_cut_video_native_execution_and_default_naming(self, mock_cut_native) -> None:
        mock_cut_native.return_value = 15.0

        source = self.workspace / "source_video.mp4"
        source.write_bytes(b"\x00" * 64)

        result_raw = cut_video(str(source), start_time=10.0, end_time=25.0)
        data = json.loads(result_raw)

        self.assertEqual(data["status"], "success")
        self.assertEqual(data["duration"], 15.0)
        expected_name = "clip_10_25.mp4"
        self.assertTrue(data["path"].endswith(expected_name))
        self.assertEqual(Path(data["path"]).parent, self.workspace)
        mock_cut_native.assert_called_once()

    @patch("script.tools.cut_video.cut_video_native")
    def test_cut_video_custom_output_name_sanitized(self, mock_cut_native) -> None:
        mock_cut_native.return_value = 8.5

        source = self.workspace / "camera_a.mp4"
        source.write_bytes(b"\x00" * 64)

        result_raw = cut_video(
            str(source),
            start_time=2.0,
            end_time=10.5,
            output_name="scene 1: highlight*cut",
        )
        data = json.loads(result_raw)

        self.assertEqual(data["status"], "success")
        self.assertEqual(data["duration"], 8.5)
        out_filename = Path(data["path"]).name
        self.assertNotIn(":", out_filename)
        self.assertNotIn("*", out_filename)
        self.assertTrue(out_filename.endswith(".mp4"))

    @patch("script.tools.cut_video.cut_video_native")
    def test_backend_cut_error_propagated_safely(self, mock_cut_native) -> None:
        mock_cut_native.side_effect = ValueError("invalid cut range 20.000-10.000s")

        source = self.workspace / "sample.mp4"
        source.write_bytes(b"\x00" * 32)

        result = cut_video(str(source), start_time=20.0, end_time=10.0)
        self.assertTrue(result.startswith("剪辑出错: invalid cut range"))

    def test_moviepy_engine_fallback_when_available(self) -> None:
        source = self.workspace / "moviepy_source.mp4"
        source.write_bytes(b"\x00" * 32)

        mock_clip = MagicMock()
        mock_subclip = MagicMock()
        mock_clip.subclipped.return_value = mock_subclip
        mock_clip.__enter__.return_value = mock_clip
        mock_clip.__exit__.return_value = None

        mock_video_file_clip = MagicMock(return_value=mock_clip)

        with patch.dict(
            "sys.modules",
            {"moviepy.video.io.VideoFileClip": MagicMock(VideoFileClip=mock_video_file_clip)},
        ):
            with patch("script.tools.cut_video.native_ffmpeg_enabled", return_value=False):
                result_raw = cut_video(
                    str(source),
                    start_time=5.0,
                    end_time=12.0,
                    output_name="moviepy_clip",
                )
                data = json.loads(result_raw)
                self.assertEqual(data["status"], "success")
                self.assertEqual(data["duration"], 7.0)
                mock_clip.subclipped.assert_called_once_with(5.0, 12.0)
                mock_subclip.write_videofile.assert_called_once()


if __name__ == "__main__":
    unittest.main()
