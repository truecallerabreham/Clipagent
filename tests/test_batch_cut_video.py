from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import script.tools._shared as shared
from script.tools.batch_cut_video import batch_cut_video
from script.tools._native_ffmpeg import VideoProbe


class BatchCutVideoTests(unittest.TestCase):
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

        # Create a mock source video inside workspace
        self.source = self.workspace / "source_lecture.mp4"
        self.source.write_bytes(b"\x00" * 64)

    def tearDown(self) -> None:
        shared.WORKSPACE = self._orig_workspace
        shared.USER_WORKSPACE = self._orig_user_workspace
        self.temp_dir.cleanup()

    def test_missing_or_external_source_rejected(self) -> None:
        res_missing = batch_cut_video("ghost.mp4", [{"start": 1.0, "end": 3.0}])
        self.assertIn("Batch cut error: Input video is outside WORKSPACE or does not exist", res_missing)

        outside_file = Path(self.temp_dir.name) / "external.mp4"
        outside_file.write_bytes(b"\x00" * 32)
        res_outside = batch_cut_video(str(outside_file), [{"start": 1.0, "end": 3.0}])
        self.assertIn("Batch cut error: Input video is outside WORKSPACE or does not exist", res_outside)

    def test_empty_segments_rejected(self) -> None:
        res = batch_cut_video(self.source.name, [])
        self.assertIn("segments list cannot be empty", res)

    @patch("script.tools.batch_cut_video.probe_video")
    def test_invalid_segment_bounds_rejected(self, mock_probe) -> None:
        mock_probe.return_value = VideoProbe(width=1920, height=1080, fps=30.0, duration=60.0, has_audio=True)

        # end <= start
        res1 = batch_cut_video(self.source.name, [{"start": 10.0, "end": 5.0}])
        self.assertIn("end_time (5.0s) must be greater than start_time (10.0s)", res1)

        # start < 0
        res2 = batch_cut_video(self.source.name, [{"start": -2.0, "end": 5.0}])
        self.assertIn("start_time (-2.0s) cannot be negative", res2)

        # end > duration
        res3 = batch_cut_video(self.source.name, [{"start": 10.0, "end": 75.0}])
        self.assertIn("exceeds total source video duration", res3)

    @patch("script.tools.batch_cut_video.cut_video_native")
    @patch("script.tools.batch_cut_video.probe_video")
    def test_successful_batch_cut_with_list(self, mock_probe, mock_cut_native) -> None:
        mock_probe.return_value = VideoProbe(width=1920, height=1080, fps=30.0, duration=100.0, has_audio=True)
        mock_cut_native.side_effect = [15.0, 10.0]

        segments = [
            {"start_time": 5.0, "end_time": 20.0, "output_name": "hook"},
            {"start_time": 30.0, "end_time": 40.0, "output_name": "key_insight"},
        ]

        result_raw = batch_cut_video(self.source.name, segments)
        data = json.loads(result_raw)

        self.assertEqual(data["status"], "success")
        self.assertEqual(data["total_clips"], 2)
        self.assertEqual(len(data["clips"]), 2)
        self.assertEqual(data["clips"][0]["name"], "hook.mp4")
        self.assertEqual(data["clips"][0]["duration"], 15.0)
        self.assertEqual(data["clips"][1]["name"], "key_insight.mp4")
        self.assertEqual(data["clips"][1]["duration"], 10.0)
        self.assertEqual(mock_cut_native.call_count, 2)

    @patch("script.tools.batch_cut_video.cut_video_native")
    @patch("script.tools.batch_cut_video.probe_video")
    def test_successful_batch_cut_with_json_string(self, mock_probe, mock_cut_native) -> None:
        mock_probe.return_value = VideoProbe(width=1920, height=1080, fps=30.0, duration=100.0, has_audio=True)
        mock_cut_native.return_value = 5.0

        json_segments = json.dumps([{"start": 1.0, "end": 6.0, "name": "clip_json"}])
        result_raw = batch_cut_video(self.source.name, json_segments)
        data = json.loads(result_raw)

        self.assertEqual(data["status"], "success")
        self.assertEqual(data["total_clips"], 1)
        self.assertEqual(data["clips"][0]["name"], "clip_json.mp4")


if __name__ == "__main__":
    unittest.main()
