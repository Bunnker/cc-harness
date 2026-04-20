# Compatibility Matrix

## Runtime Compatibility

| Dimension | Format | Current Value | Notes |
|-----------|--------|---------------|-------|
| Pack namespace | string | `cc-harness` | Logical package namespace; runtime skill names remain unprefixed |
| Pack version | semver-ish string | `0.2.0-alpha.0` | Pinned by `skills.lock.json` |
| Pack metadata schema | integer | `1` | Defined by [pack.json](./pack.json) |
| Skill manifest schema | integer | `1` | Defined by [manifest/skills.json](./manifest/skills.json) |
| Activation strategy | enum | `direct_skill_names` | Active skills are copied into `~/.claude/skills/<skill>` |
| Package state root | path | `~/.claude/skill-packs/<namespace>` | Tracks current version, backups, version store |
| Backup strategy | enum | `snapshot_restore` | Pre-upgrade snapshot used by rollback |
| Lock file | path | `skills.lock.json` | Version pin + digest verification |

## Installer Compatibility Rules

| Scenario | Supported | Behavior |
|----------|-----------|----------|
| Fresh install | Yes | Installs current source version and writes pack state |
| Upgrade same namespace | Yes | Creates backup, stores new version, activates it |
| Rollback to previous backup | Yes | Restores runtime skills from snapshot |
| Dry-run install/upgrade | Yes | Prints planned operations without writing |
| Namespace override | Yes | Uses alternate package state root, runtime activation unchanged |
| Source/lock mismatch | No | Installer exits non-zero |
| Prefixing runtime skill folder names | No | Would break `/harness` / `/harness-lite` entrypoints |

## Migration Rules

- Legacy flat install remains readable, but new installs use package state under `~/.claude/skill-packs/<namespace>/`.
- Runtime activation still targets `~/.claude/skills/<skill>` for compatibility with current skill discovery.
- Namespace is package-management metadata, not a runtime folder prefix.
- Rollback only guarantees recovery for skills managed by the same package namespace.
