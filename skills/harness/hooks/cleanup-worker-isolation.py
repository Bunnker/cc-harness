#!/usr/bin/env python3
"""Remove an isolated git worktree created for a harness worker."""

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
    parser.add_argument("--allow-dirty", action="store_true")
    return parser.parse_args()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_git(project_path: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(project_path), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )


def ensure_safe_path(project_path: Path, worktree_path: Path) -> Path:
    resolved = worktree_path.resolve()
    allowed_root = (project_path / ".claude" / "harness-lab" / "worktrees").resolve()
    if not resolved.is_relative_to(allowed_root):
        raise RuntimeError(f"refusing to remove worktree outside allowed root: {resolved}")
    return resolved


def main() -> int:
    args = parse_args()
    project_path = Path(args.project_path).resolve()
    trace_dir = Path(args.trace_dir).resolve()
    worker_id = str(args.worker)
    metadata_path = trace_dir / f"worker-{worker_id}-worktree.json"
    if not metadata_path.exists():
        raise RuntimeError(f"worktree metadata not found: {metadata_path}")

    metadata = load_json(metadata_path)
    worktree_raw = metadata.get("worktree_path")
    if not isinstance(worktree_raw, str) or not worktree_raw:
        raise RuntimeError(f"worktree_path missing in metadata: {metadata_path}")

    worktree_path = ensure_safe_path(project_path, Path(worktree_raw))
    if not worktree_path.exists():
        metadata["cleanup_status"] = "missing"
        metadata["removed_at"] = now_iso()
        write_json(metadata_path, metadata)
        print(f"Worktree already absent: {worktree_path}")
        return 0

    remove_args = ["worktree", "remove"]
    if args.allow_dirty:
        remove_args.append("--force")
    remove_args.append(str(worktree_path))
    result = run_git(project_path, remove_args)
    if result.returncode != 0:
        raise RuntimeError(result.stdout.strip() or f"failed to remove worktree: {worktree_path}")

    metadata["cleanup_status"] = "removed"
    metadata["removed_at"] = now_iso()
    write_json(metadata_path, metadata)
    print(f"Removed {worktree_path} and updated {metadata_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
