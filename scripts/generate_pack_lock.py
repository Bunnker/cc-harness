#!/usr/bin/env python3
"""Generate or validate the package lock file for cc-harness."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--output")
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def hash_tree(root: Path) -> str:
    digest = hashlib.sha256()
    files = sorted(
        ((path.relative_to(root).as_posix(), path) for path in root.rglob("*") if path.is_file()),
        key=lambda item: item[0],
    )
    for relative_text, path in files:
        relative = relative_text.encode("utf-8")
        digest.update(relative)
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def build_lock(repo_root: Path) -> dict[str, Any]:
    pack = load_json(repo_root / "pack.json")
    namespace = pack["namespace"]
    version = pack["version"]
    skills_dir = repo_root / pack.get("skills_dir", "skills")
    manifest_path = repo_root / pack.get("manifest_path", "manifest/skills.json")
    manifest = load_json(manifest_path)
    skill_items = manifest.get("skills", [])
    direct_entrypoints = sorted(
        item["name"]
        for item in skill_items
        if isinstance(item, dict) and item.get("default_invocation_mode") == "direct"
    )
    return {
        "schema_version": 1,
        "pack": {
            "name": pack["name"],
            "namespace": namespace,
            "version": version,
            "manifest_version": manifest.get("version"),
            "skill_count": len(skill_items),
            "direct_entrypoints": direct_entrypoints,
            "manifest_sha256": sha256_bytes(manifest_path.read_bytes()),
            "skills_tree_sha256": hash_tree(skills_dir),
        },
    }


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    pack = load_json(repo_root / "pack.json")
    output_path = Path(args.output).resolve() if args.output else repo_root / pack.get("lock_file", "skills.lock.json")
    expected = build_lock(repo_root)
    if args.check:
        current = load_json(output_path)
        if current != expected:
            raise SystemExit(f"Lock file drift detected: {output_path}")
        print("Pack lock validation passed.")
        return 0
    output_path.write_text(json.dumps(expected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
