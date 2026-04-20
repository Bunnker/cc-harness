# Anthropic Alignment Plan

> 基于 2026-04-17 对 Anthropic 5 篇官方 harness 文档的审视，对本仓 47 skill 做系统性对齐。本文件为前三轮的总结与后续工作的路线图。

## 一、已完成的 3 轮（2026-04-17）

### R1 · 内容对齐（commit `e7823ff`）
6 个 skill 精准插入，闭合 Codex 核实的 gap（+357/-5）：

| Skill | 插入点 | 闭合 gap |
|-------|--------|---------|
| [eval-driven-design](skills/eval-driven-design/SKILL.md) | Step 6-8 | 轨迹 vs 端态、pass@k vs pass^k、online/offline |
| [multi-agent-design](skills/multi-agent-design/SKILL.md) | §角色分层 | P/G/E 三角色 + Sprint Contract |
| [agent-resilience](skills/agent-resilience/SKILL.md) | §7 | Context Anxiety 失败模式 + 3 锚点策略 |
| [agent-reflection](skills/agent-reflection/SKILL.md) | §7 | Self-Eval Blind Spot + Evaluator 校准模板 |
| [architecture-invariants](skills/architecture-invariants/SKILL.md) | 四、ASM | Assumption Registry + 4 prune 触发信号 |
| [harness](skills/harness/SKILL.md) | §核心循环 | 外层 Plan/Approve/Execute/Report × 内层 gather/act/verify |

### R2 · 导航层（commit `258a512`）
新文件 [FAILURE-MODES.md](FAILURE-MODES.md)：47 skill 按 14 种失败模式分类，Anthropic 显式命名的 2 大失败模式（context anxiety / self-eval blind spot）领头。

### R3 · 长运行交接（commit `b0d1790`）
[multi-agent-design](skills/multi-agent-design/SKILL.md) §角色分层 新增 3 子节：
- 5 步启动仪式（pwd → git log → progress → feature_list → init.sh）
- 工件冲突仲裁规则（git 优先于 narrative）
- One-feature-at-a-time（Generator 只能推到 `ready_for_review`）
- Sprint 末客观自检边界（禁止主观夸奖，显式链接 self-eval blind spot）

## 二、原报告 17 项优先级清单 · 状态矩阵

