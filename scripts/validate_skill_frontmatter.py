#!/usr/bin/env python3
"""Validate basic frontmatter rules for all SKILL.md files."""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
FIELD_PATTERN = re.compile(r"^([A-Za-z0-9_-]+):\s*(.+)$", re.MULTILINE)


def parse_frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    match = SKILL_FRONTMATTER.match(text)
    if not match:
        raise RuntimeError(f"missing frontmatter: {path}")
    fields: dict[str, str] = {}
    for key, raw_value in FIELD_PATTERN.findall(match.group(1)):
        fields[key] = raw_value.strip().strip('"')
    return fields


def ensure(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    skills_root = REPO_ROOT / "skills"
    for skill_dir in sorted(path for path in skills_root.iterdir() if path.is_dir()):
        skill_path = skill_dir / "SKILL.md"
        ensure(skill_path.exists(), f"missing SKILL.md: {skill_path}")
        fields = parse_frontmatter(skill_path)
        ensure(fields.get("name") == skill_dir.name, f"name/frontmatter mismatch: {skill_dir.name}")
        ensure("description" in fields and fields["description"], f"description missing for {skill_dir.name}")
        if "user-invocable" in fields:
            ensure(fields["user-invocable"] in {"true", "false"}, f"user-invocable must be boolean for {skill_dir.name}")
        if "disable-model-invocation" in fields:
            ensure(
                fields["disable-model-invocation"] in {"true", "false"},
                f"disable-model-invocation must be boolean for {skill_dir.name}",
            )
    print("Skill frontmatter validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
