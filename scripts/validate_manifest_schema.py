#!/usr/bin/env python3
"""Validate the pack manifest against the repository schema without external dependencies."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def ensure(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    schema = load_json(REPO_ROOT / "manifest" / "skills.schema.json")
    manifest = load_json(REPO_ROOT / "manifest" / "skills.json")

    required_top = schema.get("required", [])
    for key in required_top:
        ensure(key in manifest, f"manifest missing required top-level key: {key}")

    ensure(isinstance(manifest.get("version"), int), "manifest.version must be an integer")
    ensure(isinstance(manifest.get("skills"), list), "manifest.skills must be a list")

    category_schema = schema["$defs"]["category"]
    skill_schema = schema["$defs"]["skill"]
    category_required = category_schema["required"]
    skill_required = skill_schema["required"]
    category_role_enum = set(category_schema["properties"]["role"]["enum"])
    portability_enum = set(skill_schema["properties"]["portability"]["enum"])
    invocation_enum = set(skill_schema["properties"]["default_invocation_mode"]["enum"])
    category_ids: set[str] = set()

    ensure(isinstance(manifest.get("categories"), list), "manifest.categories must be a list")
    for index, item in enumerate(manifest["categories"]):
        ensure(isinstance(item, dict), f"manifest.categories[{index}] must be an object")
        for key in category_required:
            ensure(key in item, f"manifest.categories[{index}] missing required key: {key}")
        category_id = item["id"]
        ensure(isinstance(category_id, str) and category_id, f"manifest.categories[{index}].id must be a non-empty string")
        ensure(category_id not in category_ids, f"duplicate category id in manifest: {category_id}")
        category_ids.add(category_id)
        ensure(item["role"] in category_role_enum, f"invalid category role for {category_id}: {item['role']}")

    seen_names: set[str] = set()
    for index, item in enumerate(manifest["skills"]):
        ensure(isinstance(item, dict), f"manifest.skills[{index}] must be an object")
        for key in skill_required:
            ensure(key in item, f"manifest.skills[{index}] missing required key: {key}")
        name = item["name"]
        ensure(isinstance(name, str) and name, f"manifest.skills[{index}].name must be a non-empty string")
        ensure(name not in seen_names, f"duplicate skill name in manifest: {name}")
        seen_names.add(name)
        ensure(item.get("category") in category_ids, f"invalid category for {name}: {item.get('category')}")
        ensure(item["portability"] in portability_enum, f"invalid portability for {name}: {item['portability']}")
        ensure(
            item["default_invocation_mode"] in invocation_enum,
            f"invalid default_invocation_mode for {name}: {item['default_invocation_mode']}",
        )
        ensure(isinstance(item.get("purpose"), str) and item["purpose"], f"purpose missing for {name}")
        ensure(isinstance(item.get("path"), str) and item["path"], f"path missing for {name}")
        ensure(item.get("parallel_mode") in {"always", "design_only", "never", "contextual"}, f"invalid parallel_mode for {name}")
        ensure(isinstance(item.get("user_invocable"), bool), f"user_invocable must be boolean for {name}")

    print("Manifest schema validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
