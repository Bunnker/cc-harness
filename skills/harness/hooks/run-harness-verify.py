#!/usr/bin/env python3
"""Execute harness verification workflow from trace artifacts and worker specs."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-path", required=True)
    parser.add_argument("--trace-dir", required=True)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--task-type", required=True, choices=["coding", "audit"])
    parser.add_argument("--state-file")
    parser.add_argument("--worker-spec-file")
    parser.add_argument("--project-name")
    parser.add_argument("--cleanup-worktrees", action="store_true")
    return parser.parse_args()


def load_worker_specs(path: Path | None, trace_dir: Path) -> list[dict]:
    if path and path.exists():
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            return [
                {"worker": worker_id, **item}
                for worker_id, item in payload.items()
                if isinstance(item, dict)
            ]

    inferred = []
    for result_file in sorted(trace_dir.glob("worker-*-result.md")):
        worker_id = result_file.stem.split("-")[1]
        inferred.append({"worker": worker_id, "target_paths": [], "expected_outputs": []})
    return inferred


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def merge_worktree_metadata(worker_specs: list[dict], trace_dir: Path) -> list[dict]:
    merged: list[dict] = []
    for spec in worker_specs:
        worker_id = str(spec.get("worker"))
        metadata_path = trace_dir / f"worker-{worker_id}-worktree.json"
        if metadata_path.exists():
            metadata = load_json(metadata_path)
            if isinstance(metadata, dict):
                merged_spec = dict(spec)
                merged_spec.setdefault("isolation", metadata.get("isolation"))
                merged_spec.setdefault("worktree_path", metadata.get("worktree_path"))
                merged_spec.setdefault("cleanup_status", metadata.get("cleanup_status"))
                merged.append(merged_spec)
                continue
        merged.append(dict(spec))
    return merged


def write_step_failure(
    *,
    trace_dir: Path,
    stage: str,
    task_type: str,
    step: str,
    command: list[str],
    exit_code: int,
    output: str,
) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d")
    failure_reason_path = trace_dir / "failure-reason.md"
    rendered_output = output.strip() or "not_available"
    lines = [
        f"## 失败归因 — {timestamp} {stage}",
        "",
        f"- task_type: `{task_type}`",
        f"- step: `{step}`",
        f"- exit_code: `{exit_code}`",
        f"- trace_path: `{trace_dir}`",
        "",
        "### 阻断项",
        "",
        f"- `{step}` 执行失败，verification bundle 未完整生成。",
        "",
        "### 失败命令",
        "",
        "```text",
        " ".join(command),
        "```",
        "",
        "### 原始输出",
        "",
        "```text",
        rendered_output,
        "```",
        "",
        "### 恢复建议",
        "",
        "- 修复当前步骤的命令/环境问题后，重新运行 run-harness-verify.py。",
        "- 如果失败发生在 diff 生成阶段，先检查 baseline commit 与 target_paths 是否有效。",
    ]
    failure_reason_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def cleanup_worktree(
    project_path: Path,
    trace_dir: Path,
    worker_id: str,
    worktree_path_raw: str,
    *,
    stage: str,
    task_type: str,
) -> None:
    allowed_root = (project_path / ".claude" / "harness-lab" / "worktrees").resolve()
    worktree_path = Path(worktree_path_raw).resolve()
    if not worktree_path.is_relative_to(allowed_root):
        raise RuntimeError(f"refusing to remove worktree outside allowed root: {worktree_path}")

    cleanup_cmd = [
        sys.executable,
        str(SCRIPT_DIR / "cleanup-worker-isolation.py"),
        "--project-path",
        str(project_path),
        "--trace-dir",
        str(trace_dir),
        "--worker",
        worker_id,
        "--allow-dirty",
    ]
    run_step(
        f"cleanup-worker-isolation worker-{worker_id}",
        cleanup_cmd,
        trace_dir=trace_dir,
        stage=stage,
        task_type=task_type,
    )


def run_step(step: str, command: list[str], *, trace_dir: Path, stage: str, task_type: str) -> None:
    completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False)
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.returncode != 0:
        write_step_failure(
            trace_dir=trace_dir,
            stage=stage,
            task_type=task_type,
            step=step,
            command=command,
            exit_code=completed.returncode,
            output=completed.stdout or "",
        )
        raise SystemExit(completed.returncode)


def main() -> int:
    args = parse_args()
    project_path = Path(args.project_path)
    trace_dir = Path(args.trace_dir)
    state_file = Path(args.state_file) if args.state_file else project_path / ".claude" / "harness-state.json"
    worker_spec_file = Path(args.worker_spec_file) if args.worker_spec_file else trace_dir / "workers.json"

    trace_dir.mkdir(parents=True, exist_ok=True)
    worker_specs = merge_worktree_metadata(
        load_worker_specs(worker_spec_file if worker_spec_file.exists() else None, trace_dir),
        trace_dir,
    )
    if not worker_specs:
        print("ERROR: no worker specs or worker result files found", file=sys.stderr)
        return 1

    if worker_spec_file and not worker_spec_file.exists():
        worker_spec_file.write_text(json.dumps(worker_specs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    all_target_paths: list[str] = []
    for spec in worker_specs:
        for path in spec.get("target_paths", []) or []:
            if isinstance(path, str) and path not in all_target_paths:
                all_target_paths.append(path)

    command_facade_cmd = [
        sys.executable,
        str(SCRIPT_DIR / "command-facade.py"),
        "--state-file",
        str(state_file),
        "--output",
        str(trace_dir / "commands.log"),
        "--project-path",
        str(project_path),
        "--context",
        "harness-verify",
    ]
    for path in all_target_paths:
        command_facade_cmd.extend(["--target-path", path])
    run_step("command-facade", command_facade_cmd, trace_dir=trace_dir, stage=args.stage, task_type=args.task_type)

    for spec in worker_specs:
        worker_id = str(spec.get("worker"))
        diff_cmd = [
            sys.executable,
            str(SCRIPT_DIR / "generate-diff-artifact.py"),
            "--project-path",
            str(project_path),
            "--trace-dir",
            str(trace_dir),
            "--baseline",
            args.baseline,
            "--worker",
            worker_id,
        ]
        target_paths = [path for path in spec.get("target_paths", []) or [] if isinstance(path, str)]
        worktree_path = spec.get("worktree_path") if isinstance(spec.get("worktree_path"), str) else None
        peer_owned_paths = []
        for peer_spec in worker_specs:
            if str(peer_spec.get("worker")) == worker_id:
                continue
            for path in peer_spec.get("target_paths", []) or []:
                if isinstance(path, str) and path not in peer_owned_paths:
                    peer_owned_paths.append(path)
        if target_paths:
            for path in target_paths:
                diff_cmd.extend(["--target-path", path])
            if worktree_path:
                diff_cmd.extend(["--worktree-path", worktree_path])
            else:
                for path in peer_owned_paths:
                    diff_cmd.extend(["--peer-owned-path", path])
        else:
            diff_cmd.append("--allow-global-fallback")
            if worktree_path:
                diff_cmd.extend(["--worktree-path", worktree_path])
        run_step(
            f"generate-diff-artifact worker-{worker_id}",
            diff_cmd,
            trace_dir=trace_dir,
            stage=args.stage,
            task_type=args.task_type,
        )

    render_cmd = [
        sys.executable,
        str(SCRIPT_DIR / "render-verification-artifacts.py"),
        "--trace-dir",
        str(trace_dir),
        "--project-path",
        str(project_path),
        "--stage",
        args.stage,
        "--task-type",
        args.task_type,
        "--state-file",
        str(state_file),
        "--worker-spec-file",
        str(worker_spec_file),
    ]
    if args.project_name:
        render_cmd.extend(["--project-name", args.project_name])
    run_step(
        "render-verification-artifacts",
        render_cmd,
        trace_dir=trace_dir,
        stage=args.stage,
        task_type=args.task_type,
    )

    if args.cleanup_worktrees:
        for spec in worker_specs:
            worker_id = str(spec.get("worker"))
            worktree_path = spec.get("worktree_path") if isinstance(spec.get("worktree_path"), str) else None
            if not worktree_path:
                continue
            cleanup_worktree(
                project_path,
                trace_dir,
                worker_id,
                worktree_path,
                stage=args.stage,
                task_type=args.task_type,
            )

    scorecard = json.loads((trace_dir / "scorecard.json").read_text(encoding="utf-8"))
    composite_score = scorecard.get("composite_score")
    print(
        f"Verification bundle ready: trace_dir={trace_dir} workers={len(worker_specs)} "
        f"composite_score={composite_score}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
