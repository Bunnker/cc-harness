#!/usr/bin/env python3
"""Validate canonical harness-lite boundary examples."""

from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_PATH = REPO_ROOT / "skills" / "harness-lite" / "examples.json"

REJECT_TAGS = {
    "public_api_change",
    "config_contract",
    "entrypoint_change",
    "new_module",
    "cross_module",
    "stage_jump",
    "parallel_workers",
    "permissions",
    "security",
    "session_recovery",
    "memory",
    "mcp",
    "plugin",
    "distribution",
}


def load_examples() -> list[dict]:
    payload = json.loads(EXAMPLES_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise RuntimeError("examples.json must be a list")
    return [item for item in payload if isinstance(item, dict)]


def classify(example: dict) -> tuple[str, list[str]]:
    candidate_files = example.get("candidate_files")
    tags = example.get("change_tags")
    if not isinstance(candidate_files, list) or not all(isinstance(item, str) for item in candidate_files):
        raise RuntimeError(f"invalid candidate_files for {example.get('id')}")
    if not isinstance(tags, list) or not all(isinstance(item, str) for item in tags):
        raise RuntimeError(f"invalid change_tags for {example.get('id')}")

    reasons: list[str] = []
    if len(candidate_files) > 2:
        reasons.append("more_than_two_files")
    blocked_tags = sorted(tag for tag in tags if tag in REJECT_TAGS)
    reasons.extend(blocked_tags)
    return ("reject" if reasons else "allow", reasons)


def main() -> int:
    examples = load_examples()
    allow_count = 0
    reject_count = 0
    rendered: list[str] = []

    for example in examples:
        example_id = str(example.get("id"))
        expected = example.get("expected_decision")
        if expected not in {"allow", "reject"}:
            raise RuntimeError(f"invalid expected_decision for {example_id}")
        actual, reasons = classify(example)
        if actual != expected:
            raise RuntimeError(
                f"harness-lite example mismatch for {example_id}: expected {expected}, got {actual}, reasons={reasons}"
            )
        if actual == "allow":
            allow_count += 1
        else:
            reject_count += 1
        rendered.append(f"{example_id}: {actual} ({', '.join(reasons) if reasons else 'within_boundary'})")

    if allow_count < 2 or reject_count < 2:
        raise RuntimeError("need at least 2 allow and 2 reject examples for harness-lite boundary validation")

    for line in rendered:
        print(line)
    print(f"harness_lite_examples=OK allow={allow_count} reject={reject_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
