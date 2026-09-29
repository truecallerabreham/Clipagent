from __future__ import annotations

import json
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from script.tools import _shared
from script.tools._native_ffmpeg import VideoProbe
from script.tools.export_video import (
    _safe_export_path,
    build_aspect_ratio_filter,
    export_video,
    format_file_size,
)


class TestExportVideo(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace = _shared.WORKSPACE
        self.test_video = self.workspace / "test_source.mp4"
        self.test_video.write_bytes(b"dummy video data")

    def tearDown(self) -> None:
        if self.test_video.exists():
            self.test_video.unlink()
        export_dir = self.workspace / "exports"
        if export_dir.exists():
            for f in export_dir.iterdir():
                if f.is_file():
                    f.unlink()

    def test_format_file_size(self) -> None:
        self.assertEqual(format_file_size(0), "0 B")
        self.assertEqual(format_file_size(1024), "1.00 KB")
        self.assertEqual(format_file_size(1048576), "1.00 MB")
        self.assertEqual(format_file_size(5242880), "5.00 MB")

    def test_safe_export_path_sanitization(self) -> None:
        path = _safe_export_path("My Final Cut! (v1).mp4", format_ext="mp4")
        self.assertTrue(path.name.startswith("My_Final_Cut_v1"))
        self.assertTrue(path.name.endswith(".mp4"))
        self.assertTrue(_shared._is_within_workspace(path))
        self.assertEqual(path.parent.name, "exports")

    def test_safe_export_path_direct_workspace(self) -> None:
        path = _safe_export_path("direct_clip", format_ext="mov", export_subfolder="")
        self.assertEqual(path.name, "direct_clip.mov")
        self.assertEqual(path.parent, self.workspace.resolve())

    def test_build_aspect_ratio_filter(self) -> None:
        probe = VideoProbe(width=1920, height=1080, fps=30.0, duration=10.0, has_audio=True)

        # Source aspect ratio: guarantees even dimensions
        vf_source = build_aspect_ratio_filter(probe, "source")
        self.assertIn("scale=trunc(iw/2)*2:trunc(ih/2)*2", vf_source)

        # 9:16 vertical crop
        vf_vertical = build_aspect_ratio_filter(probe, "9:16")
        self.assertIn("crop='min(iw,ih*9/16)':'min(ih,iw*16/9)'", vf_vertical)

        # 1:1 square crop
        vf_square = build_aspect_ratio_filter(probe, "1:1")
        self.assertIn("crop='min(iw,ih)':'min(iw,ih)'", vf_square)

        # Downscaling constraint for mobile
        vf_mobile = build_aspect_ratio_filter(probe, "source", max_height=720)
        self.assertIn("scale=-2:720", vf_mobile)

    def test_outside_workspace_rejection(self) -> None:
        res = export_video("C:/Windows/System32/notepad.exe")
        self.assertIn("Export error: Input video is outside WORKSPACE or does not exist", res)

    def test_invalid_format_rejection(self) -> None:
        res = export_video(self.test_video.name, format="invalid_ext")
        self.assertIn("Export error: Invalid format", res)

    def test_invalid_aspect_ratio_rejection(self) -> None:
        res = export_video(self.test_video.name, aspect_ratio="4:3_unsupported")
        self.assertIn("Export error: Invalid aspect_ratio", res)

    @patch("script.tools.export_video._run")
    @patch("script.tools.export_video.probe_video")
    def test_successful_video_export(
        self, mock_probe: MagicMock, mock_run: MagicMock
    ) -> None:
        # Source probe and exported probe
        src_probe = VideoProbe(width=1920, height=1080, fps=30.0, duration=10.0, has_audio=True)
        out_probe = VideoProbe(width=1920, height=1080, fps=30.0, duration=10.0, has_audio=True)
        mock_probe.side_effect = [src_probe, out_probe]

        def fake_run(cmd):
            # Create the output file so stat() succeeds
            out_file = Path(cmd[-1])
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_bytes(b"x" * 1048576)  # 1MB file

        mock_run.side_effect = fake_run

        res_raw = export_video(
            self.test_video.name,
            output_name="youtube_master",
            preset="high",
            aspect_ratio="source",
            format="mp4",
            faststart=True,
        )
        data = json.loads(res_raw)

        self.assertEqual(data["status"], "success")
        self.assertEqual(data["export_name"], "youtube_master.mp4")
        self.assertEqual(data["preset"], "high")
        self.assertEqual(data["format"], "mp4")
        self.assertEqual(data["file_size_human"], "1.00 MB")
        self.assertEqual(data["duration"], 10.0)
        self.assertTrue(data["faststart_enabled"])
        mock_run.assert_called_once()

    @patch("script.tools.export_video._run")
    @patch("script.tools.export_video.probe_video")
    def test_gif_export(
        self, mock_probe: MagicMock, mock_run: MagicMock
    ) -> None:
        src_probe = VideoProbe(width=1280, height=720, fps=30.0, duration=4.0, has_audio=False)
        mock_probe.return_value = src_probe

        def fake_run(cmd):
            out_file = Path(cmd[-1])
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_bytes(b"g" * 512000)

        mock_run.side_effect = fake_run

        res_raw = export_video(
            self.test_video.name,
            output_name="preview_animation",
            format="gif",
            fps=12.0,
        )
        data = json.loads(res_raw)

        self.assertEqual(data["status"], "success")
        self.assertEqual(data["format"], "gif")
        self.assertEqual(data["preset"], "gif")
        self.assertEqual(data["export_name"], "preview_animation.gif")
        self.assertFalse(data["has_audio"])
        mock_run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
