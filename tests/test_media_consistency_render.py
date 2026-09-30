from __future__ import annotations

import json
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from script.media_consistency.probe import MediaInspection
from script.media_consistency.render import (
    _parse_clips_list,
    _safe_standardized_output_path,
    standardize_media_clips,
    standardize_single_clip,
)
from script.tools import _shared
from script.tools._native_ffmpeg import VideoProbe


class TestMediaConsistencyRender(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace = _shared.WORKSPACE
        self.clip1 = self.workspace / "test_std_src1.mp4"
        self.clip2 = self.workspace / "test_std_src2.mp4"
        self.clip1.write_bytes(b"dummy clip 1")
        self.clip2.write_bytes(b"dummy clip 2")

    def tearDown(self) -> None:
        if self.clip1.exists():
            self.clip1.unlink()
        if self.clip2.exists():
            self.clip2.unlink()
        std_dir = self.workspace / "standardized"
        if std_dir.exists():
            for f in std_dir.iterdir():
                if f.is_file():
                    f.unlink()

    def test_safe_standardized_output_path(self) -> None:
        out = _safe_standardized_output_path("my input! (v1).mp4", prefix="std_01_")
        self.assertTrue(out.name.startswith("std_01_my_input_v1"))
        self.assertTrue(out.name.endswith(".mp4"))
        self.assertEqual(out.parent.name, "standardized")
        self.assertTrue(_shared._is_within_workspace(out))

    def test_parse_clips_list(self) -> None:
        self.assertEqual(_parse_clips_list(["a.mp4", "b.mp4"]), ["a.mp4", "b.mp4"])
        self.assertEqual(_parse_clips_list('["a.mp4", "b.mp4"]'), ["a.mp4", "b.mp4"])
        self.assertEqual(_parse_clips_list("c1.mp4, c2.mp4"), ["c1.mp4", "c2.mp4"])
        self.assertEqual(_parse_clips_list(""), [])
        self.assertEqual(_parse_clips_list([]), [])

    def test_outside_workspace_rejection(self) -> None:
        res = standardize_media_clips(["C:/Windows/System32/cmd.exe", self.clip1.name])
        self.assertIn("Standardizer error: Input video is outside WORKSPACE or does not exist", res)

    def test_empty_input_rejection(self) -> None:
        res = standardize_media_clips([])
        self.assertIn("Standardizer error: video_paths cannot be empty", res)

    @patch("script.media_consistency.render.probe_video")
    def test_identical_clip_fast_copy_without_reencode(self, mock_probe: MagicMock) -> None:
        mock_probe.return_value = VideoProbe(
            width=1920, height=1080, fps=30.0, duration=5.0, has_audio=True
        )
        out_path = self.workspace / "standardized" / "out_fast.mp4"
        recipe = {
            "needs_reencode": False,
            "needs_scale": False,
            "needs_fps_conforming": False,
            "needs_synthetic_audio": False,
        }
        master = {
            "width": 1920,
            "height": 1080,
            "fps": 30.0,
            "sample_rate": 48000,
        }

        info = standardize_single_clip(self.clip1, out_path, recipe, master)
        self.assertFalse(info.was_reencoded)
        self.assertEqual(info.resolution, "1920x1080")
        self.assertTrue(out_path.exists())

    @patch("script.media_consistency.render._run")
    @patch("script.media_consistency.render.probe_video")
    def test_conforming_clip_with_reencode_and_synthetic_audio(
        self, mock_probe: MagicMock, mock_run: MagicMock
    ) -> None:
        mock_probe.return_value = VideoProbe(
            width=1920, height=1080, fps=30.0, duration=4.0, has_audio=True
        )

        def fake_run(cmd):
            out_file = Path(cmd[-1])
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_bytes(b"standardized media")

        mock_run.side_effect = fake_run

        out_path = self.workspace / "standardized" / "out_conformed.mp4"
        recipe = {
            "needs_reencode": True,
            "needs_scale": True,
            "needs_fps_conforming": True,
            "needs_synthetic_audio": True,
            "needs_rotation_fix": False,
        }
        master = {
            "width": 1920,
            "height": 1080,
            "fps": 30.0,
            "sample_rate": 48000,
        }

        info = standardize_single_clip(self.clip1, out_path, recipe, master)
        self.assertTrue(info.was_reencoded)
        self.assertEqual(info.resolution, "1920x1080")
        mock_run.assert_called_once()
        cmd_str = " ".join(mock_run.call_args[0][0])
        self.assertIn("anullsrc", cmd_str)
        self.assertIn("scale=1920:1080", cmd_str)

    @patch("script.media_consistency.render._run")
    @patch("script.media_consistency.render.probe_video")
    @patch("script.media_consistency.render.probe_media_deep")
    def test_batch_standardize_tool_integration(
        self, mock_deep: MagicMock, mock_probe: MagicMock, mock_run: MagicMock
    ) -> None:
        # Pre-probe inspection for clip 1 and clip 2
        mock_deep.side_effect = [
            # Pre-audit clip 1
            MediaInspection(
                file_path=str(self.clip1), file_name=self.clip1.name, file_size_bytes=1000,
                file_size_human="1.00 KB", format_name="mp4", duration=3.0, bitrate_kbps=1000.0,
                has_video=True, has_audio=True, width=1920, height=1080, resolution="1920x1080",
                aspect_ratio="16:9", fps=30.0, is_vfr=False, video_codec="h264", pix_fmt="yuv420p",
                rotation=0, audio_codec="aac", sample_rate=48000, channels=2, channel_layout="stereo",
            ),
            # Pre-audit clip 2 (720p, 24fps)
            MediaInspection(
                file_path=str(self.clip2), file_name=self.clip2.name, file_size_bytes=1000,
                file_size_human="1.00 KB", format_name="mp4", duration=3.0, bitrate_kbps=1000.0,
                has_video=True, has_audio=True, width=1280, height=720, resolution="1280x720",
                aspect_ratio="16:9", fps=24.0, is_vfr=False, video_codec="h264", pix_fmt="yuv420p",
                rotation=0, audio_codec="aac", sample_rate=44100, channels=2, channel_layout="stereo",
            ),
            # Post-audit standardized clip 1
            MediaInspection(
                file_path="std_01.mp4", file_name="std_01.mp4", file_size_bytes=1000,
                file_size_human="1.00 KB", format_name="mp4", duration=3.0, bitrate_kbps=1000.0,
                has_video=True, has_audio=True, width=1920, height=1080, resolution="1920x1080",
                aspect_ratio="16:9", fps=30.0, is_vfr=False, video_codec="h264", pix_fmt="yuv420p",
                rotation=0, audio_codec="aac", sample_rate=48000, channels=2, channel_layout="stereo",
            ),
            # Post-audit standardized clip 2 (now conforming to 1080p, 30fps)
            MediaInspection(
                file_path="std_02.mp4", file_name="std_02.mp4", file_size_bytes=1000,
                file_size_human="1.00 KB", format_name="mp4", duration=3.0, bitrate_kbps=1000.0,
                has_video=True, has_audio=True, width=1920, height=1080, resolution="1920x1080",
                aspect_ratio="16:9", fps=30.0, is_vfr=False, video_codec="h264", pix_fmt="yuv420p",
                rotation=0, audio_codec="aac", sample_rate=48000, channels=2, channel_layout="stereo",
            ),
        ]

        mock_probe.return_value = VideoProbe(
            width=1920, height=1080, fps=30.0, duration=3.0, has_audio=True
        )

        def fake_run(cmd):
            out_file = Path(cmd[-1])
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_bytes(b"data")

        mock_run.side_effect = fake_run

        res_raw = standardize_media_clips([self.clip1.name, self.clip2.name])
        data = json.loads(res_raw)

        self.assertEqual(data["status"], "success")
        self.assertEqual(data["total_input_clips"], 2)
        self.assertEqual(data["standardized_clips_count"], 2)
        self.assertTrue(data["is_concat_ready"])
        self.assertTrue(data["post_audit_consistent"])
        self.assertEqual(len(data["post_audit_discrepancies"]), 0)


if __name__ == "__main__":
    unittest.main()
