# Harness Skills Pack

Claude Code 的 **Agent Harness 设计/审计编排体系**，包含 **47 个 skill**（2 个协调器 + 1 个验证 worker + 1 个课程文档生成器 + 43 个可调度 worker）。

Harness 的定位是 **设计/审计 harness，不是实现 harness**：它扫描项目 → 出执行计划 → 等用户确认 → 调度子 Agent 携带 skill 并行构建企业级 Agent 系统。每轮只做一件事：设计、编码、或审计。

---

## 按主题导航

遇到具体问题先查这里，再去看对应 skill：

- **按失败模式找 skill** → [FAILURE-MODES.md](FAILURE-MODES.md) — 15 种失败模式（含 Anthropic 显式命名的 context anxiety / self-eval blind spot / 结构保真 FM-15）× 47 个 skill 的正交视图
- **Anthropic 对齐路线图** → [ANTHROPIC-ALIGNMENT-PLAN.md](ANTHROPIC-ALIGNMENT-PLAN.md) — 原报告 17 项优先级清单状态矩阵 + 每轮改动的 commit / PR 追溯 + 维护规则
- **Harness 进化计划** → [skills/harness/HARNESS_EVOLUTION_PLAN.md](skills/harness/HARNESS_EVOLUTION_PLAN.md) — Meta-Optimization Track M0-M3（可观测 → 可执行 → 候选评估 → 自动搜索）

---

## 安装

Skill 必须放在 **全局** `~/.claude/skills/` 才能跨项目使用。项目级 `.claude/skills/` 只对当前项目可见。

```bash
# Linux / macOS / Git Bash
git clone https://github.com/<your-user>/<this-repo>.git
cd <this-repo>
bash install.sh

# 直接走统一安装器
python scripts/install_skill_pack.py install --source . --lock-file skills.lock.json

# PowerShell
.\install.ps1

# 升级 / 回滚
python scripts/install_skill_pack.py upgrade --source . --lock-file skills.lock.json
python scripts/install_skill_pack.py rollback --namespace cc-harness
```

`install.sh` / `install.ps1` 现在是 `install_skill_pack.py` 的包装器：

- 运行时技能仍激活到 `~/.claude/skills/<skill>`
- 包状态、版本仓库和备份保存在 `~/.claude/skill-packs/<namespace>/`
- 默认使用 `skills.lock.json` 做版本 pin 和源内容校验
- `bash install.sh --dry-run` / `.\install.ps1 --dry-run` 可先预览操作

namespace 是**包管理命名空间**，不是运行时技能目录前缀；这保证 `/harness`、`/harness-lite` 入口不变。

团队 bootstrap 示例见 [bootstrap/team.bootstrap.json](./bootstrap/team.bootstrap.json)，兼容矩阵见 [COMPATIBILITY.md](./COMPATIBILITY.md)。

---

## 使用

```
/harness <项目根目录路径>
```

例：`/harness "D:\ai code\Zero_magic"`

轻量快路径：

```
/harness-lite <项目根目录路径> :: <任务说明>
```

例：`/harness-lite "D:\ai code\Zero_magic" :: 修复 src/cache.ts 的 TTL 计算并补一个单测`

### 工作协议

Harness 是一个 **协调器（Coordinator）**，它的唯一职责是 **Plan → Approve → Execute → Report**：

1. **SCAN** — 读 `.claude/harness-state.json`（如有），跨会话恢复进展；否则探测代码现状
2. **PLAN** — 输出本轮目标、调度的 worker 列表、并行/串行分组、依赖前置
3. **APPROVE** — **硬边界**：用户没说"确认/OK/开始"之前绝不调度任何 worker
4. **EXECUTE** — 用 Agent 工具并发分派 worker，每个 worker 加载对应 skill
5. **REPORT** — 汇总结果、跑验证命令、更新 state、写 trace

**Coordinator 自身禁止做设计/编码/审计**——所有实质工作必须通过 worker 完成，即使只改 1 行代码。

---

## Skill 目录

