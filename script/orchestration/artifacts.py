from __future__ import annotations

# Standard library imports for hashing, serialization, process/thread coordination, and filesystem handling
import hashlib  # Provides SHA-256 cryptographic hashing for file checksum integrity
import json  # Provides JSON encoding and decoding for manifest persistence
import os  # Provides operating system level atomic file replacement and process ID lookup
import threading  # Provides reentrant locks (RLock) and thread ID lookup for concurrency
import time  # Provides sleep delay for exponential backoff during file contention
import uuid  # Provides unique UUID generation for automatic artifact IDs
from pathlib import Path  # Provides object-oriented, cross-platform filesystem paths
from typing import Any  # Provides flexible typing for metadata and return dictionaries

# Import Pydantic models and timestamp utilities from Milestone 12 models.py
from .models import ArtifactRef, utc_now_iso

# ==============================================================================
# MILESTONE 13: THE SAFE LEDGER (orchestration/artifacts.py)
# ==============================================================================
# Major Aim:
#   Serve as the thread-safe, resilient ledger ("the safe ledger") for all media
#   assets generated across the Clipagent pipeline. Provides atomic registration,
#   cryptographic SHA-256 fingerprinting, workspace perimeter security validation,
#   automatic tampering/corruption detection, and Windows-resilient file persistence.
#
# Visual Example Flow:
#   Worker Task (e.g. cut_video)
#         │
#         ▼ Generates "temp/clip_01.mp4" (15.5 MB)
#   registry.register(kind="video_clip", path="temp/clip_01.mp4", producer_task_id="cut_01")
#         │
#         ├──> 1. Security Check: Asserts path is within WORKSPACE or USER_WORKSPACE
#         ├──> 2. Cryptographic Fingerprint: Computes SHA-256 of size + first 1MB chunk
#         ├──> 3. ArtifactRef Creation: Builds immutable metadata record
#         ├──> 4. Thread-Safe Merge: Acquires manifest RLock and merges existing state
#         └──> 5. Atomic Manifest Save: Writes to .tmp file and safely replaces manifest.json
#
# Core Checking & Defense Mechanisms:
#   1. Reentrant Thread Safety: RLock per manifest prevents concurrent write corruption.
#   2. Sandbox Perimeter Defense: Rejects any file path outside registered workspaces.
#   3. Fast Cryptographic Fingerprinting: O(1) SHA-256 verification (size + 1MB buffer).
#   4. Active Corruption Detection: Automatically invalidates missing or altered files.
#   5. Windows File-Lock Resilience: Exponential backoff retries on WinError 5/32/33 locks.
# ==============================================================================


