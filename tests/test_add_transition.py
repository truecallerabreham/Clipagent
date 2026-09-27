from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import script.tools._shared as shared
from script.tools.add_transition import add_transition, add_transition_native
from script.tools._native_ffmpeg import VideoProbe


class AddTransitionTests(unittest.TestCase):
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

        self.v1 = self.workspace / "clip1.mp4"
        self.v2 = self.workspace / "clip2.mp4"
        self.v1.write_bytes(b"\x00" * 64)
        self.v2.write_bytes(b"\x00" * 64)

    def tearDown(self) -> None:
        shared.WORKSPACE = self._orig_workspace
        shared.USER_WORKSPACE = self._orig_user_workspace
        self.temp_dir.cleanup()

    def test_missing_or_external_videos_rejected(self) -> None:
        res_missing = add_transition("missing.mp4", self.v2.name)
        self.assertIn("Transition error: Video 1 is outside WORKSPACE or does not exist", res_missing)

        outside = Path(self.temp_dir.name) / "outside.mp4"
        outside.write_bytes(b"\x00" * 32)
        res_outside = add_transition(self.v1.name, str(outside))
        self.assertIn("Transition error: Video 2 is outside WORKSPACE or does not exist", res_outside)

    @patch("script.tools.add_transition.probe_video")
    def test_transition_duration_validation(self, mock_probe) -> None:
        mock_probe.side_effect = [
            VideoProbe(width=1280, height=720, fps=30.0, duration=3.0, has_audio=True),
            VideoProbe(width=1280, height=720, fps=30.0, duration=4.0, has_audio=True),
        ]

        out_path = self.workspace / "out.mp4"
        # Transition duration >= video1 duration
        with self.assertRaises(ValueError) as ctx:
            add_transition_native(self.v1, self.v2, out_path, transition_duration=3.5)
        self.assertIn("must be shorter than video1 duration", str(ctx.exception))

    @patch("script.tools.add_transition.add_transition_native")
    def test_successful_transition_json_response(self, mock_native) -> None:
        mock_native.return_value = 6.0  # 3.0s + 4.0s - 1.0s = 6.0s

        res_raw = add_transition(
            self.v1.name,
            self.v2.name,
            transition_type="wipeleft",
            transition_duration=1.0,
            output_name="scene_transition",
        )
        data = json.loads(res_raw)

        self.assertEqual(data["status"], "success")
        self.assertEqual(data["duration"], 6.0)
        self.assertEqual(data["transition"], "wipeleft")
        self.assertEqual(data["transition_duration"], 1.0)
        self.assertTrue(data["path"].endswith("scene_transition.mp4"))
        mock_native.assert_called_once()

    @patch("script.tools.add_transition.add_transition_native")
    def test_custom_output_name_sanitized(self, mock_native) -> None:
        mock_native.return_value = 5.0

        res_raw = add_transition(
            self.v1.name,
            self.v2.name,
            output_name="scene 1 -> 2: cross*fade!",
        )
        data = json.loads(res_raw)
        out_name = Path(data["path"]).name
        self.assertNotIn(":", out_name)
        self.assertNotIn("*", out_name)
        self.assertTrue(out_name.endswith(".mp4"))


if __name__ == "__main__":
    unittest.main()