以下概览由 `manifest/skills.json` 生成。详细调度元数据请查看 [`skills/harness/skill-catalog.md`](skills/harness/skill-catalog.md)。

<!-- GENERATED:SKILL_SUMMARY:START -->

- 总计：`47` 个 skill
- 角色：`44` 个 worker，`3` 个 non-worker
- 可移植性：`30` 个 portable，`17` 个 cc-bound
- 入口模式：`9` 个 direct，`37` 个 orchestrated，`1` 个 internal-only

| 分类 | 数量 | 默认阶段 | 说明 |
|------|------|----------|------|
| 协调层 | 3 | 按 skill 决定 | role=`non-worker` |
| Harness 基础设施层 | 1 | 按 skill 决定 | role=`worker` |
| 基础契约层 | 7 | 阶段 0：契约定义 | role=`worker` |
| Agent 核心层 | 9 | 按 skill 决定 | role=`worker` |
| 能力扩展层 | 8 | 按 skill 决定 | role=`worker` |
| 生产化层 | 5 | 阶段 7：生产化 | role=`worker` |
| 长会话扩展层 | 2 | 阶段 3：长会话支持 | role=`worker` |
| 记忆扩展层 | 2 | 阶段 4：跨会话与记忆 | role=`worker` |
| IDE / 输入扩展层 | 3 | 阶段 5：可扩展性 | role=`worker` |
| 企业 / 生产化扩展层 | 5 | 阶段 8：企业治理 | role=`worker` |
| 方法论 | 2 | 按 skill 决定 | role=`worker` |

详细调度元数据请查看 [`skills/harness/skill-catalog.md`](skills/harness/skill-catalog.md)。

<!-- GENERATED:SKILL_SUMMARY:END -->

---

## Manifest 维护

以下命令用于本地校验入口策略与派生文档：

```bash
python scripts/bootstrap_skill_manifest.py
python scripts/check_skill_exposure.py --fix
python scripts/check_skill_exposure.py
python scripts/validate_manifest_schema.py
python scripts/validate_skill_frontmatter.py
python scripts/generate_manifest_docs.py --check
python scripts/generate_manifest_docs.py
python scripts/generate_pack_lock.py --check
python scripts/validate_harness_lite_examples.py
python scripts/validate_parallel_diff_attribution.py
python scripts/validate_worktree_isolation.py
python scripts/validate_installer_flow.py
python skills/harness/hooks/render-verification-artifacts.py --help
python skills/harness/hooks/run-harness-verify.py --help
python scripts/install_skill_pack.py show-state --namespace cc-harness
```

- `bootstrap_skill_manifest.py`：从现有 skill/frontmatter 与 catalog 迁移出 `manifest/skills.json`
- `check_skill_exposure.py`：校验或同步 `user-invocable` 暴露面
- `validate_manifest_schema.py`：按仓库内 schema 校验 `manifest/skills.json`
- `validate_skill_frontmatter.py`：校验每个 `SKILL.md` 的 frontmatter 规则
- `generate_manifest_docs.py`：从 manifest 生成 README 概览、`skill-catalog.md`、`dependency-graph.md`
- `generate_pack_lock.py`：生成或校验 `skills.lock.json`
- `install_skill_pack.py`：统一安装器，支持 install / upgrade / rollback / bootstrap / show-state
- `validate_harness_lite_examples.py`：校验 `harness-lite` 的 allow/reject 边界样例，防止快路径越权
- `validate_parallel_diff_attribution.py`：回归并发 worker 的 diff 归因，覆盖路径不重叠和路径重叠两类场景
- `validate_worktree_isolation.py`：回归 `isolation: worktree` 流，验证主仓改动不会污染隔离 diff
- `validate_installer_flow.py`：演练 install / upgrade / rollback / bootstrap 冒烟流程
- `render-verification-artifacts.py`：从 trace 目录派生 `verification.md` 和 `scorecard.json`
- `run-harness-verify.py`：标准验证入口，串联 commands、diff、verification、scorecard、failure-reason 生成

