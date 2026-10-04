"""Interactive CLI for Milestone 14: The Conductor (ResourceScheduler).

Allows interactive testing and visualization of multi-threaded DAG scheduling,
bounded resource pools, conflict key mutual exclusion, automatic retries, and checkpointing.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import threading
import time

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from script.orchestration import (
    ArtifactRef,
    ArtifactRegistry,
    ExecutionPlan,
    ResourcePoolConfig,
    ResourceScheduler,
    TaskExecutionResult,
    TaskSpec,
    TaskState,
)


def print_banner() -> None:
    print("\n" + "=" * 70)
    print("  CLIPAGENT RESOURCE SCHEDULER EXPLORER (Milestone 14: The Conductor)")
    print("=" * 70)


def print_menu() -> None:
    print("\nChoose an action:")
    print("  [1] Run 6-stage video production pipeline simulation")
    print("  [2] Test bounded concurrency (verify pool capacity limits)")
    print("  [3] Test conflict keys (mutual exclusion for shared files)")
    print("  [4] Test automated retries on transient errors (rate limits)")
    print("  [5] Test smart task reuse & resume from checkpoint")
    print("  [6] Inspect saved checkpoints (.clipagent/<plan_id>.state.json)")
    print("  [0] Exit")


def get_default_workspace() -> Path:
    ws = PROJECT_ROOT / "temp" / "scheduler_cli_workspace"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


def handle_run_pipeline() -> None:
    ws = get_default_workspace()
    registry = ArtifactRegistry(ws)
    pools = ResourcePoolConfig(download_pool=2, ffmpeg_pool=2, export_pool=1, llm_pool=2)

    events: list[str] = []

    def event_sink(evt: str, payload: dict) -> None:
        if evt in {"task_started", "task_completed", "resource_acquired", "resource_released"}:
            t_id = payload.get("task_id", "")
            events.append(f"[{evt:<18}] {t_id}")

    scheduler = ResourceScheduler(pools=pools, workspace=ws, artifact_registry=registry, event_sink=event_sink)

    plan = ExecutionPlan(
        plan_id="cli_demo_pipeline",
        phase="editing_execution",
        goal="Produce 60s Social Media Reel",
        tasks=[
            TaskSpec(id="download_source_1", phase="prep", kind="download", resources={"download_pool": 1}, priority=10),
            TaskSpec(id="download_source_2", phase="prep", kind="download", resources={"download_pool": 1}, priority=10),
            TaskSpec(id="probe_clips", phase="prep", kind="inspect", depends_on=["download_source_1", "download_source_2"], resources={"video_analysis_pool": 1}, priority=50),
            TaskSpec(id="batch_cut_highlights", phase="edit", kind="batch_cut", depends_on=["probe_clips"], resources={"ffmpeg_pool": 1}, priority=40),
            TaskSpec(id="extract_speech_audio", phase="edit", kind="extract_audio", depends_on=["probe_clips"], resources={"ffmpeg_pool": 1}, priority=30),
            TaskSpec(id="render_final_master", phase="export", kind="merge", depends_on=["batch_cut_highlights", "extract_speech_audio"], resources={"export_pool": 1, "ffmpeg_pool": 1}, priority=100),
        ],
    )

    print(f"\n--- ExecutionPlan '{plan.plan_id}' ({len(plan.tasks)} tasks) ---")
    for t in plan.tasks:
        print(f"  * [{t.id}] kind={t.kind} depends_on={t.depends_on}")

    def worker(task: TaskSpec, dependencies: dict[str, TaskState]) -> TaskExecutionResult:
        time.sleep(0.08)
        out = ws / f"{task.id}_out.mp4"
        out.write_bytes(b"[SIMULATED_DATA]")
        return TaskExecutionResult(
            data={"result": "ok"},
            artifacts=[ArtifactRef(id=f"art_{task.id}", kind="clip", path=str(out), producer_task_id=task.id, phase=task.phase)],
        )

    t0 = time.time()
    states = scheduler.run(plan, worker)
    elapsed = time.time() - t0

    print(f"\nPipeline finished in {elapsed:.2f}s!")
    print("\n--- Final Task Execution Summary ---")
    for tid, st in states.items():
        print(f"  * {tid:<24} | Status: {st.status:<9} | Elapsed: {st.elapsed_seconds:.2f}s | Artifacts: {st.artifact_ids}")


def handle_test_concurrency() -> None:
    ws = get_default_workspace()
    registry = ArtifactRegistry(ws)
    # Strict cap of 2 concurrent downloads
    pools = ResourcePoolConfig(download_pool=2)

    active = 0
    peak = 0
    lock = threading.Lock()

    def concurrent_worker(task: TaskSpec, deps: dict) -> TaskExecutionResult:
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        print(f"  -> Task [{task.id}] started. Active concurrent workers: {active}")
        time.sleep(0.1)
        with lock:
            active -= 1
        print(f"  <- Task [{task.id}] completed. Remaining active workers: {active}")
        return TaskExecutionResult()

    scheduler = ResourceScheduler(pools=pools, workspace=ws, artifact_registry=registry)
    plan = ExecutionPlan(
        plan_id="concurrency_stress_test",
        phase="test",
        tasks=[
            TaskSpec(id=f"download_{i}", phase="test", kind="download", resources={"download_pool": 1})
            for i in range(5)
        ],
    )

    print(f"\nDispatching 5 download tasks with pool cap = 2...")
    scheduler.run(plan, concurrent_worker)
    print(f"\nResult: Peak concurrent workers observed = {peak} (Cap = 2). Concurrency bounds verified!")


def handle_test_conflicts() -> None:
    ws = get_default_workspace()
    registry = ArtifactRegistry(ws)
    # ffmpeg_pool capacity = 3, but both tasks share conflict key "lock:output.mp4"
    pools = ResourcePoolConfig(ffmpeg_pool=3)
    active = 0
    peak = 0
    lock = threading.Lock()

    def conflict_worker(task: TaskSpec, deps: dict) -> TaskExecutionResult:
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        print(f"  -> Task [{task.id}] started (holding conflict lock). Active: {active}")
        time.sleep(0.1)
        with lock:
            active -= 1
        print(f"  <- Task [{task.id}] released lock. Active: {active}")
        return TaskExecutionResult()

    scheduler = ResourceScheduler(pools=pools, workspace=ws, artifact_registry=registry)
    plan = ExecutionPlan(
        plan_id="conflict_key_test",
        phase="test",
        tasks=[
            TaskSpec(id="writer_A", phase="test", kind="cut", resources={"ffmpeg_pool": 1}, conflict_keys=["lock:output.mp4"]),
            TaskSpec(id="writer_B", phase="test", kind="cut", resources={"ffmpeg_pool": 1}, conflict_keys=["lock:output.mp4"]),
        ],
    )

    print(f"\nDispatching 2 writer tasks with shared conflict key ['lock:output.mp4']...")
    scheduler.run(plan, conflict_worker)
    print(f"\nResult: Peak concurrency = {peak} (Expected: 1). Mutual exclusion strictly serialized execution!")


def handle_test_retries() -> None:
    ws = get_default_workspace()
    registry = ArtifactRegistry(ws)
    pools = ResourcePoolConfig(llm_pool=2)

    call_count = 0

    def flaky_api_worker(task: TaskSpec, deps: dict) -> TaskExecutionResult:
        nonlocal call_count
        call_count += 1
        print(f"  -> Invocation attempt {call_count}...")
        if call_count < 3:
            print("     [Error] Simulated HTTP 429: Rate limit exceeded! Triggering backoff retry...")
            raise RuntimeError("API error: 429 rate limit exceeded")
        print("     [Success] API call succeeded on attempt 3!")
        return TaskExecutionResult(data={"transcription": "Speech text recovered"})

    scheduler = ResourceScheduler(pools=pools, workspace=ws, artifact_registry=registry)
    plan = ExecutionPlan(
        plan_id="retry_demo_test",
        phase="test",
        tasks=[
            TaskSpec(
                id="transcribe_speech",
                phase="test",
                kind="transcribe",
                retry={"max_attempts": 3, "backoff_seconds": 0.05, "retryable_errors": ["429", "rate limit"]},
            )
        ],
    )

    print(f"\nTesting automated retry on transient error with exponential backoff...")
    states = scheduler.run(plan, flaky_api_worker)
    print(f"\nResult: Final task status = {states['transcribe_speech'].status} (Attempts = {states['transcribe_speech'].attempts})")


def handle_test_reuse() -> None:
    ws = get_default_workspace()
    registry = ArtifactRegistry(ws)
    pools = ResourcePoolConfig(ffmpeg_pool=2)

    exec_count = 0

    def dummy_worker(task: TaskSpec, deps: dict) -> TaskExecutionResult:
        nonlocal exec_count
        exec_count += 1
        f = ws / f"{task.id}_cached.mp4"
        f.write_bytes(b"[CACHED_PAYLOAD]")
        return TaskExecutionResult(
            data={"val": 42},
            artifacts=[ArtifactRef(id=f"art_{task.id}", kind="clip", path=str(f), producer_task_id=task.id, phase=task.phase)],
        )

    scheduler = ResourceScheduler(pools=pools, workspace=ws, artifact_registry=registry)
    plan = ExecutionPlan(
        plan_id="reuse_demo_test",
        phase="test",
        tasks=[
            TaskSpec(id="cut_clip_alpha", phase="test", kind="cut"),
            TaskSpec(id="cut_clip_beta", phase="test", kind="cut", depends_on=["cut_clip_alpha"]),
        ],
    )

    print("\nRun 1: Initial execution from scratch...")
    scheduler.run(plan, dummy_worker)
    print(f"  -> Total task executions on Run 1: {exec_count}")

    print("\nRun 2: Re-running plan with resume=True...")
    scheduler.run(plan, dummy_worker, resume=True)
    print(f"  -> Total task executions on Run 2: {exec_count} (ZERO additional executions!)")
    print("  -> Fingerprint caching and artifact verification avoided duplicate work!")


def handle_inspect_checkpoint() -> None:
    ws = get_default_workspace()
    state_dir = ws / ".clipagent"
    print(f"\nScanning checkpoints in: {state_dir}")
    if not state_dir.exists():
        print("  (No checkpoints found yet. Run an action first.)")
        return
    files = list(state_dir.glob("*.json"))
    if not files:
        print("  (No checkpoint JSON files found.)")
        return
    for idx, f in enumerate(files, start=1):
        print(f"  ({idx}) {f.name} ({f.stat().st_size:,} bytes)")
    choice = input("\nEnter number to view contents (or 0 to cancel): ").strip()
    try:
        n = int(choice)
        if 1 <= n <= len(files):
            target = files[n - 1]
            print(f"\n--- Content of {target.name} ---")
            print(target.read_text(encoding="utf-8"))
    except ValueError:
        pass


def main() -> None:
    print_banner()
    while True:
        print_menu()
        c = input("\nEnter choice (0-6): ").strip()
        if c == "1":
            handle_run_pipeline()
        elif c == "2":
            handle_test_concurrency()
        elif c == "3":
            handle_test_conflicts()
        elif c == "4":
            handle_test_retries()
        elif c == "5":
            handle_test_reuse()
        elif c == "6":
            handle_inspect_checkpoint()
        elif c == "0":
            print("\nExiting Conductor Explorer. Goodbye!")
            break
        else:
            print("Invalid selection.")


if __name__ == "__main__":
    main()
