#!/usr/bin/env python3
"""Run standardized commands from harness-state.json and write commands.log."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


DEFAULT_SKIPS = {"structural_diff", "per_worker_diff"}
TIMEOUT_EXIT_CODE = 124
SPAWN_EXIT_CODE = 127


@dataclass
class CommandSpec:
    name: str
    command: str
    timeout: int | None = None
    category: str | None = None


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-file", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--project-path")
    parser.add_argument("--context", default="verification")
    parser.add_argument("--target-path", action="append", dest="target_paths", default=[])
    parser.add_argument("--include-command", action="append", default=[])
    parser.add_argument("--skip-command", action="append", default=[])
    return parser.parse_args()


def load_command_specs(state_file: Path) -> list[CommandSpec]:
    state = json.loads(state_file.read_text(encoding="utf-8-sig"))
    raw_commands = state.get("commands", {})
    if not isinstance(raw_commands, dict):
        return []

    specs: list[CommandSpec] = []
    for name, value in raw_commands.items():
        if isinstance(value, str):
            specs.append(CommandSpec(name=name, command=value))
            continue
        if isinstance(value, dict) and isinstance(value.get("command"), str):
            timeout = value.get("timeout")
            timeout_int = int(timeout) if isinstance(timeout, (int, float)) else None
            category = value.get("category") if isinstance(value.get("category"), str) else None
            specs.append(
                CommandSpec(
                    name=name,
                    command=value["command"],
                    timeout=timeout_int,
                    category=category,
                )
            )
    return specs


def filter_specs(specs: list[CommandSpec], includes: set[str], skips: set[str]) -> list[CommandSpec]:
    filtered: list[CommandSpec] = []
    for spec in specs:
        if spec.name in skips:
            continue
        if includes and spec.name not in includes:
            continue
        filtered.append(spec)
    return filtered


def run_command(spec: CommandSpec, project_path: Path | None) -> dict[str, object]:
    started_at = now_iso()
    started_monotonic = time.monotonic()

    try:
        completed = subprocess.run(
            spec.command,
            shell=True,
            cwd=str(project_path) if project_path else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=spec.timeout,
            check=False,
        )
        output = completed.stdout or ""
        exit_code = completed.returncode
        failure_kind = "none" if exit_code == 0 else "nonzero_exit"
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        stderr = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
        if stderr:
            output = f"{output}\n{stderr}" if output else stderr
        if output:
            output = f"{output}\n[command-facade] command timed out"
        else:
            output = "[command-facade] command timed out"
        exit_code = TIMEOUT_EXIT_CODE
        failure_kind = "timeout"
    except OSError as exc:
        output = f"[command-facade] failed to spawn command: {exc}"
        exit_code = SPAWN_EXIT_CODE
        failure_kind = "spawn_error"

    finished_at = now_iso()
    duration_ms = int((time.monotonic() - started_monotonic) * 1000)
    return {
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_ms": duration_ms,
        "output": output.rstrip(),
        "exit_code": exit_code,
        "failure_kind": failure_kind,
    }


def render_log(
    specs: list[CommandSpec],
    results: list[dict[str, object]],
    *,
    context: str,
    project_path: str | None,
    target_paths: list[str],
) -> str:
    lines = [
        "=== metadata ===",
        f"generated_at: {now_iso()}",
        f"context: {context}",
        f"project_path: {project_path or 'not_configured'}",
        f"target_paths: {' | '.join(target_paths) if target_paths else 'not_configured'}",
        "",
    ]

    for spec, result in zip(specs, results):
        lines.extend(
            [
                f"=== {spec.name} ===",
                f"$ {spec.command}",
                f"context: {context}",
                f"category: {spec.category or 'not_configured'}",
                f"target_paths: {' | '.join(target_paths) if target_paths else 'not_configured'}",
                f"started_at: {result['started_at']}",
                f"finished_at: {result['finished_at']}",
                f"duration_ms: {result['duration_ms']}",
                f"timeout_s: {spec.timeout if spec.timeout is not None else 'not_configured'}",
                f"failure_kind: {result['failure_kind']}",
            ]
        )
        if result["output"]:
            lines.append(str(result["output"]))
        lines.extend([f"exit_code: {result['exit_code']}", ""])

    if not specs:
        lines.append("[command-facade] no executable commands found")
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    state_file = Path(args.state_file)
    output_path = Path(args.output)
    project_path = Path(args.project_path) if args.project_path else None

    if not state_file.exists():
        print(f"ERROR: state file not found: {state_file}", file=sys.stderr)
        return 1

    specs = load_command_specs(state_file)
    filtered_specs = filter_specs(
        specs,
        includes=set(args.include_command),
        skips=DEFAULT_SKIPS | set(args.skip_command),
    )
    results = [run_command(spec, project_path) for spec in filtered_specs]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        render_log(
            filtered_specs,
            results,
            context=args.context,
            project_path=str(project_path) if project_path else None,
            target_paths=args.target_paths,
        ),
        encoding="utf-8",
    )

    failures = sum(1 for result in results if int(result["exit_code"]) != 0)
    print(f"Wrote {output_path} ({len(results)} commands, {failures} non-zero)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
