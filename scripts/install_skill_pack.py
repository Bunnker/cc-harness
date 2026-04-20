#!/usr/bin/env python3
"""Install, upgrade, rollback, and bootstrap cc-harness skill packs."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PACK_FILE = "pack.json"


def now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name in ("install", "upgrade"):
        sub = subparsers.add_parser(name)
        sub.add_argument("--source", required=True)
        sub.add_argument("--home")
        sub.add_argument("--namespace")
        sub.add_argument("--version")
        sub.add_argument("--lock-file")
        sub.add_argument("--dry-run", action="store_true")

    rollback = subparsers.add_parser("rollback")
    rollback.add_argument("--home")
    rollback.add_argument("--namespace", required=True)
    rollback.add_argument("--backup-id")
    rollback.add_argument("--dry-run", action="store_true")

    bootstrap = subparsers.add_parser("bootstrap")
    bootstrap.add_argument("--config", required=True)
    bootstrap.add_argument("--home")
    bootstrap.add_argument("--dry-run", action="store_true")

    show_state = subparsers.add_parser("show-state")
    show_state.add_argument("--home")
    show_state.add_argument("--namespace", required=True)

    return parser.parse_args()


def resolve_home(home_arg: str | None) -> Path:
    return Path(home_arg).expanduser().resolve() if home_arg else Path.home().resolve()


def load_pack_metadata(source_root: Path) -> dict[str, Any]:
    metadata_path = source_root / PACK_FILE
    if not metadata_path.exists():
        raise RuntimeError(f"pack metadata not found: {metadata_path}")
    payload = load_json(metadata_path)
    required = {"schema_version", "name", "namespace", "version", "skills_dir"}
    missing = sorted(required - payload.keys())
    if missing:
        raise RuntimeError(f"pack metadata missing keys: {', '.join(missing)}")
    return payload


def pack_paths(home: Path, namespace: str, metadata: dict[str, Any] | None = None) -> dict[str, Path]:
    runtime_relative = ".claude/skills"
    state_relative = ".claude/skill-packs"
    if metadata:
        installer = metadata.get("installer", {})
        if isinstance(installer, dict):
            runtime_relative = installer.get("runtime_relative_dir", runtime_relative)
            state_relative = installer.get("state_relative_dir", state_relative)

    runtime_dir = home / Path(runtime_relative)
    state_root = home / Path(state_relative) / namespace
    return {
        "runtime_dir": runtime_dir,
        "state_root": state_root,
        "versions_root": state_root / "versions",
        "backups_root": state_root / "backups",
        "current_state": state_root / "current.json",
    }


def skill_names(source_root: Path, metadata: dict[str, Any]) -> list[str]:
    skills_dir = source_root / metadata["skills_dir"]
    if not skills_dir.exists():
        raise RuntimeError(f"skills dir not found: {skills_dir}")
    return sorted(path.name for path in skills_dir.iterdir() if path.is_dir())


def load_and_validate_lock(lock_path: Path, metadata: dict[str, Any], source_root: Path) -> dict[str, Any]:
    payload = load_json(lock_path)
    pack_lock = payload.get("pack", {})
    if pack_lock.get("namespace") != metadata["namespace"]:
        raise RuntimeError(f"lock namespace mismatch: {pack_lock.get('namespace')} != {metadata['namespace']}")
    if pack_lock.get("version") != metadata["version"]:
        raise RuntimeError(f"lock version mismatch: {pack_lock.get('version')} != {metadata['version']}")

    from generate_pack_lock import build_lock  # type: ignore

    computed = build_lock(source_root)
    if payload != computed:
        raise RuntimeError(f"lock digest mismatch: {lock_path}")
    return payload


def copy_tree(src: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)


def snapshot_runtime(runtime_dir: Path, skills: list[str], backup_root: Path, previous_state: dict[str, Any] | None) -> dict[str, Any]:
    backup_skills_dir = backup_root / "runtime-skills"
    backup_skills_dir.mkdir(parents=True, exist_ok=True)
    absent: list[str] = []
    present: list[str] = []
    for skill in skills:
        runtime_skill = runtime_dir / skill
        if runtime_skill.exists():
            copy_tree(runtime_skill, backup_skills_dir / skill)
            present.append(skill)
        else:
            absent.append(skill)
    metadata = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "present_skills": present,
        "absent_skills": absent,
        "previous_state": previous_state,
    }
    write_json(backup_root / "backup.json", metadata)
    return metadata


def activate_version(source_root: Path, metadata: dict[str, Any], version_store: Path, runtime_dir: Path, skills: list[str]) -> None:
    source_skills_dir = source_root / metadata["skills_dir"]
    version_store.mkdir(parents=True, exist_ok=True)
    copy_tree(source_skills_dir, version_store / "skills")
    runtime_dir.mkdir(parents=True, exist_ok=True)
    for skill in skills:
        copy_tree(version_store / "skills" / skill, runtime_dir / skill)


def perform_install_or_upgrade(
    *,
    action: str,
    source_root: Path,
    home: Path,
    namespace_override: str | None,
    version_constraint: str | None,
    lock_path: Path | None,
    dry_run: bool,
) -> None:
    metadata = load_pack_metadata(source_root)
    namespace = namespace_override or metadata["namespace"]
    if version_constraint and version_constraint != metadata["version"]:
        raise RuntimeError(f"version mismatch: requested {version_constraint}, source has {metadata['version']}")
    paths = pack_paths(home, namespace, metadata)
    current_state_path = paths["current_state"]
    previous_state = load_json(current_state_path) if current_state_path.exists() else None
    if action == "upgrade" and previous_state is None:
        raise RuntimeError(f"cannot upgrade before install for namespace {namespace}")

    lock_payload = None
    if lock_path:
        lock_payload = load_and_validate_lock(lock_path, metadata, source_root)

    skills = skill_names(source_root, metadata)
    backup_id = now_stamp()
    backup_root = paths["backups_root"] / backup_id
    version_store = paths["versions_root"] / metadata["version"]

    planned = {
        "action": action,
        "namespace": namespace,
        "version": metadata["version"],
        "runtime_dir": str(paths["runtime_dir"]),
        "version_store": str(version_store),
        "backup_root": str(backup_root),
        "skills": skills,
        "lock_file": str(lock_path) if lock_path else None,
    }
    if dry_run:
        print(json.dumps(planned, ensure_ascii=False, indent=2))
        return

    paths["state_root"].mkdir(parents=True, exist_ok=True)
    snapshot_runtime(paths["runtime_dir"], skills, backup_root, previous_state)
    activate_version(source_root, metadata, version_store, paths["runtime_dir"], skills)

    current_state = {
        "schema_version": 1,
        "namespace": namespace,
        "pack_name": metadata["name"],
        "active_version": metadata["version"],
        "installed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "installed_from": str(source_root),
        "skill_names": skills,
        "last_action": action,
        "last_backup_id": backup_id,
        "lock_file": str(lock_path) if lock_path else None,
        "lock_summary": lock_payload["pack"] if isinstance(lock_payload, dict) else None,
    }
    write_json(current_state_path, current_state)
    print(f"{action.capitalize()}ed {len(skills)} skills for namespace {namespace} -> {paths['runtime_dir']}")


def perform_rollback(*, home: Path, namespace: str, backup_id: str | None, dry_run: bool) -> None:
    paths = pack_paths(home, namespace)
    current_state_path = paths["current_state"]
    if not current_state_path.exists():
        raise RuntimeError(f"no installed state found for namespace {namespace}")
    current_state = load_json(current_state_path)

    backups_root = paths["backups_root"]
    candidate = backups_root / backup_id if backup_id else None
    if candidate and not candidate.exists():
        raise RuntimeError(f"backup not found: {candidate}")
    if candidate is None:
        backups = sorted(path for path in backups_root.iterdir() if path.is_dir())
        if not backups:
            raise RuntimeError(f"no backups available for namespace {namespace}")
        candidate = backups[-1]

    backup_meta = load_json(candidate / "backup.json")
    present_skills = backup_meta.get("present_skills", [])
    absent_skills = backup_meta.get("absent_skills", [])
    skills = sorted(set(current_state.get("skill_names", [])) | set(present_skills) | set(absent_skills))

    planned = {
        "action": "rollback",
        "namespace": namespace,
        "backup_id": candidate.name,
        "runtime_dir": str(paths["runtime_dir"]),
        "skills": skills,
    }
    if dry_run:
        print(json.dumps(planned, ensure_ascii=False, indent=2))
        return

    runtime_dir = paths["runtime_dir"]
    runtime_dir.mkdir(parents=True, exist_ok=True)
    for skill in skills:
        runtime_skill = runtime_dir / skill
        backup_skill = candidate / "runtime-skills" / skill
        if backup_skill.exists():
            copy_tree(backup_skill, runtime_skill)
        elif runtime_skill.exists():
            shutil.rmtree(runtime_skill)

    previous_state = backup_meta.get("previous_state")
    if previous_state:
        previous_state["rolled_back_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        previous_state["last_action"] = "rollback"
        previous_state["last_backup_id"] = candidate.name
        write_json(current_state_path, previous_state)
    else:
        current_state_path.unlink(missing_ok=True)
    print(f"Rolled back namespace {namespace} using backup {candidate.name}")


def perform_bootstrap(config_path: Path, home_override: str | None, dry_run: bool) -> None:
    config = load_json(config_path)
    mode = config.get("mode", "install")
    if mode not in {"install", "upgrade"}:
        raise RuntimeError(f"unsupported bootstrap mode: {mode}")
    source_root = (config_path.parent / config.get("source", "..")).resolve()
    lock_file = config.get("lock_file")
    lock_path = (config_path.parent / lock_file).resolve() if isinstance(lock_file, str) else None
    perform_install_or_upgrade(
        action=mode,
        source_root=source_root,
        home=resolve_home(home_override),
        namespace_override=config.get("namespace"),
        version_constraint=config.get("version"),
        lock_path=lock_path,
        dry_run=dry_run or bool(config.get("dry_run")),
    )


def show_state(home: Path, namespace: str) -> None:
    current_state = pack_paths(home, namespace)["current_state"]
    if not current_state.exists():
        raise RuntimeError(f"no state found for namespace {namespace}")
    print(json.dumps(load_json(current_state), ensure_ascii=False, indent=2))


def main() -> int:
    args = parse_args()
    if args.command in {"install", "upgrade"}:
        perform_install_or_upgrade(
            action=args.command,
            source_root=Path(args.source).resolve(),
            home=resolve_home(args.home),
            namespace_override=args.namespace,
            version_constraint=args.version,
            lock_path=Path(args.lock_file).resolve() if args.lock_file else None,
            dry_run=args.dry_run,
        )
        return 0
    if args.command == "rollback":
        perform_rollback(
            home=resolve_home(args.home),
            namespace=args.namespace,
            backup_id=args.backup_id,
            dry_run=args.dry_run,
        )
        return 0
    if args.command == "bootstrap":
        perform_bootstrap(Path(args.config).resolve(), args.home, args.dry_run)
        return 0
    if args.command == "show-state":
        show_state(resolve_home(args.home), args.namespace)
        return 0
    raise RuntimeError(f"unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
