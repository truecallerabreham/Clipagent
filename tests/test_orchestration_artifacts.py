from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import threading
import unittest

from script.orchestration.artifacts import ArtifactRegistry
from script.orchestration.models import ArtifactRef


class TestArtifactRegistry(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)
        self.registry = ArtifactRegistry(self.workspace)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_register_virtual_artifact(self) -> None:
        """Test registration of an artifact without physical disk file (e.g. metadata or memory asset)."""
        artifact = self.registry.register(
            kind="metadata",
            producer_task_id="task_meta_01",
            phase="planning",
            metadata={"source": "user_prompt", "target_seconds": 60},
        )
        self.assertIsInstance(artifact, ArtifactRef)
        self.assertTrue(artifact.valid)
        self.assertEqual(artifact.kind, "metadata")
        self.assertEqual(artifact.size_bytes, 0)
        self.assertEqual(artifact.checksum, "")
        self.assertEqual(artifact.producer_task_id, "task_meta_01")

        # Verify retrieval from registry
        retrieved = self.registry.get(artifact.id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.id, artifact.id)
        self.assertEqual(retrieved.metadata.get("target_seconds"), 60)

    def test_register_physical_file_artifact_with_checksum(self) -> None:
        """Test registration of a physical file, calculating accurate size and SHA-256 checksum."""
        file_path = self.workspace / "intro_cut.mp4"
        file_path.write_bytes(b"Simulated MP4 video bytes for cut 1")

        artifact = self.registry.register(
            artifact_id="art_cut_01",
            kind="video_clip",
            producer_task_id="cut_01",
            phase="editing_execution",
            path=file_path,
            metadata={"duration": 5.0, "fps": 30.0},
        )
        self.assertEqual(artifact.id, "art_cut_01")
        self.assertTrue(artifact.valid)
        self.assertEqual(artifact.size_bytes, file_path.stat().st_size)
        self.assertTrue(len(artifact.checksum) == 64)  # Valid SHA-256 hex string
        self.assertEqual(Path(artifact.path), file_path.resolve())

    def test_security_perimeter_rejection(self) -> None:
        """Checking Mechanism: Reject paths outside allowed workspace roots."""
        outside_dir = tempfile.TemporaryDirectory()
        try:
            outside_file = Path(outside_dir.name) / "secret.txt"
            outside_file.write_text("unauthorized data", encoding="utf-8")

            # Must raise ValueError for paths outside workspace
            with self.assertRaises(ValueError) as ctx:
                self.registry.register(
                    kind="leak",
                    producer_task_id="bad_task",
                    phase="test",
                    path=outside_file,
                )
            self.assertIn("Artifact path is outside allowed workspaces", str(ctx.exception))
        finally:
            outside_dir.cleanup()

    def test_allowed_path_in_user_workspace(self) -> None:
        """Checking Mechanism: Allow paths inside CLIPAGENT_USER_WORKSPACE."""
        user_temp_dir = tempfile.TemporaryDirectory()
        old_env = os.environ.get("CLIPAGENT_USER_WORKSPACE")
        try:
            os.environ["CLIPAGENT_USER_WORKSPACE"] = user_temp_dir.name
            user_file = Path(user_temp_dir.name) / "user_source.mp4"
            user_file.write_bytes(b"User uploaded video raw material")

            artifact = self.registry.register(
                kind="source_video",
                producer_task_id="upload_01",
                phase="material_preparation",
                path=user_file,
            )
            self.assertTrue(artifact.valid)
            self.assertEqual(Path(artifact.path), user_file.resolve())
        finally:
            if old_env is None:
                os.environ.pop("CLIPAGENT_USER_WORKSPACE", None)
            else:
                os.environ["CLIPAGENT_USER_WORKSPACE"] = old_env
            user_temp_dir.cleanup()

    def test_tampering_and_corruption_detection(self) -> None:
        """Checking Mechanism: Auto-invalidate artifacts if file is modified or deleted."""
        file_path = self.workspace / "render.mp4"
        file_path.write_bytes(b"Original clean video file content")

        artifact = self.registry.register(
            artifact_id="art_render_01",
            kind="final_video",
            producer_task_id="export_01",
            phase="export",
            path=file_path,
        )
        self.assertTrue(artifact.valid)

        # Case 1: Tamper with file content (same length change)
        file_path.write_bytes(b"Tampered bad video file content!!")
        self.registry.validate()
        tampered_artifact = self.registry.get("art_render_01")
        self.assertFalse(tampered_artifact.valid)

        # Case 2: Restore valid content
        file_path.write_bytes(b"Original clean video file content")
        self.registry.validate()
        restored_artifact = self.registry.get("art_render_01")
        self.assertTrue(restored_artifact.valid)

        # Case 3: Delete physical file
        file_path.unlink()
        self.registry.validate()
        deleted_artifact = self.registry.get("art_render_01")
        self.assertFalse(deleted_artifact.valid)

    def test_filtering_and_querying(self) -> None:
        """Test listing, filtering by kind, valid_only, and find_by_producer."""
        f1 = self.workspace / "clip1.mp4"
        f1.write_bytes(b"clip 1")
        f2 = self.workspace / "clip2.mp4"
        f2.write_bytes(b"clip 2")
        f3 = self.workspace / "audio.mp3"
        f3.write_bytes(b"audio")

        self.registry.register(kind="video", producer_task_id="task_A", phase="p1", path=f1)
        self.registry.register(kind="video", producer_task_id="task_B", phase="p1", path=f2)
        self.registry.register(kind="audio", producer_task_id="task_B", phase="p1", path=f3)

        # Filter by kind
        video_items = self.registry.list(kind="video")
        self.assertEqual(len(video_items), 2)
        audio_items = self.registry.list(kind="audio")
        self.assertEqual(len(audio_items), 1)

        # Filter by producer
        task_b_items = self.registry.find_by_producer("task_B")
        self.assertEqual(len(task_b_items), 2)

        # Invalidate one file and test valid_only
        f1.unlink()
        valid_videos = self.registry.list(kind="video", valid_only=True)
        self.assertEqual(len(valid_videos), 1)

    def test_concurrent_registrations_preserve_manifest(self) -> None:
        """Checking Mechanism: Concurrency lock resilience across multiple threads."""
        file_count = 10
        barrier = threading.Barrier(file_count)
        errors: list[BaseException] = []

        def worker(index: int) -> None:
            try:
                path = self.workspace / f"threaded_{index}.txt"
                path.write_text(f"thread payload {index}", encoding="utf-8")
                # Each thread creates its own registry instance pointing to the same workspace
                reg = ArtifactRegistry(self.workspace)
                barrier.wait(timeout=5)
                reg.register(
                    artifact_id=f"thread_art_{index}",
                    kind="text_chunk",
                    producer_task_id=f"thread_task_{index}",
                    phase="concurrent_test",
                    path=path,
                )
            except BaseException as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(file_count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        self.assertFalse(errors, f"Thread errors encountered: {errors}")

        # Check manifest file directly on disk
        manifest_file = self.workspace / ".clipagent" / "artifact_manifest.json"
        self.assertTrue(manifest_file.exists())
        payload = json.loads(manifest_file.read_text(encoding="utf-8"))
        saved_ids = {item["id"] for item in payload.get("artifacts", [])}
        expected_ids = {f"thread_art_{i}" for i in range(file_count)}
        self.assertTrue(expected_ids <= saved_ids)

    def test_serialization_and_manifest_reload(self) -> None:
        """Test serialize() dictionary export and reloading from disk."""
        f = self.workspace / "export.mp4"
        f.write_bytes(b"master output")
        art = self.registry.register(kind="master", producer_task_id="t_master", phase="p_final", path=f)

        data = self.registry.serialize()
        self.assertEqual(data["version"], 1)
        self.assertEqual(data["workspace"], str(self.workspace))
        self.assertEqual(len(data["artifacts"]), 1)

        # Fresh registry instance should reload manifest automatically
        fresh_registry = ArtifactRegistry(self.workspace)
        reloaded = fresh_registry.get(art.id)
        self.assertIsNotNone(reloaded)
        self.assertEqual(reloaded.id, art.id)
        self.assertEqual(reloaded.kind, "master")
        self.assertTrue(reloaded.valid)


if __name__ == "__main__":
    unittest.main()