---

## 调度规则（依赖与并行）

完整规则在 [`skills/harness/dependency-graph.md`](skills/harness/dependency-graph.md)，速查如下。

### 核心依赖链

```
unified-tool-interface
  ├→ agent-loop ─┬→ context-engineering → agent-resilience
  │              │                       → session-recovery
  │              ├→ agent-memory → agent-reflection
  │              │              → team-memory-sync
  │              └→ multi-agent-design → runtime-summaries
  ├→ layered-permission → command-sandbox
  │                     → plan-mode
  ├→ agent-tool-budget
  ├→ concurrent-dispatch
  └→ plugin-loading

api-client-layer → model-routing
auth-identity → policy-limits / remote-managed-settings / settings-sync / team-memory-sync
context-engineering → compact-system → session-memory
agent-loop + event-hook-system → magic-docs
mcp-runtime + event-hook-system → ide-feedback-loop
harness-entry-points  ← 最后做（依赖所有核心接口）
```

### 无条件安全并行组（同组可同轮分派）

- `[unified-tool-interface, config-cascade, api-client-layer]`
- `[auth-identity, instruction-file-system]`
- `[layered-permission, agent-tool-budget]`
- `[plugin-loading, event-hook-system]`
- `[model-routing, plan-mode]`
- `[startup-optimization, telemetry-pipeline, feature-flag-system]`
- `[team-memory-sync, magic-docs]`
- `[ide-feedback-loop, tip-system, voice-input]`
- `[policy-limits, remote-managed-settings, settings-sync]`
- `[runtime-summaries, platform-integration, voice-input]`

### 条件并行组（设计可并行，编码必须串行）

- `[agent-memory, agent-reflection]`
- `[compact-system, session-memory]`
- `[agent-loop, concurrent-dispatch]`（前置：`unified-tool-interface` 完成）

### 并行决策速查

判断 A 和 B 能否同轮分派：

1. 命中条件并行组？ → 设计可并行 / 编码串行
2. 命中明确依赖链（A → B 或 B → A）？ → **串行**
3. 命中无条件安全并行组？ → **可并行**
4. 操作同一文件/目录？ → **串行**
5. 仍不确定？ → **保守串行**

---

## 状态与 Trace

artifact 命名与最低完整性要求见 [`skills/harness/trace-artifact-contract.md`](skills/harness/trace-artifact-contract.md)。

Harness 在目标项目下维护：

```
<project>/.claude/
├── harness-state.json          # 跨会话进展（current_stage / modules / learnings / denial_tracking）
├── harness-hooks.json          # 可选：自定义 PreScan/PrePlan/PostExecute hook
├── harness-lab/
│   ├── trace-index.json        # 全历史 trace 索引（不删旧轮）
│   ├── worktrees/              # 可选：isolation=worktree 时的隔离副本
│   └── traces/
│       └── <date>-<stage>-<type>/
│           ├── worker-{n}-prompt.md
│           ├── worker-{n}-result.md
│           ├── worker-{n}-worktree.json
│           ├── worker-{n}-diff.patch
│           ├── worker-{n}-diff.json
│           ├── verification.md
│           ├── scorecard.json
│           ├── commands.log
│           └── failure-reason.md  # 仅失败时
```

下次 `/harness` 启动时会读 state，输出"上次进展摘要"，从未完成的模块继续。`learnings` 注入 PLAN 阶段的约束，`cc_adaptations` 注入 worker prompt，避免重复犯错。

---

## 更新流程

源机器更新 skill → 重新打包 → push：

```bash
# 在源机器上重新拷贝最新 skill 进 pack
cp -r ~/.claude/skills/<skill-name> skills/
git add . && git commit -m "Update <skill-name>"
git push
```

目标机器：

```bash
git pull
python scripts/generate_pack_lock.py --check
python scripts/install_skill_pack.py upgrade --source . --lock-file skills.lock.json
```

如果需要回滚：

```bash
python scripts/install_skill_pack.py rollback --namespace cc-harness
```