| # | 类别 | 项 | 状态 | 落位 |
|---|------|---|------|------|
| P0 1 | Loop | gather/act/verify + 中断 | ✅ | agent-loop, harness §核心循环 |
| P0 2 | Tool | <20 + defer + ACI | ✅ | tool-authoring, agent-tool-budget |
| P0 3 | 权限 | 3+ tier + 外部副作用必问 | ✅ | layered-permission, command-sandbox |
| P0 4 | Session | JSONL + 快照 + resume/fork | ✅ | session-recovery |
| P0 5 | Compact | 或 context-reset | ✅ | compact-system |
| P1 6 | Subagent | 独立 context + 摘要回传 | ✅ | multi-agent-design |
| P1 7 | Memory | 分层 + 索引常驻 | ✅ | agent-memory |
| P1 8 | Artifacts | init.sh + progress.txt + feature_list.json | ✅ | multi-agent-design §启动仪式 (R3) |
| P1 9 | Evaluator | 轨迹 + 端态双评估 | ✅ | eval-driven-design, multi-agent-design |
| P2 10 | MCP | stdio/HTTP/SSE | ✅ | mcp-runtime |
| P2 11 | 权限设置分层 | org → personal | ✅ | policy-limits, remote-managed-settings |
| P2 12 | Plan mode | 独立子模式 | ✅ | plan-mode |
| P2 13 | 观测 | transcript 分析 | ⚠️ 部分 | telemetry-pipeline（收集）、runtime-summaries（展示） |
| Meta 14 | 压测假设 | 定期 prune | ✅ | architecture-invariants §四 ASM |
| Meta 15 | Transcript 脆弱点 | 读中间过程失败 | ⚠️ pending merge | eval-driven-design §Step 9（R5 · [PR #3](https://github.com/Bunnker/cc-harness/pull/3) 未合并）|
| Meta 16 | 失败模式视图 | 按"要防什么"组织 | ✅ | FAILURE-MODES.md |
| Meta 17 | 升级 → 简化 | 不堆砌脚手架 | ✅ | architecture-invariants §四 |

**净状态：15/17 完成 + 1/17 部分 + 1/17 pending merge。** Meta #15 的内容交付已在 R5（[PR #3](https://github.com/Bunnker/cc-harness/pull/3)）完成但未合并到 main，因此本 PR（r6）里 `FAILURE-MODES.md` 对 Step 9 的引用会在 PR #3 合并后才解析。P2 #13（观测 · transcript 分析）的仓内部分已交付（采集 via `telemetry-pipeline`、展示 via `runtime-summaries`、shape 分析方法 via Step 9），仓外的 online eval 聚合管线属于下游消费层，本 skill pack 不承担。

## 三、剩余工作清单（按价值降序）

### T1 · 闭合 Meta #15 · Transcript 脆弱点分析方法 · ⚠️ 内容交付，pending merge（R5）

**落地**：[eval-driven-design §Step 9](skills/eval-driven-design/SKILL.md)（内容在 [PR #3](https://github.com/Bunnker/cc-harness/pull/3) · commit `5fe055d` · +58 行，未合并 main 前当前分支无此锚点）

**交付内容**：
- Anthropic 原话命名的 4 种 shape 脆弱模式：冗余工具调用 / 工具调用震荡 / 过早自我总结 / 沉默能力下降——每项配计数方法和根因指向
- 与新合入 artifact（`commands.log` / `audit-findings.md` / scorecard `code_quality` 维度）的交叉引用表
- "fragile pass" 概念：端态通过 + 轨迹脆弱 → 计入 `pass@k` 但不计入 `pass^k`——在模型升级时能看到"表面分数没降但脆弱性上升"的先行信号
- Step 6（端态）+ Step 9（shape）组合决策规则

**实际用时**：58 行（原估 80-120 行）。能更紧凑是因为 [PR #2](https://github.com/Bunnker/cc-harness/pull/2) 合入的 audit 升级 + M1 hooks 产生了结构化 artifact，Step 9 不用再白手起家定义数据格式，只需引用现有文件类型。

### T2 · 加固 P1 #8 · harness 里的硬约束
**现状**：R3 的启动仪式引用了 `init.sh` / `claude-progress.txt` / `feature_list.json`，但 `harness/SKILL.md` 的 Phase 1/2 没有"**必须**产出这三个工件"的硬要求。

**建议**：在 `harness/SKILL.md` 的 Phase 1 SCAN 或 Phase 2 PLAN 里加条件："若 `estimated_sprints ≥ 3` 或 `current_stage` 标注为长运行阶段，Coordinator 必须在 PLAN 阶段把三个工件写入 target_paths，否则拒绝进入 EXECUTE"。

**估工**：单轮，30-50 行。**优先级：中**（闭环 R3 的可执行性）。

### T3 · 广度扫描 · 剩余 40+ skill 的 Anthropic 对齐
**现状**：R1 深度审视了 Codex 指定的 6 个 skill。剩余 skill 未经 Anthropic 视角系统性审视。

**做法**：spawn Codex 对每个未触及 skill 做 10-20 分钟核实，输出 gap 矩阵 → 分批修复。

**估工**：3-5 轮（扫描 + 分类 + 修复）。**优先级：中低**（可能发现非显而易见 gap，但开销大）。

### T4 · 实证验证 · 用新增 skill 跑一个真任务
**现状**：R1-R3 全是文档层工作。没有证据证明 P/G/E + Sprint Contract + 启动仪式**真的**让跨 sprint 交接更稳。

**做法**：挑一个跨 2-3 sprint 的真实任务，按 R3 仪式严格跑，记录哪里失效。反馈回写到相应 skill。

**估工**：1-2 轮实验 + 反馈回写。**前置条件**：当前仓内暂无合适的跨 sprint 任务。**优先级：未触发**（等有合适任务时再做）。

### T5 · README 集成 · 消除孤岛
**现状**：`FAILURE-MODES.md` 和 `ANTHROPIC-ALIGNMENT-PLAN.md` 是孤岛，`README.md` 没提。

**做法**：`README.md` 加一节"按失败模式导航 → FAILURE-MODES.md"、"持续对齐路线图 → ANTHROPIC-ALIGNMENT-PLAN.md"。

**估工**：5 分钟。**优先级：低**（清洁度，不是价值）。

## 四、推荐顺序

```
R4 = 本路线图诞生（2026-04-17） ✅
R5 = T1（Step 9 Transcript Shape Analysis） ⚠️ 内容交付 · PR #3 未合并
R6 = FAILURE-MODES 反哺（FM-5 加 Step 9 引用 + 新增 FM-15 结构保真） 本 PR
—— 17 项中 15 完成 / 1 部分 / 1 内容交付未合并 ——
—— 当前分叉决策点 ——
→ T2（harness 加长运行工件硬约束） — 低风险单轮，有空就做
→ T5（README 集成 FAILURE-MODES + PLAN 为导航入口） — 5 分钟清洁
→ T4（实证验证） — 等 Zero Magic 或其他项目跑几个跨 sprint 任务后做
→ T3（Codex 广度扫描剩余 40+ skill） — 3-5 轮开销，仅当怀疑有非显而易见 gap 时启动
→ 无新触发 → 暂停，等 Anthropic 发新文章或 Claude 大版本升级再审视
```

## 五、完成定义

**本对齐计划的出口条件（满足则标记本文件为 `done`）**：
1. 原报告 17 项全部 ✅ 或显式承认 "not applicable"
2. 至少一次 T4 实证反馈 **或** 书面承认"没条件实证，依赖后续使用反馈"
3. `FAILURE-MODES.md` 和本文件保持同步：每轮新增 skill / 新增失败模式时都要登记

## 六、维护规则

- 每次 Anthropic 发布新 harness 相关文章 → 本文件末尾追加 "reviewed on YYYY-MM-DD, triggered ASM-N re-check"（流程见 [architecture-invariants §四](skills/architecture-invariants/SKILL.md)）
- 每次 Claude 大版本升级（X.Y → X+1.0）→ 强制重审全部 ASM，并在本文件对应行更新"上次压测"
- 本计划书自身 → 6 个月无任何更新时标记 "possibly stale"，重新对照当前 Anthropic 官方写作

## 七、变更历史

| 日期 | 事件 | commit |
|------|------|--------|
| 2026-04-17 | R1 内容对齐 · 6 skill 插入 | `e7823ff` |
| 2026-04-17 | R2 失败模式导航层 | `258a512` |
| 2026-04-17 | R3 跨 sprint 启动仪式 | `b0d1790` |
| 2026-04-17 | R4 本路线图诞生 | `60edbc0` |
| 2026-04-17 | 继承另一 session：harness-verify audit 升级 + M1 Python hooks + trace contract | `3ff0781` / `e5d0526` / `59b3122`（[PR #2](https://github.com/Bunnker/cc-harness/pull/2)） |
| 2026-04-20 | R5 Step 9 Transcript Shape Analysis（闭合 Meta #15） | `5fe055d`（[PR #3](https://github.com/Bunnker/cc-harness/pull/3)） |
| 2026-04-20 | R6 FAILURE-MODES 反哺 + FM-15 结构保真 + 本 PLAN 状态矩阵更新 | 本次 commit |
