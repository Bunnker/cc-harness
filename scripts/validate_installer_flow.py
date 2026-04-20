#!/usr/bin/env python3
"""Smoke test install, upgrade, rollback, and bootstrap flows for the skill pack installer."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALLER = REPO_ROOT / "scripts" / "install_skill_pack.py"
LOCK_GENERATOR = REPO_ROOT / "scripts" / "generate_pack_lock.py"


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


def create_pack(root: Path, *, version: str, with_beta: bool) -> None:
    (root / "skills" / "alpha").mkdir(parents=True, exist_ok=True)
    (root / "manifest").mkdir(parents=True, exist_ok=True)
    (root / "skills" / "alpha" / "SKILL.md").write_text(
        f"---\nname: alpha\ndescription: alpha {version}\nuser-invocable: true\n---\n\n# alpha {version}\n",
        encoding="utf-8",
    )
    skills = [
        {
            "name": "alpha",
            "role": "non-worker",
            "portability": "portable",
            "description": f"alpha {version}",
            "category": "coordination",
            "default_invocation_mode": "direct",
        }
    ]
    if with_beta:
        (root / "skills" / "beta").mkdir(parents=True, exist_ok=True)
        (root / "skills" / "beta" / "SKILL.md").write_text(
            f"---\nname: beta\ndescription: beta {version}\nuser-invocable: false\n---\n\n# beta {version}\n",
            encoding="utf-8",
        )
        skills.append(
            {
                "name": "beta",
                "role": "worker",
                "portability": "portable",
                "description": f"beta {version}",
                "category": "worker",
                "default_invocation_mode": "orchestrated",
            }
        )

    write_json(
        root / "pack.json",
        {
            "schema_version": 1,
            "name": "demo-pack",
            "namespace": "demo-pack",
            "version": version,
            "skills_dir": "skills",
            "manifest_path": "manifest/skills.json",
            "lock_file": "skills.lock.json",
            "installer": {
                "runtime_relative_dir": ".claude/skills",
                "state_relative_dir": ".claude/skill-packs",
                "activation_strategy": "direct_skill_names",
                "backup_strategy": "snapshot_restore",
                "supports": ["dry_run", "upgrade", "rollback", "version_pin", "namespace_install", "bootstrap"],
            },
        },
    )
    write_json(root / "manifest" / "skills.json", {"version": 1, "skills": skills})
    run([sys.executable, str(LOCK_GENERATOR), "--repo-root", str(root)])


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="installer-flow-") as temp_dir:
        temp_root = Path(temp_dir)
        home = temp_root / "home"
        src_v1 = temp_root / "src-v1"
        src_v2 = temp_root / "src-v2"
        create_pack(src_v1, version="0.1.0", with_beta=False)
        create_pack(src_v2, version="0.2.0", with_beta=True)

        dry_run = run(
            [
                sys.executable,
                str(INSTALLER),
                "install",
                "--source",
                str(src_v1),
                "--home",
                str(home),
                "--lock-file",
                str(src_v1 / "skills.lock.json"),
                "--dry-run",
            ]
        )
        assert "\"action\": \"install\"" in dry_run.stdout
        assert not (home / ".claude" / "skills" / "alpha").exists()

        run(
            [
                sys.executable,
                str(INSTALLER),
                "install",
                "--source",
                str(src_v1),
                "--home",
                str(home),
                "--lock-file",
                str(src_v1 / "skills.lock.json"),
            ]
        )
        assert (home / ".claude" / "skills" / "alpha" / "SKILL.md").exists()
        current_state = read_json(home / ".claude" / "skill-packs" / "demo-pack" / "current.json")
        assert current_state["active_version"] == "0.1.0"

        run(
            [
                sys.executable,
                str(INSTALLER),
                "upgrade",
                "--source",
                str(src_v2),
                "--home",
                str(home),
                "--lock-file",
                str(src_v2 / "skills.lock.json"),
            ]
        )
        assert (home / ".claude" / "skills" / "alpha" / "SKILL.md").read_text(encoding="utf-8").find("0.2.0") != -1
        assert (home / ".claude" / "skills" / "beta" / "SKILL.md").exists()
        upgraded_state = read_json(home / ".claude" / "skill-packs" / "demo-pack" / "current.json")
        assert upgraded_state["active_version"] == "0.2.0"

        run(
            [
                sys.executable,
                str(INSTALLER),
                "rollback",
                "--home",
                str(home),
                "--namespace",
                "demo-pack",
            ]
        )
        rolled_back_alpha = (home / ".claude" / "skills" / "alpha" / "SKILL.md").read_text(encoding="utf-8")
        assert "0.1.0" in rolled_back_alpha
        assert not (home / ".claude" / "skills" / "beta").exists()

        bootstrap_config = src_v2 / "bootstrap.json"
        write_json(
            bootstrap_config,
            {
                "schema_version": 1,
                "namespace": "demo-pack",
                "mode": "upgrade",
                "source": ".",
                "lock_file": "skills.lock.json",
                "version": "0.2.0",
            },
        )
        run(
            [
                sys.executable,
                str(INSTALLER),
                "bootstrap",
                "--config",
                str(bootstrap_config),
                "--home",
                str(home),
            ]
        )
        bootstrapped_state = read_json(home / ".claude" / "skill-packs" / "demo-pack" / "current.json")
        assert bootstrapped_state["active_version"] == "0.2.0"
        assert (home / ".claude" / "skills" / "beta").exists()

    print("installer_flow=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
