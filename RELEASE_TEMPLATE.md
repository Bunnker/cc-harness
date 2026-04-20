# Release Note Template

## Summary

- Pack: `cc-harness`
- Namespace: `cc-harness`
- Version: `{version}`
- Release date: `{date}`

## Changes

- Added:
- Changed:
- Removed:
- Fixed:

## Compatibility

- Manifest schema: `{manifest_version}`
- Runtime activation strategy: `direct_skill_names`
- Lock file updated: `{yes|no}`
- Installer migration note: `{note}`

## Validation

- `python scripts/generate_pack_lock.py --check`
- `python scripts/check_skill_exposure.py`
- `python scripts/generate_manifest_docs.py --check`
- `python scripts/validate_harness_lite_examples.py`
- `python scripts/validate_parallel_diff_attribution.py`
- `python scripts/validate_worktree_isolation.py`
- `python scripts/validate_installer_flow.py`

## Rollout

- Upgrade command:
  `python scripts/install_skill_pack.py upgrade --source . --lock-file skills.lock.json`
- Rollback command:
  `python scripts/install_skill_pack.py rollback --namespace cc-harness`

## Notes

- User-facing migration guidance:
- Team bootstrap impact:
