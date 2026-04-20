# Trace Artifact Contract

> 目标：把 `harness-lab/traces/` 从“约定俗成的文件夹”收敛成可校验的 artifact 契约。

## 目录结构

```text
.claude/harness-lab/traces/{date}-{stage}[-{task_type}]/
├── worker-{n}-prompt.md
├── worker-{n}-result.md
├── worker-{n}-worktree.json  # 可选：isolation=worktree 时
├── worker-{n}-diff.patch
├── worker-{n}-diff.json
├── commands.log
├── verification.md
├── scorecard.json
└── failure-reason.md      # 仅失败时
```

## 命名规则

- `worker-{n}-prompt.md`
  保存发送给 worker 的完整 prompt 快照。
- `worker-{n}-result.md`
  保存 worker 的完整最终回复。
- `worker-{n}-worktree.json`
  可选。记录隔离 worktree 的路径、baseline、cleanup 状态与 target_paths。
- `worker-{n}-diff.patch`
  只包含该 worker 的 `target_paths` 范围内 diff。
- `worker-{n}-diff.json`
  保存结构化 diff 元数据，包括 `touched_files`、`numstat`、`path_violation_candidates`。
- `commands.log`
  保存 verification 阶段实际执行过的标准命令及原始输出。
- `verification.md`
  面向人读的验证摘要。
- `scorecard.json`
  面向程序消费的评分输出。
- `failure-reason.md`
  仅在失败轮次出现，记录失败分类和阻断原因。

## `failure-reason.md` 最低结构

推荐由 `skills/harness/hooks/run-harness-verify.py` 或
`skills/harness/hooks/render-verification-artifacts.py` 自动生成，而不是手写。

```markdown
## 失败归因 — {date} {stage}

### 阻断项
### 评分回退
### 失败命令
### Worker 异常
### 恢复建议
```

要求：

- 只有失败/低分轮次才写入，成功轮次应删除旧的 `failure-reason.md`
- 至少包含一个明确阻断项，不能只写泛化结论
- 失败命令应引用 `commands.log` 中的真实 `exit_code` / `failure_kind` / `duration_ms`
- 如果失败发生在 verification bundle 生成前，也必须记录失败步骤和原始输出

## `commands.log` 格式

每条命令必须是一个完整块：

```text
=== {command_name} ===
$ {command_text}
context: {string}
category: {string | not_configured}
target_paths: {path_a | path_b | not_configured}
started_at: {ISO8601}
finished_at: {ISO8601}
duration_ms: {integer}
timeout_s: {integer | not_configured}
failure_kind: {none | nonzero_exit | timeout | spawn_error}
{stdout/stderr 完整输出}
exit_code: {integer}
```

要求：

- `command_name` 必须稳定，可用于后续解析。
- `command_text` 必须是实际执行命令，不是摘要。
- `duration_ms` 必须基于真实执行时间，而不是估算。
- 输出保留原始 `stdout/stderr` 顺序，不做摘要化截断。
- `failure_kind` 用于区分普通失败、超时和命令无法启动。

## `worker-{n}-diff.patch` 格式

文件头必须包含：

```text
=== worker-{n} diff ===
baseline: {commit}
target_paths: {path_a} {path_b}
capture_source: {project_worktree | worker_worktree}
```

正文顺序固定：

1. `git diff --stat`
2. 空行
3. `git diff`

## `worker-{n}-worktree.json` 最低字段

```json
{
  "worker": "1",
  "prepared_at": "ISO8601",
  "project_path": "/repo",
  "trace_dir": "/repo/.claude/harness-lab/traces/...",
  "baseline": "commit",
  "isolation": "worktree",
  "reason": "conflict_isolation",
  "target_paths": ["src/a.ts"],
  "worktree_path": "/repo/.claude/harness-lab/worktrees/.../worker-1",
  "cleanup_status": "prepared"
}
```

要求：

- `worktree_path` 必须位于 `<project>/.claude/harness-lab/worktrees/` 下
- `cleanup_status` 至少支持 `prepared` / `removed` / `missing`
- `prepare-worker-isolation.py` 应写入该文件，`cleanup-worker-isolation.py` 或 `run-harness-verify.py --cleanup-worktrees` 应更新它

## `worker-{n}-diff.json` 最低字段

```json
{
  "worker": "1",
  "captured_at": "ISO8601",
  "baseline": "commit",
  "scope_mode": "target_paths",
  "capture_source": "worker_worktree",
  "attribution_confidence": "high",
  "target_paths": ["src/a.ts"],
  "peer_owned_paths": ["src/b.ts"],
  "scoped_changed_files": ["src/a.ts"],
  "all_changed_files": ["src/a.ts", "README.md"],
  "peer_owned_changed_files": ["src/b.ts"],
  "path_violation_candidates": ["README.md"],
  "numstat": [
    { "path": "src/a.ts", "added": 10, "deleted": 2 }
  ],
  "notes": []
}
```

要求：

- `scope_mode` 只能是 `target_paths` 或 `global_fallback`。
- `capture_source` 目前只能是 `project_worktree` 或 `worker_worktree`。
- `attribution_confidence` 目前只能是 `high` 或 `low`。
- `peer_owned_changed_files` 用于排除同轮其他 Worker 的已知合法改动，避免把并发安全场景误判成越界。
- `path_violation_candidates` 是候选告警，不等于最终归责。
- `numstat` 必须与 patch 中的 `git diff --stat` 对应。

## `verification.md` 最低结构

推荐由 `skills/harness/hooks/render-verification-artifacts.py` 从 trace 目录派生生成，而不是手写。

```markdown
## 验证结果 — {date} {stage}

### 单 Worker 验证
### 跨 Worker 兼容性
### 运行时不变式
### 失败摘要
```

如果某部分不适用，也必须显式写 `not_applicable`，避免隐式缺失。

## `scorecard.json` 最低字段

推荐由 `skills/harness/hooks/render-verification-artifacts.py` 与 `verification.md` 同时生成。

```json
{
  "date": "YYYY-MM-DD",
  "stage": "stage-x",
  "project": "name",
  "dimensions": {
    "build_lint_typecheck": { "score": 1.0, "detail": "..." },
    "smoke_tests": { "score": 1.0, "detail": "..." },
    "runtime_invariants": { "score": 1.0, "detail": "..." },
    "structural_fidelity": { "score": 1.0, "detail": "..." },
    "verification_coverage": { "score": 1.0, "detail": "..." }
  },
  "composite_score": 1.0,
  "trace_path": "harness-lab/traces/..."
}
```

要求：

- 不适用维度用 `score: null`，不要省略字段。
- `composite_score` 只能基于适用维度计算。
- `trace_path` 必须指向当前轮次 trace 目录。

## 最低完整性要求

### 设计轮

至少要有：

- `worker-{n}-prompt.md`
- `worker-{n}-result.md`
- `verification.md`
- `scorecard.json`

### 编码 / 审计轮

必须额外包含：

- `commands.log`
- 每个 worker 的 `worker-{n}-diff.patch`
- 每个 worker 的 `worker-{n}-diff.json`

## 阻断条件

以下情况应视为 trace 不完整：

- `commands.log` 存在，但没有 `duration_ms` 或 `exit_code`
- `worker-{n}-diff.patch` 缺少 `baseline` 或 `target_paths`
- `worker-{n}-diff.json` 缺少 `scope_mode` 或 `numstat`
- `scorecard.json` 缺少 `composite_score`
- 编码轮没有 `commands.log`
- 有 `worker-{n}-result.md`，但没有对应 `worker-{n}-diff.patch` 或 `worker-{n}-diff.json`
