#!/usr/bin/env python3
"""Render verification.md and scorecard.json from trace artifacts."""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


COMMAND_HEADER_RE = re.compile(r"^=== (.+) ===$")
WORKER_RESULT_RE = re.compile(r"^worker-(\d+)-result\.md$")
WORKER_DIFF_RE = re.compile(r"^worker-(\d+)-diff\.json$")
WORKER_PROMPT_RE = re.compile(r"^worker-(\d+)-prompt\.md$")


@dataclass
class CommandBlock:
    name: str
    command: str
    context: str
    category: str | None
    target_paths: list[str]
    started_at: str | None
    finished_at: str | None
    duration_ms: int | None
    timeout_s: int | None
    failure_kind: str | None
    output: str
    exit_code: int | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace-dir", required=True)
    parser.add_argument("--project-path", required=True)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--task-type", required=True, choices=["design", "coding", "audit"])
    parser.add_argument("--project-name")
    parser.add_argument("--trace-path-relative")
    parser.add_argument("--worker-spec-file")
    parser.add_argument("--state-file")
    parser.add_argument("--output-verification")
    parser.add_argument("--output-scorecard")
    parser.add_argument("--output-failure-reason")
    return parser.parse_args()


def score_label(score: float | None, *, warn_threshold: float = 1.0) -> str:
    if score is None:
        return "N/A"
    if score >= warn_threshold:
        return "PASS"
    if score > 0:
        return "WARN"
    return "FAIL"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def infer_trace_path_relative(trace_dir: Path) -> str:
    normalized = trace_dir.as_posix()
    marker = "/.claude/"
    if marker in normalized:
        return normalized.split(marker, 1)[1]
    return trace_dir.name


def split_target_paths(raw: str) -> list[str]:
    if raw == "not_configured":
        return []
    return [item.strip() for item in raw.split("|") if item.strip()]


def parse_command_blocks(path: Path) -> list[CommandBlock]:
    if not path.exists():
        return []

    lines = path.read_text(encoding="utf-8").splitlines()
    blocks: list[tuple[str, list[str]]] = []
    current_name: str | None = None
    current_lines: list[str] = []

    for line in lines:
        match = COMMAND_HEADER_RE.match(line)
        if match:
            if current_name is not None:
                blocks.append((current_name, current_lines))
            current_name = match.group(1)
            current_lines = []
            continue
        if current_name is not None:
            current_lines.append(line)
    if current_name is not None:
        blocks.append((current_name, current_lines))

    parsed: list[CommandBlock] = []
    for name, block_lines in blocks:
        if name == "metadata":
            continue

        command = ""
        context = "not_configured"
        category: str | None = None
        target_paths: list[str] = []
        started_at = None
        finished_at = None
        duration_ms = None
        timeout_s = None
        failure_kind = None
        output_lines: list[str] = []
        exit_code = None

        idx = 0
        if idx < len(block_lines) and block_lines[idx].startswith("$ "):
            command = block_lines[idx][2:]
            idx += 1

        ordered_fields = [
            ("context", "context"),
            ("category", "category"),
            ("target_paths", "target_paths"),
            ("started_at", "started_at"),
            ("finished_at", "finished_at"),
            ("duration_ms", "duration_ms"),
            ("timeout_s", "timeout_s"),
            ("failure_kind", "failure_kind"),
        ]

        while idx < len(block_lines):
            line = block_lines[idx]
            matched = False
            for prefix, attr in ordered_fields:
                needle = f"{prefix}: "
                if line.startswith(needle):
                    raw_value = line[len(needle) :]
                    if attr == "context":
                        context = raw_value
                    elif attr == "category":
                        category = None if raw_value == "not_configured" else raw_value
                    elif attr == "target_paths":
                        target_paths = split_target_paths(raw_value)
                    elif attr == "started_at":
                        started_at = raw_value
                    elif attr == "finished_at":
                        finished_at = raw_value
                    elif attr == "duration_ms":
                        duration_ms = int(raw_value) if raw_value.isdigit() else None
                    elif attr == "timeout_s":
                        timeout_s = int(raw_value) if raw_value.isdigit() else None
                    elif attr == "failure_kind":
                        failure_kind = raw_value
                    idx += 1
                    matched = True
                    break
            if not matched:
                break

        while block_lines and not block_lines[-1].strip():
            block_lines.pop()

        if idx < len(block_lines) and block_lines[-1].startswith("exit_code: "):
            exit_code_raw = block_lines[-1].split(": ", 1)[1]
            exit_code = int(exit_code_raw) if re.fullmatch(r"-?\d+", exit_code_raw) else None
            output_lines = block_lines[idx:-1]
        else:
            output_lines = block_lines[idx:]

        parsed.append(
            CommandBlock(
                name=name,
                command=command,
                context=context,
                category=category,
                target_paths=target_paths,
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=duration_ms,
                timeout_s=timeout_s,
                failure_kind=failure_kind,
                output="\n".join(output_lines).strip(),
                exit_code=exit_code,
            )
        )

    return parsed


def load_worker_specs(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None or not path.exists():
        return {}

    raw = load_json(path)
    specs: dict[str, dict[str, Any]] = {}
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict) or "worker" not in item:
                continue
            specs[str(item["worker"])] = item
    elif isinstance(raw, dict):
        for key, value in raw.items():
            if isinstance(value, dict):
                specs[str(key)] = value
    return specs


def find_worker_ids(trace_dir: Path, worker_specs: dict[str, dict[str, Any]]) -> list[str]:
    ids = set(worker_specs)
    for path in trace_dir.iterdir():
        for pattern in (WORKER_RESULT_RE, WORKER_DIFF_RE, WORKER_PROMPT_RE):
            match = pattern.match(path.name)
            if match:
                ids.add(match.group(1))
    return sorted(ids, key=lambda value: int(value))


def summarize_commands(blocks: list[CommandBlock]) -> dict[str, Any]:
    categories = defaultdict(list)
    failures: list[CommandBlock] = []
    for block in blocks:
        key = block.category or infer_command_category(block.name)
        categories[key].append(block)
        if block.exit_code not in (None, 0):
            failures.append(block)
    return {"categories": categories, "failures": failures}


def infer_command_category(name: str) -> str:
    lowered = name.lower()
    if lowered.startswith("build"):
        return "build"
    if lowered.startswith("typecheck"):
        return "typecheck"
    if lowered.startswith("lint"):
        return "lint"
    if lowered.startswith("smoke"):
        return "smoke"
    if lowered.startswith("test"):
        return "test"
    return "uncategorized"


def command_dimension(blocks: list[CommandBlock], categories: set[str]) -> tuple[float | None, str]:
    selected = [block for block in blocks if (block.category or infer_command_category(block.name)) in categories]
    if not selected:
        return None, "not_configured"

    passed = sum(1 for block in selected if block.exit_code == 0)
    total = len(selected)
    failures = [block.name for block in selected if block.exit_code not in (0, None)]
    detail = f"{passed}/{total} passed"
    if failures:
        detail += f"; failures: {', '.join(failures)}"
    return round(passed / total, 2), detail


def load_state(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    raw = load_json(path)
    return raw if isinstance(raw, dict) else {}


def file_exists(project_path: Path, relative_path: str) -> bool:
    return (project_path / relative_path).exists()


def interface_change_declared(result_path: Path) -> bool:
    if not result_path.exists():
        return False
    return "INTERFACE_CHANGE" in result_path.read_text(encoding="utf-8")


def worker_status_rows(
    worker_ids: list[str],
    trace_dir: Path,
    project_path: Path,
    worker_specs: dict[str, dict[str, Any]],
    task_type: str,
    command_blocks: list[CommandBlock],
) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    failures: list[str] = []
    overall_command_ok = all(block.exit_code in (None, 0) for block in command_blocks) if command_blocks else True

    for worker_id in worker_ids:
        prompt_path = trace_dir / f"worker-{worker_id}-prompt.md"
        result_path = trace_dir / f"worker-{worker_id}-result.md"
        diff_patch_path = trace_dir / f"worker-{worker_id}-diff.patch"
        diff_json_path = trace_dir / f"worker-{worker_id}-diff.json"
        diff_payload = load_json(diff_json_path) if diff_json_path.exists() else {}
        spec = worker_specs.get(worker_id, {})
        expected_outputs = spec.get("expected_outputs", []) if isinstance(spec.get("expected_outputs"), list) else []

        artifact_ok = prompt_path.exists() and result_path.exists()
        if task_type in {"coding", "audit"}:
            artifact_ok = artifact_ok and diff_patch_path.exists() and diff_json_path.exists()

        outputs_ok = True
        missing_outputs: list[str] = []
        for output in expected_outputs:
            if not file_exists(project_path, output):
                outputs_ok = False
                missing_outputs.append(output)

        path_violations = (
            diff_payload.get("path_violation_candidates", [])
            if isinstance(diff_payload.get("path_violation_candidates"), list)
            else []
        )
        peer_owned_changed_files = (
            diff_payload.get("peer_owned_changed_files", [])
            if isinstance(diff_payload.get("peer_owned_changed_files"), list)
            else []
        )
        capture_source = diff_payload.get("capture_source") if isinstance(diff_payload.get("capture_source"), str) else None
        scope_mode = diff_payload.get("scope_mode") if isinstance(diff_payload.get("scope_mode"), str) else None
        attribution_confidence = (
            diff_payload.get("attribution_confidence")
            if isinstance(diff_payload.get("attribution_confidence"), str)
            else ("low" if scope_mode == "global_fallback" else "unknown")
        )
        interface_change = interface_change_declared(result_path)
        numstat = diff_payload.get("numstat", []) if isinstance(diff_payload.get("numstat"), list) else []
        change_volume = 0
        for item in numstat:
            if isinstance(item, dict):
                for key in ("added", "deleted"):
                    value = item.get(key)
                    if isinstance(value, int):
                        change_volume += value

        structural_score = 1.0
        structural_notes: list[str] = []
        if path_violations:
            structural_score -= 0.5
            structural_notes.append(f"path violations: {', '.join(path_violations)}")
        if interface_change:
            structural_score -= 0.25
            structural_notes.append("INTERFACE_CHANGE declared")
        if change_volume > 200:
            structural_score -= 0.25
            structural_notes.append(f"large diff volume={change_volume}")
        if scope_mode == "global_fallback":
            structural_score -= 0.25
            structural_notes.append("global fallback attribution")
        if capture_source == "worker_worktree":
            structural_notes.append("isolated worker worktree")
        if peer_owned_changed_files:
            structural_notes.append(f"peer-owned parallel changes: {', '.join(peer_owned_changed_files)}")
        if attribution_confidence == "low" and scope_mode != "global_fallback":
            structural_score -= 0.25
            structural_notes.append("low attribution confidence")
        structural_score = max(structural_score, 0.0)

        path_score = 1.0 if not path_violations else 0.5
        path_detail = "within target paths" if not path_violations else f"candidates: {', '.join(path_violations)}"
        if scope_mode == "global_fallback":
            path_score = 0.5
            path_detail = "global_fallback; attribution is not path-scoped"
        elif capture_source == "worker_worktree":
            path_detail = "within target paths; isolated worker worktree"
        elif peer_owned_changed_files:
            path_detail = f"within target paths; peer-owned changes excluded: {', '.join(peer_owned_changed_files)}"

        row = {
            "worker": worker_id,
            "artifacts_score": 1.0 if artifact_ok else 0.0,
            "artifacts_detail": "complete" if artifact_ok else "missing trace artifacts",
            "outputs_score": 1.0 if outputs_ok else 0.0 if expected_outputs else None,
            "outputs_detail": "all expected outputs present"
            if outputs_ok and expected_outputs
            else ("not_configured" if not expected_outputs else f"missing outputs: {', '.join(missing_outputs)}"),
            "commands_score": 1.0 if overall_command_ok else 0.0,
            "commands_detail": "all tracked commands passed" if overall_command_ok else "one or more commands failed",
            "path_score": path_score,
            "path_detail": path_detail,
            "structural_score": structural_score,
            "structural_detail": "; ".join(structural_notes) if structural_notes else f"diff volume={change_volume}",
            "coverage_score": 1.0 if artifact_ok and outputs_ok else 0.5 if artifact_ok else 0.0,
            "coverage_detail": "artifacts and outputs covered" if artifact_ok and outputs_ok else "partial verification coverage",
            "attribution_confidence": attribution_confidence,
        }
        rows.append(row)

        if not artifact_ok:
            failures.append(f"worker-{worker_id}: missing trace artifacts")
        if path_violations:
            failures.append(f"worker-{worker_id}: path violation candidates detected")
        if expected_outputs and not outputs_ok:
            failures.append(f"worker-{worker_id}: missing expected outputs")

    return rows, failures


def summarize_cross_worker(rows: list[dict[str, Any]], worker_specs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    overlaps: list[str] = []
    normalized_targets: dict[str, list[str]] = defaultdict(list)
    for worker_id, spec in worker_specs.items():
        paths = spec.get("target_paths", []) if isinstance(spec.get("target_paths"), list) else []
        for path in paths:
            normalized_targets[path].append(worker_id)

    for path, owners in sorted(normalized_targets.items()):
        if len(owners) > 1:
            overlaps.append(f"{path}: {', '.join(f'worker-{owner}' for owner in owners)}")

    has_conflicts = bool(overlaps)
    low_confidence_workers = [
        f"worker-{row['worker']}" for row in rows if row.get("attribution_confidence") not in (None, "high")
    ]
    detail_parts: list[str] = []
    if has_conflicts:
        detail_parts.append("; ".join(overlaps))
    else:
        detail_parts.append("no overlapping target paths")
    if low_confidence_workers:
        detail_parts.append(f"low attribution confidence: {', '.join(low_confidence_workers)}")
    return {
        "score": 1.0 if not has_conflicts and not low_confidence_workers else 0.5,
        "detail": "; ".join(detail_parts),
    }


def runtime_invariant_dimension(command_blocks: list[CommandBlock], state: dict[str, Any]) -> tuple[float | None, str]:
    smoke_tests = state.get("smoke_tests")
    if not isinstance(smoke_tests, list):
        smoke_tests = []

    smoke_score, smoke_detail = command_dimension(command_blocks, {"smoke"})
    if smoke_score is not None:
        return smoke_score, smoke_detail

    constraints = state.get("constraints")
    if constraints:
        return 0.5, "constraints configured but no automated invariant evidence recorded"
    if smoke_tests:
        return 0.0, "smoke tests configured but no smoke command evidence recorded"
    return None, "not_configured"


def verification_coverage_dimension(rows: list[dict[str, Any]], task_type: str) -> tuple[float | None, str]:
    if not rows:
        return None, "not_configured"
    scores = [row["coverage_score"] for row in rows]
    average = round(sum(scores) / len(scores), 2)
    return average, f"{sum(1 for score in scores if score == 1.0)}/{len(scores)} workers fully covered for {task_type}"


def structural_fidelity_dimension(rows: list[dict[str, Any]]) -> tuple[float | None, str]:
    if not rows:
        return None, "not_configured"
    scores = [row["structural_score"] for row in rows]
    average = round(sum(scores) / len(scores), 2)
    warnings = [f"worker-{row['worker']}: {row['structural_detail']}" for row in rows if row["structural_score"] < 1.0]
    detail = f"avg={average}"
    if warnings:
        detail += f"; warnings: {' | '.join(warnings)}"
    return average, detail


def calculate_composite(dimensions: dict[str, dict[str, Any]]) -> float | None:
    applicable = [item["score"] for item in dimensions.values() if isinstance(item.get("score"), (int, float))]
    if not applicable:
        return None
    return round(sum(applicable) / len(applicable), 2)


def render_failure_reason_md(
    *,
    date: str,
    stage: str,
    task_type: str,
    trace_path_relative: str,
    scorecard: dict[str, Any],
    rows: list[dict[str, Any]],
    failure_items: list[str],
    command_summary: dict[str, Any],
) -> str:
    lines = [
        f"## 失败归因 — {date} {stage}",
        "",
        f"- task_type: `{task_type}`",
        f"- composite_score: `{scorecard['composite_score'] if scorecard['composite_score'] is not None else 'null'}`",
        f"- trace_path: `{trace_path_relative}`",
        "",
        "### 阻断项",
        "",
    ]

    if failure_items:
        for item in failure_items:
            lines.append(f"- {item}")
    else:
        lines.append("- verification bundle completed with warnings but no explicit blocker was captured")

    lines.extend(["", "### 评分回退", ""])
    has_dimension_regression = False
    for name, payload in scorecard["dimensions"].items():
        score = payload.get("score")
        if isinstance(score, (int, float)) and score < 1.0:
            has_dimension_regression = True
            lines.append(f"- `{name}`: score={score} detail={payload.get('detail', 'not_configured')}")
    if not has_dimension_regression:
        lines.append("- none")

    lines.extend(["", "### 失败命令", ""])
    failures = command_summary["failures"]
    if failures:
        for block in failures:
            lines.append(
                f"- `{block.name}` exit_code={block.exit_code} failure_kind={block.failure_kind or 'unknown'} "
                f"duration_ms={block.duration_ms or 'unknown'}"
            )
    else:
        lines.append("- none")

    lines.extend(["", "### Worker 异常", ""])
    worker_anomalies = []
    for row in rows:
        if row["artifacts_score"] < 1.0:
            worker_anomalies.append(f"worker-{row['worker']}: {row['artifacts_detail']}")
        if row["outputs_score"] == 0.0:
            worker_anomalies.append(f"worker-{row['worker']}: {row['outputs_detail']}")
        if row["path_score"] < 1.0:
            worker_anomalies.append(f"worker-{row['worker']}: {row['path_detail']}")
        if row["structural_score"] < 1.0:
            worker_anomalies.append(f"worker-{row['worker']}: {row['structural_detail']}")
    if worker_anomalies:
        for item in worker_anomalies:
            lines.append(f"- {item}")
    else:
        lines.append("- none")

    recovery_hints: list[str] = []
    if failures:
        recovery_hints.append("基于 commands.log 逐条重跑失败命令，只修复新增报错，不回溯项目历史告警。")
    if any(row["path_score"] < 1.0 for row in rows):
        recovery_hints.append("收窄 target_paths 或把越界文件升级为显式计划输入，避免归责漂移。")
    if any(row["outputs_score"] == 0.0 for row in rows):
        recovery_hints.append("补齐缺失产出文件，再重新渲染 verification bundle。")
    if any(
        isinstance(payload.get("score"), (int, float)) and payload["score"] < 1.0
        for key, payload in scorecard["dimensions"].items()
        if key in {"runtime_invariants", "verification_coverage"}
    ):
        recovery_hints.append("补 smoke_tests / runtime invariants 证据，并重新生成 scorecard。")
    if not recovery_hints:
        recovery_hints.append("重新运行 run-harness-verify.py，确认 failure-reason.md 与 scorecard.json 同步更新。")

    lines.extend(["", "### 恢复建议", ""])
    for item in recovery_hints:
        lines.append(f"- {item}")

    return "\n".join(lines) + "\n"


def render_verification_md(
    *,
    date: str,
    stage: str,
    task_type: str,
    rows: list[dict[str, Any]],
    cross_worker: dict[str, Any],
    runtime_invariants: tuple[float | None, str],
    command_summary: dict[str, Any],
    scorecard: dict[str, Any],
    failure_items: list[str],
) -> str:
    lines = [
        f"## 验证结果 — {date} {stage}",
        "",
        f"- task_type: `{task_type}`",
        f"- composite_score: `{scorecard['composite_score'] if scorecard['composite_score'] is not None else 'null'}`",
        "",
        "### 单 Worker 验证",
        "",
        "| Worker | Trace | Outputs | Commands | Path | Structure | Coverage |",
        "|--------|------|---------|----------|------|-----------|----------|",
    ]

    for row in rows:
        lines.append(
            "| "
            f"worker-{row['worker']} | "
            f"{score_label(row['artifacts_score'])} {row['artifacts_detail']} | "
            f"{score_label(row['outputs_score'])} {row['outputs_detail']} | "
            f"{score_label(row['commands_score'])} {row['commands_detail']} | "
            f"{score_label(row['path_score'], warn_threshold=1.0)} {row['path_detail']} | "
            f"{score_label(row['structural_score'], warn_threshold=1.0)} {row['structural_detail']} | "
            f"{score_label(row['coverage_score'], warn_threshold=1.0)} {row['coverage_detail']} |"
        )

    lines.extend(
        [
            "",
            "### 跨 Worker 兼容性",
            "",
            f"- target_paths overlap: {score_label(cross_worker['score'], warn_threshold=1.0)} {cross_worker['detail']}",
            "",
            "### 运行时不变式",
            "",
            f"- runtime invariants: {score_label(runtime_invariants[0], warn_threshold=1.0)} {runtime_invariants[1]}",
            "",
            "### 命令摘要",
            "",
        ]
    )

    failures = command_summary["failures"]
    if failures:
        for block in failures:
            lines.append(
                f"- `{block.name}` exit_code={block.exit_code} failure_kind={block.failure_kind or 'unknown'} duration_ms={block.duration_ms or 'unknown'}"
            )
    else:
        lines.append("- all tracked commands passed")

    lines.extend(["", "### 失败摘要", ""])
    if failure_items:
        for item in failure_items:
            lines.append(f"- {item}")
    else:
        lines.append("- none")

    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    trace_dir = Path(args.trace_dir)
    project_path = Path(args.project_path)
    project_name = args.project_name or project_path.name
    verification_path = Path(args.output_verification) if args.output_verification else trace_dir / "verification.md"
    scorecard_path = Path(args.output_scorecard) if args.output_scorecard else trace_dir / "scorecard.json"
    failure_reason_path = Path(args.output_failure_reason) if args.output_failure_reason else trace_dir / "failure-reason.md"
    worker_specs = load_worker_specs(Path(args.worker_spec_file) if args.worker_spec_file else None)
    state = load_state(Path(args.state_file) if args.state_file else None)

    trace_dir.mkdir(parents=True, exist_ok=True)

    command_blocks = parse_command_blocks(trace_dir / "commands.log")
    worker_ids = find_worker_ids(trace_dir, worker_specs)
    rows, row_failures = worker_status_rows(
        worker_ids,
        trace_dir,
        project_path,
        worker_specs,
        args.task_type,
        command_blocks,
    )
    command_summary = summarize_commands(command_blocks)
    cross_worker = summarize_cross_worker(rows, worker_specs)

    build_score, build_detail = command_dimension(command_blocks, {"build", "lint", "typecheck", "check"})
    smoke_score, smoke_detail = command_dimension(command_blocks, {"smoke"})
    runtime_score, runtime_detail = runtime_invariant_dimension(command_blocks, state)
    structural_score, structural_detail = structural_fidelity_dimension(rows)
    coverage_score, coverage_detail = verification_coverage_dimension(rows, args.task_type)

    dimensions = {
        "build_lint_typecheck": {"score": build_score, "detail": build_detail},
        "smoke_tests": {"score": smoke_score, "detail": smoke_detail},
        "runtime_invariants": {"score": runtime_score, "detail": runtime_detail},
        "structural_fidelity": {"score": structural_score, "detail": structural_detail},
        "verification_coverage": {"score": coverage_score, "detail": coverage_detail},
    }
    composite_score = calculate_composite(dimensions)

    trace_path_relative = args.trace_path_relative or infer_trace_path_relative(trace_dir)
    date = datetime.now().strftime("%Y-%m-%d")
    scorecard = {
        "date": date,
        "stage": args.stage,
        "project": project_name,
        "dimensions": dimensions,
        "composite_score": composite_score,
        "trace_path": trace_path_relative,
    }

    failure_items = list(row_failures)
    for failure in command_summary["failures"]:
        failure_items.append(
            f"command `{failure.name}` failed with exit_code={failure.exit_code} failure_kind={failure.failure_kind or 'unknown'}"
        )
    if cross_worker["score"] != 1.0:
        failure_items.append(f"cross-worker overlap: {cross_worker['detail']}")
    if runtime_score == 0.0:
        failure_items.append(runtime_detail)

    verification_md = render_verification_md(
        date=date,
        stage=args.stage,
        task_type=args.task_type,
        rows=rows,
        cross_worker=cross_worker,
        runtime_invariants=(runtime_score, runtime_detail),
        command_summary=command_summary,
        scorecard=scorecard,
        failure_items=failure_items,
    )

    verification_path.write_text(verification_md, encoding="utf-8")
    scorecard_path.write_text(json.dumps(scorecard, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    should_write_failure_reason = bool(failure_items) or any(
        isinstance(payload.get("score"), (int, float)) and payload["score"] < 1.0 for payload in dimensions.values()
    )
    if should_write_failure_reason:
        failure_reason_md = render_failure_reason_md(
            date=date,
            stage=args.stage,
            task_type=args.task_type,
            trace_path_relative=trace_path_relative,
            scorecard=scorecard,
            rows=rows,
            failure_items=failure_items,
            command_summary=command_summary,
        )
        failure_reason_path.write_text(failure_reason_md, encoding="utf-8")
    elif failure_reason_path.exists():
        failure_reason_path.unlink()

    print(
        f"Wrote {verification_path} and {scorecard_path} "
        f"(workers={len(worker_ids)}, composite_score={composite_score if composite_score is not None else 'null'})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
