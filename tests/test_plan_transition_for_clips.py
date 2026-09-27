from __future__ import annotations

import json
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from script.tools import _shared
from script.tools._native_ffmpeg import VideoProbe
from script.tools.plan_transition_for_clips import (
    _parse_clips_input,
    plan_clip_transitions,
    plan_transition_for_clips,
)


class TestPlanTransitionForClips(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace = _shared.WORKSPACE
        self.clip1 = self.workspace / "test_clip_1.mp4"
        self.clip2 = self.workspace / "test_clip_2.mp4"
        self.clip3 = self.workspace / "test_clip_3.mp4"

        # Create dummy physical files so _resolve_workspace_input_path finds them
        for c in (self.clip1, self.clip2, self.clip3):
            c.write_bytes(b"dummy")

    def tearDown(self) -> None:
        for c in (self.clip1, self.clip2, self.clip3):
            if c.exists():
                c.unlink()

    def test_parse_clips_input_formats(self) -> None:
        # Python list
        self.assertEqual(_parse_clips_input(["a.mp4", "b.mp4"]), ["a.mp4", "b.mp4"])
        # JSON string
        self.assertEqual(_parse_clips_input('["c1.mp4", "c2.mp4"]'), ["c1.mp4", "c2.mp4"])
        # Comma-separated string
        self.assertEqual(_parse_clips_input("clip1.mp4, clip2.mp4, clip3.mp4"), ["clip1.mp4", "clip2.mp4", "clip3.mp4"])
        # Empty inputs
        self.assertEqual(_parse_clips_input([]), [])
        self.assertEqual(_parse_clips_input(""), [])

    def test_outside_workspace_rejection(self) -> None:
        res = plan_transition_for_clips(["C:/Windows/System32/calc.exe", self.clip1.name])
        self.assertIn("Clip is outside WORKSPACE or does not exist", res)

    def test_empty_clips_rejection(self) -> None:
        res = plan_transition_for_clips([])
        self.assertIn("clips list cannot be empty", res)

    @patch("script.tools.plan_transition_for_clips.probe_video")
    def test_single_clip_handling(self, mock_probe: MagicMock) -> None:
        mock_probe.return_value = VideoProbe(
            duration=4.5, width=1280, height=720, fps=30.0, has_audio=True
        )
        res_raw = plan_transition_for_clips([self.clip1.name])
        data = json.loads(res_raw)

        self.assertEqual(data["status"], "success")
        self.assertEqual(data["clip_count"], 1)
        self.assertEqual(data["transition_count"], 0)
        self.assertEqual(data["total_planned_duration"], 4.5)
        self.assertEqual(len(data["transitions"]), 0)

    @patch("script.tools.plan_transition_for_clips.probe_video")
    def test_timeline_math_and_offsets(self, mock_probe: MagicMock) -> None:
        # Setup 3 clips: 4.0s, 5.0s, 6.0s
        mock_probe.side_effect = [
            VideoProbe(duration=4.0, width=1280, height=720, fps=30.0, has_audio=True),
            VideoProbe(duration=5.0, width=1280, height=720, fps=30.0, has_audio=True),
            VideoProbe(duration=6.0, width=1280, height=720, fps=30.0, has_audio=True),
        ]

        res_raw = plan_transition_for_clips(
            [self.clip1.name, self.clip2.name, self.clip3.name],
            style="cinematic",
            default_duration=1.0,
        )
        data = json.loads(res_raw)

        self.assertEqual(data["status"], "success")
        self.assertEqual(data["clip_count"], 3)
        self.assertEqual(data["transition_count"], 2)
        self.assertEqual(data["total_raw_duration"], 15.0)
        # 15.0 - (1.0 + 1.0) = 13.0
        self.assertEqual(data["total_planned_duration"], 13.0)
        self.assertEqual(data["overlap_duration_saved"], 2.0)

        # Verify Transition 0
        t0 = data["transitions"][0]
        self.assertEqual(t0["from_clip"], self.clip1.name)
        self.assertEqual(t0["to_clip"], self.clip2.name)
        self.assertEqual(t0["duration"], 1.0)
        self.assertEqual(t0["timeline_offset"], 3.0)  # 4.0 - 1.0 = 3.0s

        # Verify Transition 1
        t1 = data["transitions"][1]
        self.assertEqual(t1["from_clip"], self.clip2.name)
        self.assertEqual(t1["to_clip"], self.clip3.name)
        self.assertEqual(t1["duration"], 1.0)
        self.assertEqual(t1["timeline_offset"], 7.0)  # (3.0 + 5.0) - 1.0 = 7.0s

        # Verify Clips timeline positions
        c0 = data["clips"][0]
        self.assertEqual(c0["timeline_start"], 0.0)
        self.assertEqual(c0["timeline_end"], 4.0)

        c1 = data["clips"][1]
        self.assertEqual(c1["timeline_start"], 3.0)
        self.assertEqual(c1["timeline_end"], 8.0)

        c2 = data["clips"][2]
        self.assertEqual(c2["timeline_start"], 7.0)
        self.assertEqual(c2["timeline_end"], 13.0)

    @patch("script.tools.plan_transition_for_clips.probe_video")
    def test_auto_adjust_duration_for_short_clips(self, mock_probe: MagicMock) -> None:
        # Clip 1 is 1.0s, Clip 2 is 4.0s. Requested transition is 1.0s.
        # Safe threshold is 45% of min(1.0, 4.0) = 0.45s.
        mock_probe.side_effect = [
            VideoProbe(duration=1.0, width=1280, height=720, fps=30.0, has_audio=True),
            VideoProbe(duration=4.0, width=1280, height=720, fps=30.0, has_audio=True),
        ]

        # With auto_adjust=True: clamps duration and succeeds
        res_raw = plan_transition_for_clips(
            [self.clip1.name, self.clip2.name],
            default_duration=1.0,
            auto_adjust=True,
        )
        data = json.loads(res_raw)
        self.assertEqual(data["status"], "success")
        t0 = data["transitions"][0]
        self.assertTrue(t0["adjusted"])
        self.assertEqual(t0["duration"], 0.45)
        self.assertIn("Clamped to 0.45s", t0["adjustment_reason"])

    @patch("script.tools.plan_transition_for_clips.probe_video")
    def test_strict_mode_rejects_overlength_transition(self, mock_probe: MagicMock) -> None:
        # Clip 1 is 1.0s, Clip 2 is 4.0s. Requested transition is 1.0s.
        mock_probe.side_effect = [
            VideoProbe(duration=1.0, width=1280, height=720, fps=30.0, has_audio=True),
            VideoProbe(duration=4.0, width=1280, height=720, fps=30.0, has_audio=True),
        ]

        # With auto_adjust=False: raises error
        res_raw = plan_transition_for_clips(
            [self.clip1.name, self.clip2.name],
            default_duration=1.0,
            auto_adjust=False,
        )
        self.assertIn("Transition planner error: Transition duration (1.0s) is too long", res_raw)

    @patch("script.tools.plan_transition_for_clips.probe_video")
    def test_diagnostics_detection(self, mock_probe: MagicMock) -> None:
        # Differing resolutions and framerates, and mixed audio
        mock_probe.side_effect = [
            VideoProbe(duration=4.0, width=1920, height=1080, fps=60.0, has_audio=True),
            VideoProbe(duration=4.0, width=1280, height=720, fps=30.0, has_audio=False),
        ]

        res_raw = plan_transition_for_clips([self.clip1.name, self.clip2.name])
        data = json.loads(res_raw)

        diagnostics_str = " ".join(data["diagnostics"])
        self.assertIn("Resolution mismatch", diagnostics_str)
        self.assertIn("Framerate variance", diagnostics_str)
        self.assertIn("Audio mismatch", diagnostics_str)

    @patch("script.tools.plan_transition_for_clips.execute_planned_transitions_native")
    @patch("script.tools.plan_transition_for_clips.probe_video")
    def test_render_video_integration(
        self, mock_probe: MagicMock, mock_execute: MagicMock
    ) -> None:
        mock_probe.side_effect = [
            VideoProbe(duration=3.0, width=1280, height=720, fps=30.0, has_audio=True),
            VideoProbe(duration=3.0, width=1280, height=720, fps=30.0, has_audio=True),
        ]
        mock_execute.return_value = 5.0

        res_raw = plan_transition_for_clips(
            [self.clip1.name, self.clip2.name],
            render_video=True,
            output_name="custom_rendered_sequence",
        )
        data = json.loads(res_raw)
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["rendered_duration"], 5.0)
        self.assertTrue(data["rendered_video_path"].endswith("custom_rendered_sequence.mp4"))
        mock_execute.assert_called_once()


if __name__ == "__main__":
    unittest.main()
