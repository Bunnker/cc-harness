#!/usr/bin/env python3
"""Prepare an isolated git worktree for a harness worker."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-path", required=True)
    parser.add_argument("--trace-dir", required=True)
    parser.add_argument("--worker", required=True)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--target-path", action="append", dest="target_paths", default=[])
    parser.add_argument("--reason", default="conflict_isolation")
    parser.add_argument("--reuse-existing", action="store_true")
    return parser.parse_args()


def normalize_repo_path(path: str) -> str:
    normalized = path.replace("\\", "/").strip()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.rstrip("/")


def unique_paths(paths: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for path in paths:
        normalized = normalize_repo_path(path)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique.append(normalized)
    return unique


def safe_worktree_root(project_path: Path, trace_dir: Path) -> Path:
    root = project_path / ".claude" / "harness-lab" / "worktrees" / trace_dir.name
    resolved = root.resolve()
    allowed_root = (project_path / ".claude" / "harness-lab" / "worktrees").resolve()
    if not resolved.is_relative_to(allowed_root):
        raise RuntimeError(f"unsafe worktree root: {resolved}")
    return resolved


def run_git(project_path: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(project_path), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )


def validate_git_repo(project_path: Path, baseline: str) -> None:
    if not project_path.exists():
        raise RuntimeError(f"project path not found: {project_path}")
    status = run_git(project_path, ["rev-parse", "--show-toplevel"])
    if status.returncode != 0:
        raise RuntimeError(status.stdout.strip() or f"not a git repo: {project_path}")
    baseline_result = run_git(project_path, ["rev-parse", "--verify", baseline])
    if baseline_result.returncode != 0:
        raise RuntimeError(baseline_result.stdout.strip() or f"baseline not found: {baseline}")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def update_workers_json(trace_dir: Path, worker_id: str, worktree_path: Path) -> None:
    workers_path = trace_dir / "workers.json"
    if not workers_path.exists():
        return

    payload = load_json(workers_path)
    updated = False
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict) and str(item.get("worker")) == worker_id:
                item["isolation"] = "worktree"
                item["worktree_path"] = str(worktree_path)
                updated = True
    elif isinstance(payload, dict):
        for key, value in payload.items():
            if str(key) == worker_id and isinstance(value, dict):
                value["isolation"] = "worktree"
                value["worktree_path"] = str(worktree_path)
                updated = True

    if updated:
        write_json(workers_path, payload)


def main() -> int:
    args = parse_args()
    project_path = Path(args.project_path).resolve()
    trace_dir = Path(args.trace_dir).resolve()
    worker_id = str(args.worker)
    target_paths = unique_paths(args.target_paths)

    validate_git_repo(project_path, args.baseline)
    worktree_root = safe_worktree_root(project_path, trace_dir)
    worktree_path = worktree_root / f"worker-{worker_id}"
    metadata_path = trace_dir / f"worker-{worker_id}-worktree.json"

    trace_dir.mkdir(parents=True, exist_ok=True)
    worktree_root.mkdir(parents=True, exist_ok=True)

    if worktree_path.exists():
        if not args.reuse_existing:
            raise RuntimeError(f"worktree path already exists: {worktree_path}")
        metadata: dict[str, Any]
        if metadata_path.exists():
            metadata = load_json(metadata_path)
        else:
            metadata = {}
        metadata.update(
            {
                "worker": worker_id,
                "prepared_at": metadata.get("prepared_at", now_iso()),
                "project_path": str(project_path),
                "trace_dir": str(trace_dir),
                "baseline": args.baseline,
                "isolation": "worktree",
                "reason": args.reason,
                "target_paths": target_paths,
                "worktree_path": str(worktree_path),
                "cleanup_status": metadata.get("cleanup_status", "prepared"),
            }
        )
        write_json(metadata_path, metadata)
        update_workers_json(trace_dir, worker_id, worktree_path)
        print(f"Reused {worktree_path} and refreshed {metadata_path}")
        return 0

    add_result = run_git(project_path, ["worktree", "add", "--detach", str(worktree_path), args.baseline])
    if add_result.returncode != 0:
        raise RuntimeError(add_result.stdout.strip() or f"failed to add worktree: {worktree_path}")

    metadata = {
        "worker": worker_id,
        "prepared_at": now_iso(),
        "project_path": str(project_path),
        "trace_dir": str(trace_dir),
        "baseline": args.baseline,
        "isolation": "worktree",
        "reason": args.reason,
        "target_paths": target_paths,
        "worktree_path": str(worktree_path),
        "cleanup_status": "prepared",
    }
    write_json(metadata_path, metadata)
    update_workers_json(trace_dir, worker_id, worktree_path)
    print(f"Prepared {worktree_path} and wrote {metadata_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
