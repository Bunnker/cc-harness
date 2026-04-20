#!/usr/bin/env python3
"""Validate parallel per-worker diff attribution for disjoint and overlapping target paths."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
HOOK_DIR = REPO_ROOT / "skills" / "harness" / "hooks"


def run(command: list[str], *, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    if check and completed.returncode != 0:
        raise RuntimeError(f"command failed ({completed.returncode}): {' '.join(command)}\n{completed.stdout}")
    return completed


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def make_repo(root: Path, *, modify_same_file: bool) -> tuple[Path, str]:
    run(["git", "init", "--quiet"], cwd=root)
    run(["git", "config", "user.email", "codex@example.com"], cwd=root)
    run(["git", "config", "user.name", "Codex"], cwd=root)

    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / ".claude").mkdir(parents=True, exist_ok=True)
    (root / "src" / "a.ts").write_text("export const a = 1;\n", encoding="utf-8")
    (root / "src" / "b.ts").write_text("export const b = 1;\n", encoding="utf-8")
    run(["git", "add", "."], cwd=root)
    run(["git", "commit", "-m", "baseline", "--quiet"], cwd=root)
    baseline = run(["git", "rev-parse", "HEAD"], cwd=root).stdout.strip()

    if modify_same_file:
        (root / "src" / "a.ts").write_text(
            "export const a = 2;\nexport const a2 = 3;\n",
            encoding="utf-8",
        )
    else:
        (root / "src" / "a.ts").write_text("export const a = 2;\n", encoding="utf-8")
        (root / "src" / "b.ts").write_text("export const b = 2;\n", encoding="utf-8")

    return root, baseline


def seed_trace(trace_dir: Path, workers: list[dict]) -> None:
    trace_dir.mkdir(parents=True, exist_ok=True)
    for worker in workers:
        worker_id = str(worker["worker"])
        (trace_dir / f"worker-{worker_id}-prompt.md").write_text(
            f"worker-{worker_id} target_paths: {', '.join(worker.get('target_paths', []))}\n",
            encoding="utf-8",
        )
        (trace_dir / f"worker-{worker_id}-result.md").write_text(
            f"worker-{worker_id} completed.\n",
            encoding="utf-8",
        )
    write_json(trace_dir / "workers.json", workers)


def run_diff(trace_dir: Path, project_path: Path, baseline: str, worker: dict, workers: list[dict]) -> None:
    command = [
        sys.executable,
        str(HOOK_DIR / "generate-diff-artifact.py"),
        "--project-path",
        str(project_path),
        "--trace-dir",
        str(trace_dir),
        "--baseline",
        baseline,
        "--worker",
        str(worker["worker"]),
    ]
    for path in worker.get("target_paths", []):
        command.extend(["--target-path", path])
    for peer in workers:
        if str(peer["worker"]) == str(worker["worker"]):
            continue
        for path in peer.get("target_paths", []):
            command.extend(["--peer-owned-path", path])
    run(command)


def render_bundle(trace_dir: Path, project_path: Path, stage: str) -> str:
    state_file = project_path / ".claude" / "harness-state.json"
    if not state_file.exists():
        write_json(state_file, {"constraints": [], "smoke_tests": []})
    run(
        [
            sys.executable,
            str(HOOK_DIR / "render-verification-artifacts.py"),
            "--trace-dir",
            str(trace_dir),
            "--project-path",
            str(project_path),
            "--stage",
            stage,
            "--task-type",
            "coding",
            "--state-file",
            str(state_file),
            "--worker-spec-file",
            str(trace_dir / "workers.json"),
            "--project-name",
            "parallel-attribution-fixture",
        ]
    )
    return (trace_dir / "verification.md").read_text(encoding="utf-8")


def validate_disjoint_case(root: Path) -> None:
    project_path, baseline = make_repo(root, modify_same_file=False)
    trace_dir = project_path / ".claude" / "harness-lab" / "traces" / "2026-04-15-stage-1-coding"
    workers = [
        {"worker": "1", "target_paths": ["src/a.ts"], "expected_outputs": ["src/a.ts"]},
        {"worker": "2", "target_paths": ["src/b.ts"], "expected_outputs": ["src/b.ts"]},
    ]
    seed_trace(trace_dir, workers)
    for worker in workers:
        run_diff(trace_dir, project_path, baseline, worker, workers)

    verification = render_bundle(trace_dir, project_path, "stage-1")
    worker_1 = read_json(trace_dir / "worker-1-diff.json")
    worker_2 = read_json(trace_dir / "worker-2-diff.json")

    assert worker_1["attribution_confidence"] == "high"
    assert worker_2["attribution_confidence"] == "high"
    assert worker_1["peer_owned_changed_files"] == ["src/b.ts"]
    assert worker_2["peer_owned_changed_files"] == ["src/a.ts"]
    assert worker_1["path_violation_candidates"] == []
    assert worker_2["path_violation_candidates"] == []
    assert "target_paths overlap: PASS no overlapping target paths" in verification


def validate_overlap_case(root: Path) -> None:
    project_path, baseline = make_repo(root, modify_same_file=True)
    trace_dir = project_path / ".claude" / "harness-lab" / "traces" / "2026-04-15-stage-2-coding"
    workers = [
        {"worker": "1", "target_paths": ["src/a.ts"], "expected_outputs": ["src/a.ts"]},
        {"worker": "2", "target_paths": ["src/a.ts"], "expected_outputs": ["src/a.ts"]},
    ]
    seed_trace(trace_dir, workers)
    for worker in workers:
        run_diff(trace_dir, project_path, baseline, worker, workers)

    verification = render_bundle(trace_dir, project_path, "stage-2")
    assert "target_paths overlap: WARN" in verification
    assert "src/a.ts: worker-1, worker-2" in verification


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="parallel-diff-disjoint-") as temp_dir:
        validate_disjoint_case(Path(temp_dir))
    with tempfile.TemporaryDirectory(prefix="parallel-diff-overlap-") as temp_dir:
        validate_overlap_case(Path(temp_dir))
    print("parallel_diff_attribution=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
