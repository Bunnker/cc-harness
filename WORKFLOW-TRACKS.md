# Workflow Tracks · harness 与 OpenSpec 的并行与共存

> **基础观察**：本文基于 **1 个项目**（Zero Magic `feature/fengshui-mvp`）的实际使用模式归纳，是**初稿决策框架**（n=1，不作通用规则）。证据见 [`EVOLUTION-FROM-ZEROMAGIC.md`](EVOLUTION-FROM-ZEROMAGIC.md) §9。

> **定位**：此文档是**使用指南**，不是 skill。放在仓根是因为它跨 `harness/`、`harness-verify/`、`harness-lite/` 多个 skill 的边界，且引用外部 spec 系统（OpenSpec），单 skill 范围放不下。

---

## 核心判断

**harness 和 OpenSpec 是两条并行工作流轨道，不是竞争关系，也不是父子关系。**

误解：
- ❌ OpenSpec 是 harness 的"文档驱动模式"
- ❌ harness 是 OpenSpec 的"实现引擎"
- ❌ 两者只能二选一

正确：
- ✅ **OpenSpec 管"要交付什么"**（spec / tasks / design artifact + change 级归档）
- ✅ **harness 管"交付得好不好 + 怎么自我改进"**（代码质量 6 维 + M0-M3 Meta Track）
- ✅ **同一项目可以两条轨道并行**——Zero Magic 就是 fengshui OpenSpec change + stage-7 harness stage 同时在推进

---

## 两者能力对比

| 维度 | OpenSpec | harness |
|------|----------|---------|
| **原子单位** | Change（可归档）| Stage / Sprint |
| **主入口** | `/opsx:apply` / `/opsx:verify` / `/opsx:archive` | `/harness` / `/harness-lite` |
| **核心 skill** | `openspec-apply-change` / `openspec-verify-change` / `openspec-archive-change`（共 11 个）| `harness` / `harness-lite` / `harness-verify`（3 个） |
| **依赖外部 CLI** | `openspec` CLI | 无 |
| **核心产物** | `openspec/changes/*/`（proposal / tasks / design）+ `openspec/specs/*/spec.md` | `harness-lab/traces/*`（scorecard / verification / worker diffs）|
| **verify 语义** | 实现**是否匹配 change artifacts**（spec 覆盖率、tasks 完成率）| **代码质量 6 维** + 独立代码审计（code_quality）|
| **跨会话记忆** | spec 版本化 + git 归档 | `harness-state.json` 的 `learnings` + `harness-lab/trace-index.json` |
| **生命周期终点** | Archive（change 并入 main specs）| Stage 推进（循环无终点）|
| **Meta 自优化** | 无内建 M2/M3 等价物 | M0 observability → M1 command façade → M2 candidate eval → M3 auto-search |
| **适合的任务** | 用户可见的业务功能、有明确交付边界 | 内部重构、基础设施、harness 自身优化 |

---

## 决策框架：何时用哪个

### 场景 A · 只用 OpenSpec（不碰 harness）

**触发条件（任一满足）**：
- 业务功能有明确 spec 可写（用户可见的界面、API、数据结构）
- 需要**正式归档**（将来别人要能追溯"这个功能当初为啥这么做"）
- **团队协作**需求（spec 是合同）
- 任务天然分成**多个 Phase**，Phase 边界清晰（设计 → 实现 → 前端 → 联调）

**你得到什么**：
- `openspec` CLI 提供 change 列表 / 状态 / 校验
- spec delta + tasks.md + design.md 三件套作为文档驱动
- `/opsx:archive` 时强制 verify 覆盖率
- Archive 之后 change 目录进 `archive/`，历史可追溯

**放弃什么**：
- 不会生成 harness-lab trace（你不能用这次 change 的数据做 M2 对比）
- 不会自动跑代码质量 6 维审计（`openspec-verify-change` 只看 spec 覆盖，不看 `code_quality`）
- harness 的 `learnings` 数组不增长（跨会话经验不沉淀到 harness 侧）

**Zero Magic 实例**：`add-fengshui-demo-workbench`（18 commits，Phase 1-5 + Archive，一次跑通）

---

### 场景 B · 只用 harness（不碰 OpenSpec）

**触发条件（任一满足）**：
- **基础设施 / 内部重构**，没有用户可见的 spec（e.g. "把 Runtime 的 X 改成 Y"）
- **harness 自身的演进**（Meta Track M0/M1/M2/M3）
- **需要跨会话多 Worker 并行**，Worker 之间要共享 trace 作为下一轮 scan 输入
- **探索性任务**：需求没定、要试 3 条路、不适合提前写 spec

**你得到什么**：
- 硬边界保护（$ARGUMENTS 参数检查 / PLAN 审批锁 / 禁自执行 / 卫生门 JSON 校验）
- harness-lab trace（scorecard.json / verification.md / worker diffs）
- 6 维 scorecard + 独立代码审计（harness-verify §6）
- 跨会话 learnings 累积
- 候选实验管线（M2）

**放弃什么**：
- 没有 change 级归档概念（不会有"归档后进 main specs"的清晰收束）
- 不天然产生 spec 文档（如果将来要做成面向用户的功能，需要补 spec）

**Zero Magic 实例**：stage-0 到 stage-7（7 个已完成 stage，runtime 底层硬化）

---

### 场景 C · 两者结合（OpenSpec 主导 + harness 支援）

**触发条件（同时满足）**：
- 业务功能走 OpenSpec（场景 A 触发）
- 但在某个 Phase 内，代码质量特别关键（e.g. 跨层契约、安全敏感路径）
- 需要**独立代码审计**而非单纯 spec 覆盖率

**实现方式**：项目级 **Phase Coordinator**——参考 `D:\ai code\Zero_magic\.claude\agents\fengshui-phase-coordinator.md` 模式：
- OpenSpec 管整体 change 流
- Phase Coordinator 管本 Phase 内 Worker 调度（借鉴 harness 协议）
- 特别紧要的 Phase 可调用 `harness-verify` 做代码质量审计（作为**辅助信号**，不替代 `openspec-verify-change`）

**注意**：
- Phase Coordinator 是**项目级** agent，不在 harness-skills-pack 里
- 它借鉴 harness 的 Plan→Execute→Report 骨架，但**不写 harness-lab trace**（change 级 trace 由 OpenSpec artifacts 承担）
- APPROVE 门**由父会话承担**，Phase Coordinator 不自己等用户批准

**Zero Magic 实例**：`fengshui-phase-coordinator.md` 完整跑通 5 个 Phase，Phase 4 的 W1/W2/W5 修复、Phase 5 的 W-VERIFY-NEW-1 收口都是 Phase 内部独立验证

---

## 已识别的边界（**不**应该整合的地方）

基于 §9.2 的方法论教训——**不要硬套框架**。下列边界应保持：

| 不整合的东西 | 原因 |
|------------|------|
| OpenSpec 的 `proposal / tasks / design` **不该**进 harness `trace-index.json` | 两者 schema 语义不同；混合会让跨轮 M2 对比口径错乱 |
| harness 的 `harness-state.json` **不该**用 OpenSpec change 状态替代 | harness-state 是 Stage 节奏，change 是交付节奏，尺度不同 |
| Meta-Optimization M2 candidate 对比池**不该**包含 OpenSpec 跑的 change | Phase 切分让 scorecard 口径不统一，候选对比会误判 |
| `harness-verify` **不该**被当作 `openspec-verify-change` 的替代 | 两者语义不同（代码质量 vs spec 覆盖）；替代会让 spec 漂移没人管 |
| `openspec-verify-change` **不该**被当作 `harness-verify` 的替代 | 反向同理，代码质量没人看 |

---

## 已识别的开放问题

[speculation] 以下推测基于 1 项目观察，**未经多项目验证**：

1. **harness 是否该知道项目有 OpenSpec 在用？** — 当前 `/harness SCAN` 不感知 `openspec/` 目录。如果 scan 时能看到"项目里有 N 个 active change"，可以避免 stage 推进撞上 change 交付
2. **`harness-verify` 是否该有 "invoked by phase coordinator" 模式？** — 当前 harness-verify 预设是被 harness Coordinator 调；被项目级 Phase Coordinator 调时 trace 写到哪、scorecard 如何归档，缺规范
3. **skill-catalog 是否该有 `role: bridge` 或 `role: vertical-workflow` 类别？** — 目前 `fengshui-phase-coordinator.md` 是项目级文件，没在 harness-skills-pack 的 catalog 里。如果未来多项目都用这种桥接模式，该有个正式归类
4. **独立评审人清单**——Archive-Ready 独立审的 agent 是谁？如果每次自由选（general-purpose / harness-verify / Codex），可重复性差

---

## 本指南的限制

- **基于 1 个项目**（Zero Magic）× 1 个 OpenSpec change × 7 个 harness stage × 1 次 Archive-Ready
- **OpenSpec 是一个特定的 spec 系统**，其他 spec 系统（Notion doc / Linear ticket / JIRA epic / 自制 YAML）可能需要重新校准分工规则
- **Phase Coordinator 模式也是 n=1**（`fengshui-phase-coordinator.md` 是项目特定实现，没被抽象成可复用 skill）
- 下一步验证：再观察 1-2 个项目用 harness + spec system 的场景后，决定是否把本文**升级为正式 skill**（如 `skills/workflow-tracks/SKILL.md`）

---

## 相关文档

- [`EVOLUTION-FROM-ZEROMAGIC.md`](EVOLUTION-FROM-ZEROMAGIC.md) §9.2 — 本分工判断的证据来源 + 方法论教训
- [`UNIFIED-ROADMAP.md`](UNIFIED-ROADMAP.md) §M2 实证启发式 — 为什么 M2 pool 不应混合 OpenSpec change
- [`FAILURE-MODES.md`](FAILURE-MODES.md) — 两条 workflow 各自擅长治哪些失败模式
- `OPENSPEC-HARNESS-COEXISTENCE-ANALYSIS.md`（待 Codex 产出）— 更深入的技术整合分析

---

## 变更历史

| 日期 | 事件 | commit |
|------|------|--------|
| 2026-04-21 | 初稿诞生（基于 Zero Magic 实战观察 + 用户反馈 "两个都用，分场景"）| （本次 commit）|
