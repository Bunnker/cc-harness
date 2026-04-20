#!/usr/bin/env python3
"""Check or sync skill frontmatter exposure against manifest/skills.json."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "manifest" / "skills.json"
SKILL_FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n", re.S)
NAME_PATTERN = re.compile(r"^name:\s*(.+)$", re.M)
USER_INVOCABLE_PATTERN = re.compile(r"^user-invocable:\s*(true|false)$", re.M)


def load_manifest() -> dict[str, object]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def parse_frontmatter(skill_file: Path) -> tuple[str | None, bool | None]:
    text = skill_file.read_text(encoding="utf-8")
    block_match = SKILL_FRONTMATTER.search(text)
    if not block_match:
        return None, None
    block = block_match.group(1)

    name_match = NAME_PATTERN.search(block)
    user_invocable_match = USER_INVOCABLE_PATTERN.search(block)
    name = name_match.group(1).strip() if name_match else None
    user_invocable = None
    if user_invocable_match:
        user_invocable = user_invocable_match.group(1) == "true"
    return name, user_invocable


def sync_frontmatter(skill_file: Path, user_invocable: bool) -> bool:
    text = skill_file.read_text(encoding="utf-8")
    replacement = f"user-invocable: {'true' if user_invocable else 'false'}"
    updated = USER_INVOCABLE_PATTERN.sub(replacement, text, count=1)
    if updated == text:
        return False
    skill_file.write_text(updated, encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fix", action="store_true", help="rewrite SKILL.md frontmatter to match manifest")
    args = parser.parse_args()

    manifest = load_manifest()
    skill_map = {skill["name"]: skill for skill in manifest["skills"]}
    counts = Counter(skill["default_invocation_mode"] for skill in manifest["skills"])
    errors: list[str] = []
    updated_files: list[Path] = []

    for skill_name, skill in sorted(skill_map.items()):
        skill_file = REPO_ROOT / skill["path"] / "SKILL.md"
        if not skill_file.exists():
            errors.append(f"{skill_name}: missing {skill_file}")
            continue

        frontmatter_name, user_invocable = parse_frontmatter(skill_file)
        if frontmatter_name != skill_name:
            errors.append(f"{skill_name}: frontmatter name mismatch ({frontmatter_name!r})")

        if user_invocable is None:
            errors.append(f"{skill_name}: missing user-invocable in frontmatter")
            continue

        expected = bool(skill["user_invocable"])
        if user_invocable != expected:
            if args.fix:
                if sync_frontmatter(skill_file, expected):
                    updated_files.append(skill_file)
            else:
                errors.append(
                    f"{skill_name}: user-invocable is {user_invocable} but manifest expects {expected}"
                )

    if args.fix:
        for path in updated_files:
            print(f"updated {path.relative_to(REPO_ROOT).as_posix()}")
        print(
            "Exposure sync completed: "
            f"{counts['direct']} direct, {counts['orchestrated']} orchestrated, {counts['internal_only']} internal-only"
        )
        return 0

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(
            "Exposure check failed: "
            f"{counts['direct']} direct, {counts['orchestrated']} orchestrated, {counts['internal_only']} internal-only",
            file=sys.stderr,
        )
        return 1

    print(
        "Exposure check passed: "
        f"{counts['direct']} direct, {counts['orchestrated']} orchestrated, {counts['internal_only']} internal-only"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