class ArtifactRegistry:
    """Thread-safe, persistent registry managing media artifacts and manifests."""

    # Class-level lock protecting access to the manifest lock registry map
    _locks_guard = threading.RLock()

    # Registry mapping canonical manifest file paths to their respective reentrant locks
    _manifest_locks: dict[str, threading.RLock] = {}

    def __init__(self, workspace: Path, manifest_path: Path | None = None) -> None:
        """Initialize registry anchored to workspace directory and manifest file."""
        # Resolve the root workspace directory into an absolute filesystem path
        self.workspace = workspace.resolve(strict=False)

        # Ensure the root workspace directory exists on disk
        self.workspace.mkdir(parents=True, exist_ok=True)

        # Set manifest path: defaults to .clipagent/artifact_manifest.json inside workspace
        self.manifest_path = manifest_path or (self.workspace / ".clipagent" / "artifact_manifest.json")

        # Ensure the parent directory holding the manifest file exists (.clipagent/)
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)

        # Obtain the canonical reentrant lock dedicated to this specific manifest file
        self._lock = self._lock_for_manifest(self.manifest_path)

        # In-memory dictionary indexing registered ArtifactRef models by artifact ID
        self._artifacts: dict[str, ArtifactRef] = {}

        # Acquire lock to safely load existing manifest records from disk if present
        with self._lock:
            # Load stored artifacts into in-memory dictionary
            self._load()

    def register(
        self,
        *,
        kind: str,
        producer_task_id: str,
        phase: str,
        path: str | Path = "",
        metadata: dict[str, Any] | None = None,
        artifact_id: str | None = None,
    ) -> ArtifactRef:
        """Register a new media asset into the ledger with integrity fingerprinting."""
        # Initialize default empty string for resolved filesystem path
        resolved_path = ""

        # Initialize default size in bytes
        size_bytes = 0

        # Initialize default cryptographic checksum string
        checksum = ""

        # Process file path if provided
        if path:
            # Resolve candidate path to absolute Path representation
            candidate = Path(path).resolve(strict=False)

            # Checking Mechanism: Assert path is strictly inside allowed workspace sandboxes
            self._assert_allowed_path(candidate)

            # Store validated absolute path string
            resolved_path = str(candidate)

            # Check if physical file currently exists on disk
            if candidate.exists() and candidate.is_file():
                # Read filesystem file stat metadata
                stat = candidate.stat()

                # Extract accurate file size in bytes
                size_bytes = stat.st_size

                # Checking Mechanism: Calculate fast cryptographic fingerprint of file
                checksum = self._fingerprint(candidate, stat.st_size)

        # Construct immutable ArtifactRef model instance
        artifact = ArtifactRef(
            # Use provided ID or generate a unique random UUID string
            id=artifact_id or f"artifact_{uuid.uuid4().hex}",
            # Assign asset category kind (e.g., 'source_video', 'audio_track')
            kind=kind,
            # Assign resolved path string
            path=resolved_path,
            # Assign ID of task that produced this asset
            producer_task_id=producer_task_id,
            # Assign workflow phase name
            phase=phase,
            # Copy provided metadata or default to empty dictionary
            metadata=dict(metadata or {}),
            # Record calculated SHA-256 checksum
            checksum=checksum,
            # Record file size in bytes
            size_bytes=size_bytes,
            # Set validity: true if path is empty (virtual artifact) or file exists on disk
            valid=not resolved_path or Path(resolved_path).is_file(),
        )

        # Acquire manifest lock to safely update storage
        with self._lock:
            # Reload from disk merging external updates from other processes
            self._load(merge=True)

            # Insert new artifact into in-memory dictionary
            self._artifacts[artifact.id] = artifact

            # Save full registry atomically to manifest file
            self._save()

        # Return registered ArtifactRef instance
        return artifact

    def get(self, artifact_id: str) -> ArtifactRef | None:
        """Retrieve a deep-copied artifact by ID, re-validating physical file integrity."""
        # Acquire lock to ensure thread safety
        with self._lock:
            # Checking Mechanism: Re-validate all registered artifacts against physical disk
            self.validate()

            # Retrieve artifact from in-memory dictionary
            artifact = self._artifacts.get(artifact_id)

            # Return deep copy of artifact to prevent external mutation, or None if missing
            return artifact.model_copy(deep=True) if artifact is not None else None

    def list(self, *, kind: str | None = None, valid_only: bool = False) -> list[ArtifactRef]:
        """List registered artifacts with optional kind filtering and validity checks."""
        # Acquire lock for thread-safe query
        with self._lock:
            # Checking Mechanism: Validate integrity of all tracked artifacts
            self.validate()

            # Extract list of all artifact models
            items = list(self._artifacts.values())

            # Filter by category kind if requested
            if kind is not None:
                items = [item for item in items if item.kind == kind]

            # Filter by validity status if requested
            if valid_only:
                items = [item for item in items if item.valid]

            # Return deep-copied list of matching ArtifactRef models
            return [item.model_copy(deep=True) for item in items]

    def find_by_producer(self, task_id: str) -> list[ArtifactRef]:
        """Find all artifacts produced by a specific task ID."""
        # Filter list of all artifacts by producer task ID
        return [item for item in self.list() if item.producer_task_id == task_id]

    def validate(self) -> None:
        """Checking Mechanism: Detect missing, modified, or corrupted artifact files on disk."""
        # Track whether any artifact validity state changed
        changed = False

        # Iterate over all registered artifacts
        for artifact in self._artifacts.values():
            # Assume valid by default
            valid = True

            # If artifact has an associated physical path, verify on disk
            if artifact.path:
                # Instantiate Path object
                path = Path(artifact.path)

                # Check 1: File must exist and be a regular file
                valid = path.exists() and path.is_file()

                # Check 2: File size must match recorded size_bytes
                if valid and artifact.size_bytes:
                    valid = path.stat().st_size == artifact.size_bytes

                # Check 3: Cryptographic fingerprint must match recorded checksum
                if valid and artifact.checksum:
                    valid = self._fingerprint(path, path.stat().st_size) == artifact.checksum

            # If computed validity differs from recorded validity, update state
            if artifact.valid != valid:
                # Update validity flag
                artifact.valid = valid

                # Mark that state changed
                changed = True

        # If any validity state changed, persist updated status to manifest
        if changed:
            self._save()

    def serialize(self) -> dict[str, Any]:
        """Export the full ledger as a JSON-serializable dictionary."""
        # Acquire lock for thread-safe serialization
        with self._lock:
            # Re-validate all artifacts prior to serialization
            self.validate()

            # Return standardized manifest dictionary
            return {
                "version": 1,  # Schema format version
                "updated_at": utc_now_iso(),  # Timestamp of current export
                "workspace": str(self.workspace),  # Registered workspace path
                "artifacts": [item.model_dump() for item in self._artifacts.values()],  # Serialized artifacts
            }

    @classmethod
    def _lock_for_manifest(cls, manifest_path: Path) -> threading.RLock:
        """Retrieve or create a canonical reentrant lock for a given manifest file path."""
        # Create normalized lowercase key from absolute manifest path
        key = str(manifest_path.resolve(strict=False)).lower()

        # Synchronize access to class-level lock registry map
        with cls._locks_guard:
            # Check if lock already exists for this path
            lock = cls._manifest_locks.get(key)

            # If not yet registered, create new reentrant lock
            if lock is None:
                lock = threading.RLock()
                cls._manifest_locks[key] = lock

            # Return the canonical lock
            return lock

    def _load(self, *, merge: bool = False) -> None:
        """Load manifest from disk into memory, with optional merge mode."""
        # If manifest file does not exist on disk, return silently
        if not self.manifest_path.exists():
            return

        # Read and parse JSON content safely
        try:
            # Read UTF-8 text and parse JSON dictionary
            payload = json.loads(self.manifest_path.read_text(encoding="utf-8"))

            # If not merging, reset current in-memory artifacts map
            if not merge:
                self._artifacts = {}

            # Iterate over raw artifact dictionary records
            for raw in payload.get("artifacts", []):
                # Validate and construct ArtifactRef Pydantic model
                artifact = ArtifactRef.model_validate(raw)

                # Store artifact in in-memory dictionary
                self._artifacts[artifact.id] = artifact

            # Run physical validation check on loaded artifacts
            self.validate()

        except Exception:
            # Reset in-memory dictionary on parse failure if not merging
            if not merge:
                self._artifacts = {}

    def _save(self) -> None:
        """Checking Mechanism: Atomically save manifest to disk using a unique temporary file."""
        # Prepare structured manifest payload dictionary
        payload = {
            "version": 1,  # Manifest schema version
            "updated_at": utc_now_iso(),  # UTC timestamp of write
            "workspace": str(self.workspace),  # Workspace root
            "artifacts": [item.model_dump() for item in self._artifacts.values()],  # Serialized artifact list
        }

        # Create unique temporary filename using PID and thread ID to prevent collisions
        temp_path = self.manifest_path.with_name(
            f".{self.manifest_path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
        )

        # Write JSON payload to temporary file with UTF-8 encoding
        temp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # Replace target manifest atomically with exponential backoff retry defense
        self._replace_with_retry(temp_path, self.manifest_path)

    @staticmethod
    def _replace_with_retry(temp_path: Path, target_path: Path) -> None:
        """Checking Mechanism: Atomically replace target file with Windows lock defense."""
        # Variable to store last caught OSError
        last_error: OSError | None = None

        # Attempt up to 6 retries with exponential backoff
        for attempt in range(6):
            try:
                # Perform atomic filesystem replace
                os.replace(temp_path, target_path)

                # Return immediately on successful replace
                return

            except OSError as exc:
                # Capture exception
                last_error = exc

                # Check if error is a Windows sharing/access lock violation (WinError 5, 32, 33)
                if getattr(exc, "winerror", None) not in {5, 32, 33} and not isinstance(exc, PermissionError):
                    # Raise immediately for unrecoverable errors
                    raise

                # Sleep with exponential backoff delay before next retry
                time.sleep(0.05 * (2 ** attempt))

        # Clean up temporary file if all retries failed
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass

        # Re-raise final error if replace could not be completed
        if last_error is not None:
            raise last_error

    def _assert_allowed_path(self, path: Path) -> None:
        """Checking Mechanism: Assert that target path resides within allowed workspace roots."""
        # Build list of allowed directories starting with the primary workspace
        allowed = [self.workspace]

        # Check for optional external user workspace environment variable
        user_workspace = os.environ.get("CLIPAGENT_USER_WORKSPACE", "").strip()

        # If configured, append user workspace to allowed directory roots
        if user_workspace:
            allowed.append(Path(user_workspace).resolve(strict=False))

        # Check if target path is relative to any of the allowed workspace roots
        for root in allowed:
            try:
                # If relative_to succeeds, path is within sandbox perimeter
                path.relative_to(root)
                return
            except ValueError:
                # Path is outside this root, try next allowed root
                continue

        # Raise security ValueError if path is outside all allowed workspaces
        raise ValueError(f"Artifact path is outside allowed workspaces: {path}")

    @staticmethod
    def _fingerprint(path: Path, size: int) -> str:
        """Checking Mechanism: Compute fast SHA-256 checksum of file size and first 1MB chunk."""
        # Initialize SHA-256 hash digest
        digest = hashlib.sha256()

        # Update digest with ASCII-encoded file size bytes to detect length truncations
        digest.update(str(size).encode("ascii"))

        # Open file in binary read mode
        with path.open("rb") as handle:
            # Read and hash up to 1MB of file content for fast O(1) integrity check
            digest.update(handle.read(1024 * 1024))

        # Return lowercase hexadecimal checksum string
        return digest.hexdigest()
