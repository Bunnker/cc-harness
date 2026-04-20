#!/usr/bin/env python3
"""Validate isolated worker worktree flow for harness verification."""

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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="harness-worktree-") as temp_dir:
        repo = Path(temp_dir)
        trace_dir = repo / ".claude" / "harness-lab" / "traces" / "2026-04-15-stage-1-coding"
        trace_dir.mkdir(parents=True, exist_ok=True)

        run(["git", "init", "--quiet"], cwd=repo)
        run(["git", "config", "user.email", "codex@example.com"], cwd=repo)
        run(["git", "config", "user.name", "Codex"], cwd=repo)

        (repo / "src").mkdir(exist_ok=True)
        (repo / "src" / "a.ts").write_text("export const a = 1;\n", encoding="utf-8")
        (repo / "src" / "b.ts").write_text("export const b = 1;\n", encoding="utf-8")
        run(["git", "add", "."], cwd=repo)
        run(["git", "commit", "-m", "baseline", "--quiet"], cwd=repo)
        baseline = run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()

        write_json(
            repo / ".claude" / "harness-state.json",
            {
                "commands": {
                    "build": {"command": "git diff --stat HEAD -- src/a.ts", "category": "build"},
                    "smoke": {"command": "git diff --name-only HEAD -- src/a.ts", "category": "smoke"},
                },
                "constraints": ["Only modify src/a.ts inside isolated worker worktree"],
                "smoke_tests": ["git diff --name-only HEAD -- src/a.ts"],
            },
        )
        write_json(
            trace_dir / "workers.json",
            [
                {
                    "worker": "1",
                    "target_paths": ["src/a.ts"],
                    "expected_outputs": ["src/a.ts"],
                    "isolation": "worktree",
                }
            ],
        )
        (trace_dir / "worker-1-prompt.md").write_text("worker-1 target_paths: src/a.ts\n", encoding="utf-8")
        (trace_dir / "worker-1-result.md").write_text("worker-1 completed in isolated worktree.\n", encoding="utf-8")

        run(
            [
                sys.executable,
                str(HOOK_DIR / "prepare-worker-isolation.py"),
                "--project-path",
                str(repo),
                "--trace-dir",
                str(trace_dir),
                "--worker",
                "1",
                "--baseline",
                baseline,
                "--target-path",
                "src/a.ts",
            ]
        )

        metadata_path = trace_dir / "worker-1-worktree.json"
        metadata = read_json(metadata_path)
        worktree_path = Path(metadata["worktree_path"])
        assert worktree_path.exists()

        (worktree_path / "src" / "a.ts").write_text(
            "export const a = 2;\nexport function square(x: number) { return x * x; }\n",
            encoding="utf-8",
        )
        (repo / "src" / "b.ts").write_text("export const b = 2;\n", encoding="utf-8")

        run(
            [
                sys.executable,
                str(HOOK_DIR / "run-harness-verify.py"),
                "--project-path",
                str(repo),
                "--trace-dir",
                str(trace_dir),
                "--baseline",
                baseline,
                "--stage",
                "stage-1",
                "--task-type",
                "coding",
                "--project-name",
                "worktree-fixture",
                "--cleanup-worktrees",
            ]
        )

        diff_payload = read_json(trace_dir / "worker-1-diff.json")
        assert diff_payload["capture_source"] == "worker_worktree"
        assert diff_payload["attribution_confidence"] == "high"
        assert diff_payload["scoped_changed_files"] == ["src/a.ts"]
        assert diff_payload["all_changed_files"] == ["src/a.ts"]
        assert diff_payload["path_violation_candidates"] == []

        verification = (trace_dir / "verification.md").read_text(encoding="utf-8")
        assert "isolated worker worktree" in verification

        cleanup_metadata = read_json(metadata_path)
        assert cleanup_metadata["cleanup_status"] == "removed"
        assert not worktree_path.exists()

        main_repo_diff = run(["git", "diff", "--name-only"], cwd=repo).stdout.splitlines()
        assert "src/b.ts" in main_repo_diff
        assert "src/a.ts" not in main_repo_diff

    print("worktree_isolation=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
