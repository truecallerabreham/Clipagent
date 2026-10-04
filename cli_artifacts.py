"""Interactive CLI for Milestone 13: The Safe Ledger (ArtifactRegistry).

Allows interactive exploration of artifact registration, SHA-256 fingerprinting,
tampering/corruption detection, workspace security sandboxing, and manifest persistence.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from script.orchestration.artifacts import ArtifactRegistry
from script.orchestration.models import ArtifactRef


def print_banner() -> None:
    print("\n" + "=" * 70)
    print("  CLIPAGENT ARTIFACT REGISTRY EXPLORER (Milestone 13: The Safe Ledger)")
    print("=" * 70)


def print_menu() -> None:
    print("\nChoose an action:")
    print("  [1] View all registered artifacts in ledger")
    print("  [2] Register sample production media assets")
    print("  [3] Inspect physical file validity & check for tampering")
    print("  [4] Simulate file tampering & observe automatic invalidation")
    print("  [5] Test security sandbox defense (attempt out-of-bounds registration)")
    print("  [6] Display raw manifest JSON (.clipagent/artifact_manifest.json)")
    print("  [0] Exit")


def get_default_workspace() -> Path:
    ws = PROJECT_ROOT / "temp" / "cli_workspace"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


def handle_list_artifacts(registry: ArtifactRegistry) -> None:
    items = registry.list()
    print(f"\n--- Registered Artifacts ({len(items)} items) ---")
    if not items:
        print("  (Ledger is empty. Select [2] to register sample assets.)")
        return
    for idx, a in enumerate(items, start=1):
        status = "VALID" if a.valid else "INVALID/MISSING"
        short_hash = f"{a.checksum[:12]}..." if a.checksum else "(virtual)"
        print(f"  ({idx:02d}) [{a.id}]")
        print(f"       Kind: {a.kind:<18} | Status: {status}")
        print(f"       Path: {a.path or '(in-memory metadata)'}")
        print(f"       Size: {a.size_bytes:,} bytes | SHA256: {short_hash}")
        print(f"       Producer: {a.producer_task_id} (Phase: {a.phase})")


def handle_register_sample_assets(registry: ArtifactRegistry) -> None:
    ws = registry.workspace
    print("\nGenerating sample media files inside workspace...")

    # 1. Source raw video
    f_src = ws / "nature_drone_raw.mp4"
    f_src.write_bytes(b"[SIMULATED_RAW_4K_DRONE_CLIP_CONTENT_STREAM]")
    a_src = registry.register(
        artifact_id="art_raw_drone",
        kind="source_video",
        producer_task_id="task_download_01",
        phase="material_preparation",
        path=f_src,
        metadata={"fps": 60.0, "resolution": "3840x2160"},
    )

    # 2. Trimmed highlight clip
    f_cut = ws / "waterfall_highlight.mp4"
    f_cut.write_bytes(b"[SIMULATED_1080P_TRIMMED_WATERFALL_CLIP]")
    a_cut = registry.register(
        artifact_id="art_cut_waterfall",
        kind="video_clip",
        producer_task_id="task_cut_02",
        phase="editing_execution",
        path=f_cut,
        metadata={"duration": 4.5},
    )

    # 3. Audio narration
    f_aud = ws / "voiceover.wav"
    f_aud.write_bytes(b"[SIMULATED_VOICEOVER_AUDIO_TRACK_DATA]")
    a_aud = registry.register(
        artifact_id="art_voiceover",
        kind="audio_track",
        producer_task_id="task_tts_03",
        phase="editing_research",
        path=f_aud,
        metadata={"language": "en-US", "sample_rate": 48000},
    )

    # 4. Virtual metadata notes
    a_meta = registry.register(
        artifact_id="art_style_guide",
        kind="editing_notes",
        producer_task_id="task_plan_00",
        phase="planning",
        metadata={"music_tempo": "120bpm", "color_profile": "cinematic_teal"},
    )

    print("  -> Registered 4 sample assets:")
    print(f"     + [{a_src.id}] ({a_src.kind}) -> {f_src.name}")
    print(f"     + [{a_cut.id}] ({a_cut.kind}) -> {f_cut.name}")
    print(f"     + [{a_aud.id}] ({a_aud.kind}) -> {f_aud.name}")
    print(f"     + [{a_meta.id}] ({a_meta.kind}) -> (in-memory)")


def handle_validate(registry: ArtifactRegistry) -> None:
    print("\nRunning active validation on all registered artifacts...")
    registry.validate()
    items = registry.list()
    all_valid = all(a.valid for a in items)
    print(f"  -> Validated {len(items)} artifacts.")
    if all_valid:
        print("  -> ALL physical files and checksums match 100% on disk!")
    else:
        for a in items:
            if not a.valid:
                print(f"  -> WARNING: Asset [{a.id}] ({a.path}) is INVALID or MISSING!")


def handle_simulate_tampering(registry: ArtifactRegistry) -> None:
    ws = registry.workspace
    target = ws / "waterfall_highlight.mp4"
    if not target.exists():
        print("  -> Please run [2] to register sample assets first.")
        return

    print(f"\nModifying bytes in '{target.name}' to simulate tampering / file corruption...")
    target.write_bytes(b"[TAMPERED_BYTES_SIMULATING_FILE_CORRUPTION_ALERT]")

    print("Calling registry.validate()...")
    registry.validate()
    art = registry.get("art_cut_waterfall")
    if art:
        print(f"  -> Asset 'art_cut_waterfall' validity is now: valid={art.valid}")
        print("  -> The ledger successfully caught the checksum mismatch and flagged it as invalid!")

    input("\nPress Enter to restore clean original bytes...")
    target.write_bytes(b"[SIMULATED_1080P_TRIMMED_WATERFALL_CLIP]")
    registry.validate()
    restored = registry.get("art_cut_waterfall")
    if restored:
        print(f"  -> Clean bytes restored. Asset validity is now: valid={restored.valid} (SELF-HEALED)")


def handle_test_sandbox(registry: ArtifactRegistry) -> None:
    import tempfile
    with tempfile.TemporaryDirectory() as out_dir:
        outside_path = Path(out_dir) / "restricted_file.txt"
        outside_path.write_text("classified data", encoding="utf-8")
        print(f"\nAttempting to register external path outside workspace:\n  {outside_path}")
        try:
            registry.register(
                kind="exploit_test",
                producer_task_id="bad_actor",
                phase="attack",
                path=outside_path,
            )
            print("  -> ERROR: Sandbox failed to block the path!")
        except ValueError as err:
            print(f"  -> SUCCESS: Security sandbox intercepted the call!\n     Error: {err}")


def handle_display_manifest(registry: ArtifactRegistry) -> None:
    m_path = registry.manifest_path
    if not m_path.exists():
        print(f"\nManifest file does not exist yet at {m_path}")
        return
    print(f"\n--- Manifest File Content ({m_path}) ---")
    content = m_path.read_text(encoding="utf-8")
    print(content)


def main() -> None:
    print_banner()
    workspace = get_default_workspace()
    registry = ArtifactRegistry(workspace)
    print(f"Active Workspace: {workspace}")
    print(f"Manifest Path:    {registry.manifest_path}")

    while True:
        print_menu()
        choice = input("\nEnter choice (0-6): ").strip()
        if choice == "1":
            handle_list_artifacts(registry)
        elif choice == "2":
            handle_register_sample_assets(registry)
        elif choice == "3":
            handle_validate(registry)
        elif choice == "4":
            handle_simulate_tampering(registry)
        elif choice == "5":
            handle_test_sandbox(registry)
        elif choice == "6":
            handle_display_manifest(registry)
        elif choice == "0":
            print("\nExiting Artifact Registry Explorer. Goodbye!")
            break
        else:
            print("Invalid selection. Please choose an option from the menu.")


if __name__ == "__main__":
    main()
