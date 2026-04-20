#!/usr/bin/env python3
"""Generate per-worker diff artifacts for harness traces."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-path", required=True)
    parser.add_argument("--trace-dir", required=True)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--worker", required=True)
    parser.add_argument("--target-path", action="append", dest="target_paths", default=[])
    parser.add_argument("--peer-owned-path", action="append", dest="peer_owned_paths", default=[])
    parser.add_argument("--worktree-path")
    parser.add_argument("--allow-global-fallback", action="store_true")
    return parser.parse_args()


def run_git(project_path: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(project_path), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )


def normalize_repo_path(path: str) -> str:
    normalized = path.replace("\\", "/").strip()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.rstrip("/")


def matches_target(path: str, targets: list[str]) -> bool:
    normalized_path = normalize_repo_path(path)
    for target in targets:
        normalized_target = normalize_repo_path(target)
        if not normalized_target:
            continue
        if normalized_path == normalized_target:
            return True
        if normalized_path.startswith(f"{normalized_target}/"):
            return True
    return False


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


def parse_numstat(output: str) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for line in output.splitlines():
        if line.startswith("warning: "):
            continue
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        added_raw, deleted_raw, path = parts
        items.append(
            {
                "path": normalize_repo_path(path),
                "added": None if added_raw == "-" else int(added_raw),
                "deleted": None if deleted_raw == "-" else int(deleted_raw),
            }
        )
    return items


def git_output_lines(project_path: Path, baseline: str, target_paths: list[str], args: list[str]) -> str:
    command = [*args, baseline]
    if target_paths:
        command.extend(["--", *target_paths])
    result = run_git(project_path, command)
    if result.returncode != 0:
        raise RuntimeError(result.stdout.strip() or f"git {' '.join(command)} failed")
    return result.stdout


def main() -> int:
    args = parse_args()
    project_path = Path(args.project_path)
    trace_dir = Path(args.trace_dir)
    source_project_path = Path(args.worktree_path) if args.worktree_path else project_path
    worker = args.worker
    baseline = args.baseline
    target_paths = unique_paths(args.target_paths)
    peer_owned_paths = [path for path in unique_paths(args.peer_owned_paths) if not matches_target(path, target_paths)]

    if not target_paths and not args.allow_global_fallback:
        print("ERROR: target paths are required unless --allow-global-fallback is set", file=sys.stderr)
        return 1

    if not project_path.exists():
        print(f"ERROR: project path not found: {project_path}", file=sys.stderr)
        return 1
    if args.worktree_path and not source_project_path.exists():
        print(f"ERROR: worktree path not found: {source_project_path}", file=sys.stderr)
        return 1

    trace_dir.mkdir(parents=True, exist_ok=True)

    scope_mode = "target_paths" if target_paths else "global_fallback"
    capture_source = "worker_worktree" if args.worktree_path else "project_worktree"
    scoped_name_output = git_output_lines(source_project_path, baseline, target_paths, ["diff", "--name-only"])
    scoped_stat_output = git_output_lines(source_project_path, baseline, target_paths, ["diff", "--stat"])
    scoped_patch_output = git_output_lines(source_project_path, baseline, target_paths, ["diff"])
    numstat_output = git_output_lines(source_project_path, baseline, target_paths, ["diff", "--numstat"])
    all_changed_output = git_output_lines(source_project_path, baseline, [], ["diff", "--name-only"])

    scoped_changed_files = [
        normalize_repo_path(line)
        for line in scoped_name_output.splitlines()
        if line.strip() and not line.startswith("warning: ")
    ]
    all_changed_files = [
        normalize_repo_path(line)
        for line in all_changed_output.splitlines()
        if line.strip() and not line.startswith("warning: ")
    ]
    peer_owned_changed_files = (
        [path for path in all_changed_files if not matches_target(path, target_paths) and matches_target(path, peer_owned_paths)]
        if target_paths and not args.worktree_path
        else []
    )
    path_violation_candidates = (
        [
            path
            for path in all_changed_files
            if not matches_target(path, target_paths) and not matches_target(path, peer_owned_paths)
        ]
        if target_paths and not args.worktree_path
        else []
    )

    attribution_confidence = "high"
    if scope_mode == "global_fallback":
        attribution_confidence = "low"
    elif path_violation_candidates:
        attribution_confidence = "low"

    notes: list[str] = []
    if scope_mode == "global_fallback":
        notes.append("target_paths unavailable; diff captured against the full baseline->worktree change set")
    if args.worktree_path:
        notes.append("diff captured from isolated worker worktree")
    if peer_owned_changed_files:
        notes.append(
            "peer-owned target_paths detected in the same baseline->worktree window and excluded from path violations"
        )
    if path_violation_candidates:
        notes.append(
            "path_violation_candidates are based on baseline->worktree and may include unrelated parallel changes"
        )

    patch_path = trace_dir / f"worker-{worker}-diff.patch"
    patch_lines = [
        f"=== worker-{worker} diff ===",
        f"baseline: {baseline}",
        f"target_paths: {' '.join(target_paths) if target_paths else '* (global_fallback)'}",
        f"scope_mode: {scope_mode}",
        f"capture_source: {capture_source}",
        f"attribution_confidence: {attribution_confidence}",
        f"touched_files: {', '.join(scoped_changed_files) if scoped_changed_files else 'none'}",
        f"peer_owned_changed_files: {', '.join(peer_owned_changed_files) if peer_owned_changed_files else 'none'}",
        f"path_violation_candidates: {', '.join(path_violation_candidates) if path_violation_candidates else 'none'}",
        "",
        "=== git diff --stat ===",
        scoped_stat_output.rstrip(),
        "",
        "=== git diff ===",
        scoped_patch_output.rstrip(),
        "",
    ]
    patch_path.write_text("\n".join(patch_lines), encoding="utf-8")

    diff_json = {
        "worker": worker,
        "captured_at": now_iso(),
        "baseline": baseline,
        "scope_mode": scope_mode,
        "capture_source": capture_source,
        "attribution_confidence": attribution_confidence,
        "target_paths": target_paths,
        "peer_owned_paths": peer_owned_paths,
        "scoped_changed_files": scoped_changed_files,
        "all_changed_files": all_changed_files,
        "peer_owned_changed_files": peer_owned_changed_files,
        "path_violation_candidates": path_violation_candidates,
        "numstat": parse_numstat(numstat_output),
        "notes": notes,
    }
    diff_json_path = trace_dir / f"worker-{worker}-diff.json"
    diff_json_path.write_text(json.dumps(diff_json, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote {patch_path} and {diff_json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
