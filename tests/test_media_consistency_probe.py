from __future__ import annotations

import json
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from script.media_consistency.probe import (
    MediaInspection,
    _parse_input_video_list,
    check_media_consistency,
    format_bytes_human,
    inspect_media_consistency,
    math_gcd,
)
from script.tools import _shared


class TestMediaConsistencyProbe(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace = _shared.WORKSPACE
        self.clip1 = self.workspace / "test_probe_1.mp4"
        self.clip2 = self.workspace / "test_probe_2.mp4"
        self.clip1.write_bytes(b"dummy clip 1")
        self.clip2.write_bytes(b"dummy clip 2")

    def tearDown(self) -> None:
        if self.clip1.exists():
            self.clip1.unlink()
        if self.clip2.exists():
            self.clip2.unlink()

    def test_format_bytes_human(self) -> None:
        self.assertEqual(format_bytes_human(0), "0 B")
        self.assertEqual(format_bytes_human(1024), "1.00 KB")
        self.assertEqual(format_bytes_human(1048576), "1.00 MB")
        self.assertEqual(format_bytes_human(1073741824), "1.00 GB")

    def test_math_gcd(self) -> None:
        self.assertEqual(math_gcd(1920, 1080), 120)  # 16:9
        self.assertEqual(math_gcd(1280, 720), 80)    # 16:9
        self.assertEqual(math_gcd(1080, 1920), 120)  # 9:16
        self.assertEqual(math_gcd(1080, 1080), 1080) # 1:1

    def test_parse_input_video_list(self) -> None:
        self.assertEqual(_parse_input_video_list(["a.mp4", "b.mp4"]), ["a.mp4", "b.mp4"])
        self.assertEqual(_parse_input_video_list('["a.mp4", "b.mp4"]'), ["a.mp4", "b.mp4"])
        self.assertEqual(_parse_input_video_list("c1.mp4, c2.mp4"), ["c1.mp4", "c2.mp4"])
        self.assertEqual(_parse_input_video_list(""), [])
        self.assertEqual(_parse_input_video_list([]), [])

    def test_outside_workspace_rejection(self) -> None:
        res = inspect_media_consistency(["C:/Windows/System32/cmd.exe", self.clip1.name])
        self.assertIn("Consistency probe error: Video is outside WORKSPACE or does not exist", res)

    def test_empty_input_rejection(self) -> None:
        res = inspect_media_consistency([])
        self.assertIn("Consistency probe error: video_paths cannot be empty", res)

    def test_perfectly_consistent_clips_are_concat_ready(self) -> None:
        c1 = MediaInspection(
            file_path=str(self.clip1),
            file_name="clip1.mp4",
            file_size_bytes=1000000,
            file_size_human="1.00 MB",
            format_name="mp4",
            duration=5.0,
            bitrate_kbps=1600.0,
            has_video=True,
            has_audio=True,
            width=1920,
            height=1080,
            resolution="1920x1080",
            aspect_ratio="16:9",
            fps=30.0,
            is_vfr=False,
            video_codec="h264",
            pix_fmt="yuv420p",
            rotation=0,
            audio_codec="aac",
            sample_rate=48000,
            channels=2,
            channel_layout="stereo",
        )
        c2 = MediaInspection(
            file_path=str(self.clip2),
            file_name="clip2.mp4",
            file_size_bytes=1000000,
            file_size_human="1.00 MB",
            format_name="mp4",
            duration=6.0,
            bitrate_kbps=1600.0,
            has_video=True,
            has_audio=True,
            width=1920,
            height=1080,
            resolution="1920x1080",
            aspect_ratio="16:9",
            fps=30.0,
            is_vfr=False,
            video_codec="h264",
            pix_fmt="yuv420p",
            rotation=0,
            audio_codec="aac",
            sample_rate=48000,
            channels=2,
            channel_layout="stereo",
        )

        report = check_media_consistency([c1, c2])
        self.assertTrue(report["is_consistent"])
        self.assertTrue(report["is_concat_ready"])
        self.assertEqual(len(report["discrepancies"]), 0)
        self.assertFalse(report["recipes"][0]["needs_reencode"])
        self.assertFalse(report["recipes"][1]["needs_reencode"])

    def test_mismatched_clips_generate_discrepancies_and_recipes(self) -> None:
        c1 = MediaInspection(
            file_path=str(self.clip1),
            file_name="master.mp4",
            file_size_bytes=2000000,
            file_size_human="2.00 MB",
            format_name="mp4",
            duration=5.0,
            bitrate_kbps=3200.0,
            has_video=True,
            has_audio=True,
            width=1920,
            height=1080,
            resolution="1920x1080",
            aspect_ratio="16:9",
            fps=60.0,
            is_vfr=False,
            video_codec="h264",
            pix_fmt="yuv420p",
            rotation=0,
            audio_codec="aac",
            sample_rate=48000,
            channels=2,
            channel_layout="stereo",
        )
        c2 = MediaInspection(
            file_path=str(self.clip2),
            file_name="legacy.mp4",
            file_size_bytes=1000000,
            file_size_human="1.00 MB",
            format_name="mp4",
            duration=4.0,
            bitrate_kbps=1500.0,
            has_video=True,
            has_audio=True,
            width=1280,
            height=720,
            resolution="1280x720",
            aspect_ratio="16:9",
            fps=24.0,
            is_vfr=False,
            video_codec="h264",
            pix_fmt="yuv420p",
            rotation=0,
            audio_codec="aac",
            sample_rate=44100,
            channels=1,
            channel_layout="mono",
        )

        report = check_media_consistency([c1, c2])
        self.assertFalse(report["is_consistent"])
        self.assertFalse(report["is_concat_ready"])

        discrepancies_text = " ".join(report["discrepancies"])
        self.assertIn("Resolution mismatch", discrepancies_text)
        self.assertIn("Framerate variance", discrepancies_text)
        self.assertIn("Audio sample rate mismatch", discrepancies_text)
        self.assertIn("Audio channel layout mismatch", discrepancies_text)

        # Standard should be 1920x1080 @ 60fps
        std = report["recommended_standard"]
        self.assertEqual(std["resolution"], "1920x1080")
        self.assertEqual(std["fps"], 60.0)
        self.assertEqual(std["sample_rate"], 48000)
        self.assertEqual(std["channels"], 2)

        # Legacy clip recipe
        recipe2 = report["recipes"][1]
        self.assertTrue(recipe2["needs_reencode"])
        self.assertTrue(recipe2["needs_scale"])
        self.assertTrue(recipe2["needs_fps_conforming"])
        self.assertTrue(recipe2["needs_audio_resample"])
        self.assertTrue(recipe2["needs_audio_channel_conforming"])
        self.assertIn("scale=1920:1080", recipe2["suggested_video_filter"])
        self.assertIn("fps=60.00", recipe2["suggested_video_filter"])
        self.assertIn("sample_rates=48000", recipe2["suggested_audio_filter"])

    def test_silent_clip_and_rotation_detection(self) -> None:
        c1 = MediaInspection(
            file_path=str(self.clip1),
            file_name="clip1.mp4",
            file_size_bytes=1000000,
            file_size_human="1.00 MB",
            format_name="mp4",
            duration=3.0,
            bitrate_kbps=1000.0,
            has_video=True,
            has_audio=True,
            width=1920,
            height=1080,
            resolution="1920x1080",
            aspect_ratio="16:9",
            fps=30.0,
            is_vfr=False,
            video_codec="h264",
            pix_fmt="yuv420p",
            rotation=0,
            audio_codec="aac",
            sample_rate=48000,
            channels=2,
            channel_layout="stereo",
        )
        c2 = MediaInspection(
            file_path=str(self.clip2),
            file_name="mobile_silent.mp4",
            file_size_bytes=1000000,
            file_size_human="1.00 MB",
            format_name="mp4",
            duration=3.0,
            bitrate_kbps=1000.0,
            has_video=True,
            has_audio=False,  # Silent!
            width=1920,
            height=1080,
            resolution="1920x1080",
            aspect_ratio="16:9",
            fps=30.0,
            is_vfr=False,
            video_codec="h264",
            pix_fmt="yuv420p",
            rotation=90,  # Rotated!
            audio_codec="",
            sample_rate=0,
            channels=0,
            channel_layout="",
        )

        report = check_media_consistency([c1, c2])
        discrepancies_text = " ".join(report["discrepancies"])
        self.assertIn("Audio presence asymmetry", discrepancies_text)
        self.assertIn("Display rotation detected", discrepancies_text)

        recipe2 = report["recipes"][1]
        self.assertTrue(recipe2["needs_rotation_fix"])
        self.assertTrue(recipe2["needs_synthetic_audio"])
        self.assertIn("transpose=1", recipe2["suggested_video_filter"])

    @patch("script.media_consistency.probe.probe_media_deep")
    def test_inspect_media_consistency_tool(self, mock_probe: MagicMock) -> None:
        mock_probe.return_value = MediaInspection(
            file_path=str(self.clip1),
            file_name="clip1.mp4",
            file_size_bytes=1000000,
            file_size_human="1.00 MB",
            format_name="mp4",
            duration=5.0,
            bitrate_kbps=1600.0,
            has_video=True,
            has_audio=True,
            width=1920,
            height=1080,
            resolution="1920x1080",
            aspect_ratio="16:9",
            fps=30.0,
            is_vfr=False,
            video_codec="h264",
            pix_fmt="yuv420p",
            rotation=0,
            audio_codec="aac",
            sample_rate=48000,
            channels=2,
            channel_layout="stereo",
        )

        res_raw = inspect_media_consistency([self.clip1.name])
        data = json.loads(res_raw)
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["clip_count"], 1)
        self.assertTrue(data["is_concat_ready"])
        mock_probe.assert_called_once()


if __name__ == "__main__":
    unittest.main()
