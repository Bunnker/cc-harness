# Harness 进化计划：从 Design/Audit Harness 到 CC 级架构

> 基于 CC 源码全量验证（10/10 机制确认存在）+ 85,000 行文档交叉审计 + 44 个 skill 内容分析

## 当前状态评估

### 已验证的 CC 设计精髓（源码级确认）

| # | 机制 | 源码入口 | harness 状态 |
|---|------|---------|-------------|
| 1 | Hook 27 事件 × 5 类型 | `src/schemas/hooks.ts` + `src/utils/hooks/hookEvents.ts` | skill 覆盖，编排层未利用 |
| 2 | 权限 deny 优先不可覆盖 | `src/utils/permissions/permissions.ts:1078-1150` | 完全缺失 |
| 3 | CacheSafeParams 缓存共享 | `src/utils/forkedAgent.ts:57-141` | 完全缺失 |
| 4 | 并发分区（只读并行/写入串行） | `src/services/tools/toolOrchestration.ts:91-177` | skill 覆盖，编排层未利用 |
| 5 | 拒绝追踪 3 次降级 | `src/utils/permissions/denialTracking.ts:12-44` | 完全缺失 |
| 6 | 投机执行 CoW 隔离 | `src/services/PromptSuggestion/speculation.ts:72+` | skill 覆盖，编排层未利用 |
| 7 | 工具排序确定性 | `src/tools.ts:354-366` | 完全缺失 |
| 8 | fork 递归防护 | `src/constants/tools.ts:36-46` | 完全缺失 |
| 9 | Bash 错误级联取消 | `src/services/tools/toolOrchestration.ts:118-150` | 完全缺失 |
| 10 | 消息规范化多步 | `src/utils/messages.ts:731+` + `normalizeMessagesForAPI:1989+` | 不适用 |

### 评分：37/100 → P0 后 55 → P1 后 ~70 → P2 后 ~85 → 结构保真补强后 ~90/100

| 维度 | 满分 | 初始 | P0 | P1 | P2 | 当前 | 缺什么 |
|------|------|------|-----|-----|-----|------|--------|
| 架构哲学 | 5 | 1.5 | 3 | 3.5 | 5 | 5 | — |
| 运行时机制（skill 覆盖） | 8 | 8 | 8 | 8 | 8 | 8 | 全覆盖 |
| 运行时机制（编排利用） | 8 | 1.5 | 4 | 6.5 | 7 | 7.5 | 并发自动分区（需代码）、投机执行（需运行时） |
| 工程纪律 | 6 | 1 | 3.5 | 5 | 5.5 | 6 | — |
| 进化能力 | 4 | 0.5 | 1.5 | 3 | 3.5 | 3.5 | 后台自治（需常驻进程） |
| **结构保真**（新增维度） | **5** | **0** | **0** | **0** | **0** | **4** | smoke test 需要项目配合写测试用例 |
| **合计** | **36** | **12.5** | **20** | **26** | **29** | **34** | |

> **为什么新增"结构保真"维度**：P0-P2 的 5 个维度覆盖了"harness 怎么调度 Worker"，但没覆盖"Worker 产出怎么不破坏现有代码"。Zero Magic 实战暴露了这个盲区——Worker 语法对、类型对，但破坏了模块边界和框架不变式。结构保真是独立于调度能力的质量维度。

### 结构保真维度明细（4/5）

| 子项 | 得分 | 落地位置 |
|------|------|---------|
| Worker 结构保真约束（5 条） | 1/1 | SKILL.md Worker prompt |
| Coordinator 结构保真决策规则 + ESCALATE | 1/1 | execution-policy.md 三++ |
| 变更漂移检查（git baseline + 工作区 diff） | 1/1 | SKILL.md Phase 3 3a+ |
| 运行时不变式验证（静态 + smoke test） | 0.5/1 | verification-protocol.md（smoke test 依赖项目配合） |
| 项目约束注入到 Worker prompt | 0.5/1 | harness-state.json constraints + smoke_tests（Zero Magic 已配，通用机制已就绪） |

### 剩余 6 分差距（当前 34/36 ≈ 94%，但部分维度满分上限被 P3 锁住）

| 缺口 | 性质 | 分值 |
|------|------|------|
| 并发 Worker 自动分区 | 需要代码（解析 dependency-graph → 自动分组） | 0.5 |
| 投机执行 | 需要 Agent 运行时 + CoW 隔离 | 不计入（超出 harness 编排层范围） |
| 后台自治 | 需要常驻进程/cron | 0.5 |
| smoke test 项目覆盖率 | 需要每个目标项目写测试用例 | 0.5 |
| 约束注入的自动发现 | 当前靠人工加 constraints，理想是自动从框架文档提取 | 0.5 |

---

## CC 架构的 4 层精髓与 Harness 对齐方案

### Layer 0: 架构哲学 — 5 条必须遵守的原则

#### 原则 1：中间输出价值决定架构

**CC 源码事实**：`src/tools/AgentTool/runAgent.ts` 的 fork 决策不是看"任务大不大"，是看"中间搜索结果值得保留在主对话吗"。

**harness 缺失**：stage-roadmap 是线性推进（0→1→2→...→8），没有"这个阶段的产出值得保留吗"的决策。

**对齐方案**：
```
在 stage-roadmap.md 每个阶段加 value_assessment：

### 阶段 N：{名称}
**产出价值评估**：
- 设计方案 → 值得保留（作为后续编码的输入）
- 探索性分析 → 不值得保留（结论写入 state，过程丢弃）
- 审计报告 → 看情况（严重问题保留，通过则丢弃）

**架构决策**：
- 值得保留 → Worker 结果写入项目文件
- 不值得保留 → Worker 在 isolation: worktree 中执行，只提取结论
```

#### 原则 2：永不委托理解

**CC 源码事实**：Bible CH5 + Philosophy 明确禁止"基于你的发现去修复"。Coordinator 必须自己读 Worker 结果，给出具体指令。

**harness 缺失**：SKILL.md Phase 4 REPORT 模板没有强制 Coordinator 综合 Worker 结果的检查。

**对齐方案**：
```
在 SKILL.md Phase 4 REPORT 加强制检查：

### 综合理解检查（REPORT 前必须完成）
Coordinator 必须：
1. 逐个阅读 Worker 返回结果
2. 用自己的话总结每个 Worker 做了什么（不引用 Worker 原文）
3. 检查 Worker 间的接口是否对齐
4. 如果发现矛盾，在 Report 中标注并建议修正方案

禁止：
- "Worker-1 的结果请参考其输出" ← 这是委托理解
- "基于 Worker 的发现继续推进" ← 这是委托理解
```

#### 原则 3：隔离是运行时的，缓存是请求时的

**CC 源码事实**：`src/utils/forkedAgent.ts:46-56` 注释明确说明——fork Agent 的 API 请求必须与父 Agent 的 system prompt + tools + model 完全一致（byte-identical），才能复用 prompt cache。但 fork Agent 的消息历史、文件缓存、取消信号完全隔离。

**harness 缺失**：Worker 是独立的 Agent 调用，没有 cache 共享意识。每个 Worker 的 system prompt 不同（因为传了不同的项目上下文和 skill 指令），导致每个 Worker 都是独立的 cache miss。

**对齐方案**：
```
短期（design harness 够用）：
  在 Worker prompt 模板中统一前缀——项目上下文 + 约束放在相同位置、相同格式
  skill 指令放在 prompt 末尾（动态部分不影响前缀 cache）

长期（implementation harness 需要）：
  实现 CacheSafeParams 概念——
  1. 主循环调用后保存 lastCacheSafeParams
  2. Worker fork 时传入相同参数
  3. Worker 的 system prompt = 父 system prompt + skill 指令（追加不替换）
```

#### 原则 4：保守默认值

**CC 源码事实**：`src/tools.ts` 的 `buildTool()` 把所有不确定的属性默认为 false（isConcurrencySafe=false, isReadOnly=false, isDestructive=false）。忘了声明安全性的工具会被保守地串行执行。

**harness 缺失**：skill-catalog 的 `parallel_safe_with` 列出了可以并行的组合，但没有"未声明 = 默认不可并行"的强制规则。

**对齐方案**：
```
在 dependency-graph.md 的决策速查末尾加：

6. 如果 skill A 和 B 都没有出现在任何并行安全组中
   → **默认串行**（保守默认值原则）
   → 不要因为"看起来没依赖"就并行
```

#### 原则 5：deny 优先不可覆盖

**CC 源码事实**：`src/utils/permissions/permissions.ts:1145` 注释 "Safety checks are bypass-immune"。deny 一旦触发，后续任何 allow 都无法覆盖。

**harness 缺失**：没有权限模型。Worker 能做什么取决于 prompt 指令，没有系统级约束。

**对齐方案**：
```
在 execution-policy.md 加 Worker 约束规则：

## Worker 安全约束

### 路径约束（deny 优先）
每个 Worker 的 prompt 必须包含：
  ## 输出约束
  - 只允许创建/修改以下路径：{paths}
  - 禁止修改：.claude/、.git/、node_modules/、*.lock
  - 禁止执行：rm -rf、git push、npm publish

### 工具约束
Worker 禁止使用：
  - AgentTool（防递归）
  - AskUserQuestion（只有 Coordinator 与用户交互）

### 约束不可覆盖
Worker 的 prompt 中不能包含"忽略上述约束"类指令。
Coordinator 不能在 Worker prompt 中授权被禁止的操作。
```

---

### Layer 1: 运行时机制 — 编排层需要利用的 8 个机制

#### 机制 1：Hook 事件点

**CC 怎么做**：27 种事件在关键时刻触发，外部可以拦截和修改行为。

**harness 怎么加**：
```
在 SKILL.md 的 4 个 Phase 中加 Hook 点：

Phase 1 SCAN：
  hook: PreScan — 允许自定义探测规则
  hook: PostScan — 允许修正探测结果

Phase 2 PLAN：
  hook: PrePlan — 允许注入额外约束
  hook: PostPlan — 允许审查/修改计划（用户确认前）

Phase 3 EXECUTE：
  hook: PreWorkerDispatch — 允许修改 Worker prompt
  hook: PostWorkerComplete — 允许审查 Worker 结果
  hook: WorkerFailed — 允许自定义失败处理

Phase 4 REPORT：
  hook: PreReport — 允许补充检查
  hook: PostReport — 允许触发后续动作（如自动提交 git）

实现方式：
  不需要真正的 Hook 基础设施。
  在 SKILL.md 的每个 Phase 加一步"检查 harness-hooks.json 配置"。
  如果配置了对应 Hook，执行它。
```

#### 机制 2：并发分区

**CC 怎么做**：`partitionToolCalls()` 按 `isConcurrencySafe()` 自动分区。

**harness 怎么加**：
```
已经有 dependency-graph 的三类并行组。
缺的是 Coordinator 在 EXECUTE 阶段的自动分区逻辑。

当前：Coordinator 手工决定并行组
应该：Coordinator 查 dependency-graph 自动分区

在 SKILL.md Phase 3 加：
  调度前自动检查：
  1. 读 dependency-graph.md 的并行安全矩阵
  2. 对计划中的每对 Worker，查它们的 skill 组合是否在安全组中
  3. 不在安全组中 → 自动拆到不同批次
  4. 条件并行组 → 检查任务类型（设计可并行 / 编码串行）
```

#### 机制 3：拒绝追踪 + 自动降级

**CC 怎么做**：`denialTracking.ts` 记录连续拒绝次数，3 次后 `shouldFallbackToPrompting()` 返回 true。

**harness 怎么加**：
```
在 harness-state.json 加 denial_tracking：

{
  "denial_tracking": {
    "consecutive_failures": 0,
    "total_failures": 0,
    "last_failure_reason": null
  }
}

逻辑：
- Worker 失败 → consecutive_failures++
- Worker 成功 → consecutive_failures = 0
- consecutive_failures >= 3 → 自动降级：
    - 设计任务降级为"仅生成架构骨架，不做详细方案"
    - 编码任务降级为"仅生成接口定义，不做完整实现"
    - 审计任务降级为"仅检查最关键的 3 项，不做全量审计"
```

#### 机制 4：缓存经济学

**CC 怎么做**：工具按名称排序、Beta Header 会话锁定、fork 用统一占位符。

**harness 怎么加**：
```
短期不需要实现完整缓存系统。
但 Worker prompt 模板应该有确定性：

1. Worker prompt 的项目上下文段落用固定格式（不随 Coordinator 的表述风格变化）
2. Worker 列表中的 skill 名称按字母序排列
3. 同一轮的 Worker 共享相同的项目上下文前缀

这不需要代码实现，只需要 SKILL.md 的 prompt 模板保持确定性。
```

#### 机制 5：fork 递归防护

**CC 怎么做**：`src/constants/tools.ts:36-46` 禁止 Worker 使用 AgentTool。

**harness 怎么加**：
```
在 Worker prompt 模板加：

## 禁止操作
- 不要使用 Agent 工具派生子 Agent
- 不要使用 AskUserQuestion 工具（只有 Coordinator 与用户交互）
- 如果你需要更多信息，在输出中说明需要什么，由 Coordinator 在下一轮补充
```

#### 机制 6：Bash 错误级联取消

**CC 怎么做**：Bash 失败中止同批次其他工具。

**harness 怎么加**：
```
在 execution-policy.md 的失败处理加：

### 级联失败规则
如果同一并行组中有 Worker 失败：
- 检查失败原因是否影响同组其他 Worker
- 如果失败 Worker 的输出是其他 Worker 的输入 → 取消未完成的 Worker
- 如果失败 Worker 独立 → 其他 Worker 继续

类比 CC 的设计：
- Bash（改系统状态）失败 → 级联取消（状态可能不一致）
- Read（只读）失败 → 不级联（不影响其他）
- Worker 的设计任务失败 → 不影响同组其他设计任务
- Worker 的编码任务失败 → 检查是否有依赖的编码任务需要取消
```

#### 机制 7：阶段跳过（门控）

**CC 怎么做**：`isGateOpen()` 返回 false 时整个 auto dream 不触发。

**harness 怎么加**：
```
在 stage-roadmap.md 每个阶段加 skip_if：

### 阶段 4：跨会话与记忆
**skip_if**：
  - 目标项目是一次性脚本（无需跨会话记忆）
  - 目标项目已有成熟的记忆系统
  - 用户明确说"不需要记忆"

### 阶段 8：企业治理
**skip_if**：
  - 目标项目是个人项目
  - 目标项目不需要远程配置管理
  - 用户明确说"不需要企业功能"

Coordinator 在 SCAN 阶段检查 skip_if 条件，
跳过的阶段在计划中标注"已跳过（原因：{skip_if 命中的条件}）"
```

#### 机制 8：Worker 工具约束（最小权限）

**CC 怎么做**：每个 fork Agent 的 `canUseTool` 回调严格限制可用工具和可修改路径。

**harness 怎么加**：
```
在 Worker prompt 模板加：

## 输出约束
- 只允许创建/修改以下路径：{target_paths}
- 只允许使用以下工具：Read, Glob, Grep, Edit, Write, Bash（只读命令）
- 禁止使用 Agent 工具
- 禁止修改 .claude/ 目录、.git/ 目录
```

---

### Layer 2: 工程纪律 — 6 条必须遵守的规则

| 纪律 | 来源 | harness 实现方式 |
|------|------|----------------|
| 工具排序确定性 | `tools.ts:362` | Worker prompt 中的 skill 列表按字母序 |
| fork 递归防护 | `constants/tools.ts:36` | Worker prompt 禁止 AgentTool |
| Bash 错误级联 | `toolOrchestration.ts:118` | 同组 Worker 失败检查依赖关系 |
| 消息规范化 | `messages.ts:731` | 不适用（harness 不直接处理消息） |
| writeSync 终端恢复 | `gracefulShutdown.ts` | 不适用 |
| 状态文件损坏恢复 | CC 的 lock rollback | SCAN 阶段加健康检查 |

**状态文件健康检查（在 SKILL.md Phase 1 SCAN 加）**：
```
### 1d. 状态文件健康检查

如果 harness-state.json 存在，验证以下一致性：
1. 每个 status=designed 的模块 → 检查设计文件是否存在
2. 每个 status=implemented 的模块 → 检查代码文件是否存在
3. current_stage 是否与 modules 状态一致
4. completed_stages 中的阶段是否真的所有模块都完成了

不一致时：
- 文件缺失 → 降级 status 为 not_started，在 Report 中标注
- stage 不一致 → 重新计算 current_stage
- 不删除 state 文件（用户可能手动编辑过，保留意图）
```

---

### Layer 3: 进化能力 — 4 个反馈闭环

#### 闭环 1：执行后学习

```
当前：Worker 完成 → Report → 结束
缺失：没有把成功/失败经验写入持久化状态

对齐方案：
REPORT 阶段结束后，自动提取本轮经验：

harness-state.json 新增：
{
  "learnings": [
    {
      "date": "2026-04-03",
      "stage": "stage-2-security",
      "type": "success",
      "insight": "该项目的 Flask 框架有内置权限中间件，不需要从零设计"
    },
    {
      "date": "2026-04-03",
      "stage": "stage-1-minimal-loop",
      "type": "failure",
      "insight": "Worker 生成的循环设计依赖了 CC 特有的 stopHooks，需要改用项目自己的事件机制"
    }
  ]
}

下次 SCAN 时读取 learnings，避免重复犯错。
```

#### 闭环 2：跨会话状态积累

```
当前：每次 /harness 是独立调度
已有：harness-state.json 持久化

缺失：没有"上次做到哪了，这次从哪继续"的自动衔接

对齐方案：
SCAN 阶段读取 state 后，自动生成"上次进展摘要"：

"上次执行摘要（来自 harness-state.json）：
- 上次日期：{last_execution.date}
- 上次目标：{last_execution.plan_summary}
- 上次结果：{results 的一句话总结}
- 当前阶段：{current_stage}
- 本次应该从哪继续：{下一个 not_started 模块}"
```

#### 闭环 3：cc-bound skill 使用后的迁移反馈

```
当前：cc-bound skill 使用时标注"需人工判断 CC 特有实现"
缺失：没有记录"哪些 CC 实现在目标项目中被替换了"

对齐方案：
当 Worker 使用 cc-bound skill 时，Report 阶段记录：

harness-state.json 新增：
{
  "cc_adaptations": [
    {
      "skill": "auth-identity",
      "cc_pattern": "macOS Keychain 集成",
      "adapted_to": "环境变量 + .env 文件",
      "reason": "目标项目是 Linux 服务器，无 Keychain"
    }
  ]
}

这些记录会在下次使用同一 skill 时作为上下文注入 Worker prompt，
避免重复做相同的迁移决策。
```

#### 闭环 4：阶段完成度自动检测

```
当前：Coordinator 手动判断"这个阶段是否完成"
缺失：没有自动检测条件

对齐方案：
stage-roadmap.md 的每个阶段已有"检测条件"，但 harness 没有用它。

在 SKILL.md Phase 1 SCAN 加：
  如果 state 显示 current_stage = stage-N：
  1. 读 stage-roadmap.md 中 stage-N 的"检测条件"
  2. 用 Bash 工具在目标项目中检查这些条件
  3. 如果全部满足 → 建议进入 stage-N+1
  4. 如果部分满足 → 列出未满足的条件，建议补齐
```

---

## 实施优先级

### P0（做了就能从 37 分到 55 分）— ✅ 已完成

| 改进 | 修改文件 | 状态 |
|------|---------|------|
| Worker 路径约束 + 工具约束 | SKILL.md Phase 3 prompt 模板 | ✅ |
| 阶段跳过逻辑 skip_if | stage-roadmap.md 每个阶段 | ✅ |
| 状态文件健康检查 | SKILL.md Phase 1 加 1d 步骤 | ✅ |
| fork 递归防护 | SKILL.md Worker prompt 模板 | ✅ |
| 永不委托理解检查 | SKILL.md Phase 4 加强制步骤 | ✅ |

### P1（做了能从 55 分到 70 分）— ✅ 已完成（2026-04-03）

| 改进 | 修改文件 | 状态 |
|------|---------|------|
| Hook 事件点（9 个） | SKILL.md 4 个 Phase + 新建 harness-hooks-schema.md | ✅ |
| 拒绝追踪 + 自动降级 | state-schema.md + execution-policy.md 第七节 + SKILL.md Phase 3 3a 降级检查 + Phase 4 denial_tracking 更新 | ✅ |
| 执行后学习（learnings） | state-schema.md + execution-policy.md 第十节 + SKILL.md Phase 4 执行后学习提取 | ✅ |
| cc-bound 迁移记录 | state-schema.md + execution-policy.md 第十节 + SKILL.md Phase 1 1a+ 注入 + Phase 4 提取 | ✅ |
| 级联失败规则 | execution-policy.md 第八节 + SKILL.md Phase 3 3e 级联失败处理 | ✅ |

### P2（做了能从 70 分到 85 分）— ✅ 已完成（2026-04-04）

| 改进 | 修改文件 | 状态 |
|------|---------|------|
| CacheSafeParams 概念 | SKILL.md Phase 3 Worker prompt 模板改为两段式（固定前缀+动态后缀）+ 字母序排列 + 前缀生成规则 | ✅ |
| 阶段完成度自动检测 | SKILL.md Phase 1 加 1e 步骤（读 stage-roadmap.md 检测条件 → Bash 验证 → 建议推进/补齐） | ✅ |
| 中间输出价值评估 | stage-roadmap.md 全部 9 个阶段加 value_assessment + execution-policy.md 加三+节（保留/不保留/看情况 → isolation 决策） | ✅ |
| 跨会话自动衔接 | SKILL.md Phase 1 1a 后加上次进展摘要模板（自动输出给用户） | ✅ |

### P3（85 分以上需要代码实现，不只是文档）

| 改进 | 性质 | 说明 |
|------|------|------|
| 后台自治 | 需要 Agent 运行时 | harness 需要常驻进程或 cron 触发 |
| 投机执行 | 需要 Agent 运行时 | 需要 CoW 文件系统隔离 |
| 真正的 CacheSafeParams | 需要 API 层 | 需要控制 system prompt 的 byte-level 一致性 |
| 并发 Worker 自动分区 | 需要代码 | 需要自动解析 dependency-graph 并分区 |

---

## Meta-Optimization Track（外循环优化层）

> **定位**：Meta-Optimization Track 是独立于 P0-P3 的外循环优化轨道。
> P0-P3 解决的是"harness 怎么正确调度 Worker"；Meta Track 解决的是"harness 自身怎么持续变好"。
> 它不替代现有 harness 主流程，不替代 `harness-state.json` 的 `state/learnings/denial_tracking` 控制面。
> 它在现有控制面之上新增**数据面**（traces/evals/candidates），让 harness 的改进可观测、可评估、可搜索。

### 核心原则

1. **控制面不动，数据面新增**：`harness-state.json` 继续做调度决策的单一来源；新增的 traces/artifacts/scorecard 是证据层，不参与调度决策
2. **先可观测，再可评估，再多候选，再自动优化**：M0→M1→M2→M3 严格顺序，前一阶段稳定后才启动下一阶段
3. **不过拟合单一项目**：必须区分 search repos 和 held-out repos，只有两侧都通过才允许晋升
4. **搜索空间收窄**：第一批只优化编排模板和策略文件，不自动修改 skill 主体和安全边界

---

### 候选版本库结构

```
.claude/harness-lab/
├── traces/                    # M0: 执行原始证据
│   └── {date}-{stage}/       # 每轮一个目录
│       ├── worker-{n}-prompt.md       # Worker prompt 快照
│       ├── worker-{n}-commands.log    # 关键命令输出
│       ├── worker-{n}-result.md       # Worker 最终回复
│       ├── worker-{n}-diff.patch      # git diff
│       ├── verification.md            # verification artifact
│       └── failure-reason.md          # 失败原因（仅失败时）
├── evals/                     # M1: 评估结果
│   └── {date}-{stage}/
│       ├── scorecard.json             # 多维评分
│       └── smoke-results.log          # smoke test 原始输出
├── candidates/                # M2: 候选变体
│   └── {candidate-id}/
│       ├── manifest.json              # 变体描述：改了什么、为什么
│       ├── patches/                   # 相对于 baseline 的 diff
│       └── eval-results/              # 该候选在各项目上的评估
└── leaderboard.json           # M2: 候选排行榜
```

**与现有结构的关系**：
- `harness-state.json` → 控制面，调度用，不变
- `harness-lab/traces/` → 数据面，`learnings` 的证据来源（`learnings` 是从 traces 提取的摘要）
- `harness-lab/evals/` → `smoke_tests` 的扩展（smoke_tests 是 scorecard 的一个子维度）

---

### M0：Observability（可观测）

**目标**：每轮 harness 执行后留下完整的可回溯证据链，而不只是 `learnings` 里的一句话摘要。

**前置依赖**：P1 已完成（learnings 机制已就绪）

#### M0.1 Execution Traces

**做什么**：每个 Worker 执行时，自动保存 5 类原始证据到 `harness-lab/traces/{date}-{stage}/`。

| 证据类型 | 来源 | 文件名 |
|---------|------|--------|
| Worker prompt 快照 | Phase 3 dispatching 时的完整 prompt | `worker-{n}-prompt.md` |
| 关键命令输出 | Worker 执行的 Bash 命令及其 stdout/stderr | `worker-{n}-commands.log` |
| Worker 最终回复 | Worker 返回给 Coordinator 的完整文本 | `worker-{n}-result.md` |
| git diff | Worker 完成后的 `git diff --stat` + `git diff` | `worker-{n}-diff.patch` |
| 失败原因与状态变更 | 仅失败时记录：错误信息 + state 字段变更 | `failure-reason.md` |

**实现方式**：在 SKILL.md Phase 3 的 Worker dispatch 模板中加：
```
每个 Worker 完成后，Coordinator 将以下内容写入
harness-lab/traces/{date}-{stage}/：
1. 本次发送给 Worker 的完整 prompt → worker-{n}-prompt.md
2. Worker 回复中涉及的命令输出 → worker-{n}-commands.log
3. Worker 的完整回复 → worker-{n}-result.md
4. 在目标项目中执行 git diff --stat 和 git diff → worker-{n}-diff.patch
5. 如果 Worker 失败：失败原因 + harness-state.json 的变更 → failure-reason.md
```

**与 `learnings` 的关系**：`learnings` 继续存在于 `harness-state.json`，是 trace 的**摘要**。Phase 4 REPORT 提取 learnings 时，必须引用对应的 trace 文件路径作为证据来源。

#### M0.2 Verification Artifacts

**做什么**：将 verification-protocol.md 的每次执行结果持久化，而不只是 pass/fail 状态。

**保存内容**：
- build/lint/typecheck 的完整输出（不只是 exit code）
- smoke test 的逐条结果
- 结构保真检查的 diff（baseline vs 当前）
- 运行时不变式验证的输出

**文件位置**：`harness-lab/traces/{date}-{stage}/verification.md`

#### M0.3 Scorecard

**做什么**：替代单一 `pass_rate`，引入多维评分卡。

**scorecard 结构**：
```json
{
  "date": "2026-04-05",
  "stage": "stage-1-minimal-loop",
  "project": "Zero_magic",
  "dimensions": {
    "build_lint_typecheck": {
      "score": 1.0,
      "detail": "tsc 0 errors, eslint 0 warnings"
    },
    "smoke_tests": {
      "score": 0.8,
      "detail": "4/5 passed, failed: auth_flow_test"
    },
    "runtime_invariants": {
      "score": 1.0,
      "detail": "all framework constraints preserved"
    },
    "structural_fidelity": {
      "score": 0.9,
      "detail": "1 module boundary drift detected (minor)"
    },
    "verification_coverage": {
      "score": 0.75,
      "detail": "3/4 modules have verification artifacts"
    }
  },
  "composite_score": 0.89,
  "trace_path": "harness-lab/traces/2026-04-05-stage-1/"
}
```

**与现有 `smoke_tests` 的关系**：`harness-state.json` 中的 `smoke_tests` 配置不变（它定义**要测什么**）。Scorecard 记录的是**测出了什么**，是 `smoke_tests` 执行后的结果归档。

**成功标准**：
- [ ] 每轮执行后 `harness-lab/traces/` 下有完整的 5 类证据文件
- [ ] scorecard 的所有**适用维度**都有非空值（设计任务只要求 verification_coverage 非空，编码任务要求 5 维全非空）
- [ ] `learnings` 中的每条 insight 都引用了 trace 路径
- [ ] 连续 3 轮实战执行后，traces 可回溯且与 learnings 一致

---

### M1：Executable Shell（可执行）

**目标**：将 harness 文档中的检查步骤变成可直接运行的命令和脚本，减少 Coordinator 的解释偏差。

**前置依赖**：M0 稳定（有 traces 可对比执行结果）

#### M1.1 Command Façade

**做什么**：为 verification-protocol.md 中的每类检查，提供标准化的命令模板。

```
# 每个目标项目的 harness-state.json 中新增：
{
  "commands": {
    "build": "cd {project_path} && npm run build 2>&1",
    "lint": "cd {project_path} && npm run lint 2>&1",
    "typecheck": "cd {project_path} && npx tsc --noEmit 2>&1",
    "smoke": "cd {project_path} && npm test -- --grep smoke 2>&1",
    "structural_diff": "cd {project_path} && git diff --stat {baseline_commit} HEAD"
  }
}
```

**Coordinator 在 Phase 3 verification 时**：不再靠 prompt 指令让 Worker "运行构建检查"，而是直接执行 `commands.build`、`commands.lint` 等，将输出写入 trace。

#### M1.2 Real Hook Scripts

**做什么**：将 harness-hooks-schema.md 中的声明式 Hook 配置，落地为可执行的 shell 脚本。

**目录结构**：
```
.claude/harness-lab/hooks/
├── pre-worker-dispatch.sh     # 注入额外约束、修改 prompt
├── post-worker-complete.sh    # 自动 diff check、artifact 归档
├── worker-failed.sh           # 失败分类、降级触发
└── post-report.sh             # scorecard 生成、trace 归档
```

**与现有 Hook 机制的关系**：harness-hooks-schema.md 定义**语义**（什么事件、什么条件、什么动作）；这里的脚本是**实例**（具体怎么执行）。Coordinator 在对应 Phase 检查到 Hook 配置后，调用对应脚本。

#### M1.3 Regression Tests

**做什么**：为 harness 编排逻辑本身写测试，验证改进不引入回退。

**测试类别**：

| 测试 | 验证什么 | 怎么跑 |
|------|---------|--------|
| state-schema 一致性 | `harness-state.json` 符合 `state-schema.md` 定义 | JSON Schema 校验 |
| trace 完整性 | 每轮执行后 5 类证据文件都存在 | 检查 traces/ 目录 |
| scorecard 覆盖 | 适用维度都有值（设计任务仅 verification_coverage，编码任务 5 维） | 解析 scorecard.json |
| learnings 可溯源 | 每条 learning 引用了 trace 路径 | 正则匹配 |
| 候选不侵入主流程 | `harness-lab/candidates/` 的 patch 不包含 `harness-state.json` 的 schema 主结构变更 | diff 检查 |

**成功标准**：
- [ ] `commands` 配置覆盖 build/lint/typecheck/smoke/structural_diff
- [ ] 至少 2 个 Hook 有可执行脚本
- [ ] 回归测试全部通过
- [ ] 在已有项目（Zero Magic）上运行 M1 全流程无报错

---

### M2：Candidate Evaluation（候选评估）

**目标**：对 harness 编排策略的变体进行受控 A/B 评估，用数据而非直觉决定是否采纳。

**前置依赖**：M1 稳定（有可执行的 commands 和 tests 做自动评估）

#### M2.1 A/B Candidates

**做什么**：当需要优化某个编排策略时，生成候选变体，在隔离环境中对比评估。

**候选 manifest 结构**：
```json
{
  "candidate_id": "prompt-v2-concise-worker",
  "created": "2026-04-10",
  "baseline": "current harness main",
  "hypothesis": "精简 Worker prompt 模板（去掉冗余上下文）可以减少 token 用量 20% 而不降低 scorecard",
  "modified_files": [
    "harness/SKILL.md"
  ],
  "search_space": "worker-prompt-template",
  "status": "evaluating"
}
```

**第一阶段只在以下任务类型启用 A/B**：
- prompt / template 变体（Worker prompt 模板措辞）
- 设计方案变体（不同的模块拆分策略）
- 小范围局部 patch（verification checklist 调整）
- 高不确定性但可快速验证的模块

**不在以下场景启用**（避免合并漂移和验证成本爆炸）：
- 大规模编码任务
- 跨多文件的架构重构
- 安全边界相关的变更

#### M2.2 Worktree Isolation

**做什么**：每个候选变体在独立 git worktree 中评估，不污染主分支。

**执行流程**：
```
1. 从 main 创建 worktree: git worktree add harness-lab/eval-{candidate-id} -b eval/{candidate-id}
2. 在 worktree 中应用候选的 patches/
3. 在 worktree 中对 search repo 执行一轮完整 harness 调度
4. 收集 scorecard → 写入 candidates/{candidate-id}/eval-results/
5. 清理 worktree: git worktree remove harness-lab/eval-{candidate-id}
```

**与现有 `isolation: worktree` 的关系**：现有的 worktree 用于 Worker 的"不值得保留的中间输出"隔离（P2 中间输出价值评估）。这里的 worktree 用于候选变体的**整轮评估隔离**，范围更大。

#### M2.3 Leaderboard

**做什么**：维护候选变体的排行榜，记录各候选在不同项目上的 scorecard。

**leaderboard.json 结构**：
```json
{
  "last_updated": "2026-04-12",
  "baseline": {
    "composite_score": { "Zero_magic": 0.89 },
    "cost_tokens": { "Zero_magic": 45000 }
  },
  "candidates": [
    {
      "candidate_id": "prompt-v2-concise-worker",
      "scores": {
        "Zero_magic": {
          "composite_score": 0.91,
          "cost_tokens": 36000,
          "dimensions": { "build_lint_typecheck": 1.0, "smoke_tests": 0.8, "runtime_invariants": 1.0, "structural_fidelity": 0.95, "verification_coverage": 0.8 }
        }
      },
      "delta_vs_baseline": { "Zero_magic": { "composite": "+0.02", "cost": "-20%" } },
      "status": "pending_held_out"
    }
  ]
}
```

**成功标准**：
- [ ] 至少 1 个候选变体完成 A/B 评估
- [ ] leaderboard 有 baseline 和至少 1 个候选的对比数据
- [ ] worktree 评估后自动清理，不留残余分支
- [ ] 候选的 eval-results 包含完整 scorecard

---

### M3：Harness Search（自动搜索优化）

**目标**：用受控的 proposer 自动生成候选变体，在 search/held-out 双集上评估，稳定提升后自动晋升。

**前置依赖**：M2 稳定（有候选评估管线和 leaderboard）

#### M3.1 Proposer

**做什么**：基于 traces 和 scorecard 中的低分维度，自动提出改进候选。

**Proposer 的输入**：
- 最近 N 轮的 traces（失败原因、Worker prompt、verification 结果）
- 当前 scorecard 的低分维度
- leaderboard 中已尝试过的候选（避免重复）
- 版本化搜索空间的边界（只能改什么、不能改什么）

**Proposer 的输出**：
- 一个 `candidates/{candidate-id}/manifest.json`
- 对应的 `patches/` 目录

**Proposer 的约束**：
- 每次只改一个文件或一个策略点（单变量实验）
- 必须写出 hypothesis（改什么、预期什么效果）
- 不能修改搜索空间边界之外的文件

#### M3.2 Search Set / Held-out Set

**做什么**：防止 harness 优化过拟合到单一项目。

**切分规则**：
```
search_repos:
  - 用于训练/优化的项目（proposer 可以看这些项目的 traces 和 scorecard）
  - 例如：Zero_magic（已有深度使用历史）

held_out_repos:
  - 用于验证泛化性的项目（proposer 不看这些项目的数据）
  - 候选晋升前必须在 held-out 上也不回退
  - 例如：至少 1 个不同技术栈的项目

配置位置（harness-lab/eval-config.json）：
{
  "search_repos": [
    { "name": "Zero_magic", "path": "D:/ai code/Zero_magic" }
  ],
  "held_out_repos": [
    { "name": "TBD", "path": "TBD", "note": "需至少 1 个不同技术栈的项目" }
  ]
}
```

**held-out 最少要求**：至少 1 个与 search repo 不同技术栈/框架的项目。如果没有 held-out 项目，M3 不启动。

#### M3.3 Promote / Reject Policy

**做什么**：定义候选变体从实验到正式的晋升规则。

**晋升的 4 个必要条件（全部满足才 promote）**：

| # | 条件 | 具体指标 | 验证方式 |
|---|------|---------|---------|
| 1 | search set 提升 | composite_score 在所有 search repos 上 ≥ baseline | leaderboard 对比 |
| 2 | held-out 不回退 | composite_score 在所有 held-out repos 上 ≥ baseline - 0.02（允许噪声） | 在 held-out 上跑一轮评估 |
| 3 | 结构保真/不变式不下降 | `structural_fidelity` 和 `runtime_invariants` 维度 ≥ baseline | scorecard 对比 |
| 4 | 成本可接受 | token 用量 ≤ baseline × 1.3（允许 30% 增长换取质量提升） | cost_tokens 对比 |

**晋升流程**：
```
1. Proposer 生成候选 → manifest + patches
2. 在 search repo worktree 中评估 → eval-results
3. 检查条件 1: search set 提升？
   - 否 → reject，记录到 leaderboard，status = "rejected_search"
   - 是 → 继续
4. 在 held-out repo worktree 中评估 → eval-results
5. 检查条件 2-4: held-out 不回退 + 结构保真 + 成本？
   - 任一不满足 → reject，status = "rejected_held_out" / "rejected_fidelity" / "rejected_cost"
   - 全部满足 → promote
6. Promote：
   - 将 patches 应用到 harness 主文件
   - 更新 leaderboard baseline
   - 记录晋升原因到 harness-state.json learnings
   - 归档候选到 candidates/{id}/，status = "promoted"
```

**Reject 后的处理**：
- 被 reject 的候选保留在 `candidates/` 中（带 reject 原因），供 proposer 避免重复尝试
- 连续 3 次 reject 后，Proposer 暂停，等待人工 review traces 和 scorecard 后再重启

---

### 版本化搜索空间

**第一批允许 proposer 修改的文件**（低风险、高杠杆）：

| 文件 | 可修改范围 | 理由 |
|------|-----------|------|
| `harness/SKILL.md` | Worker prompt 模板措辞、Phase 检查步骤顺序 | 直接影响 Worker 输出质量 |
| `execution-policy.md` | 决策阈值、降级策略、并行分组规则 | 影响调度效率 |
| `verification-protocol.md` | 检查项权重、通过阈值 | 影响 scorecard 敏感度 |
| Hook 启用矩阵 | 哪些 Hook 在哪些阶段启用 | 影响执行流程 |
| Context packing / prompt 模板 | Worker prompt 的上下文段落顺序和格式 | 影响 cache 命中和 token 用量 |

**暂不允许 proposer 自动修改的文件**（需要人工审批）：

| 文件 | 原因 |
|------|------|
| 各 skill 主体内容（`*/SKILL.md`） | 改 skill 内容等于改领域知识，需要人工验证正确性 |
| `portable/cc-bound` 分类 | 分类错误会导致 Worker 误用 CC 特有实现 |
| `state-schema.md` 主结构 | 改 schema 会破坏跨会话状态兼容性 |
| 安全边界（路径约束、工具约束、递归防护） | 安全规则放松可能导致不可逆损害 |

---

### M0-M3 阶段总览

| 阶段 | 目标 | 输入 | 输出 | 前置 | 成功标准 |
|------|------|------|------|------|---------|
| M0 | 可观测 | 每轮 harness 执行 | traces/ + scorecard | P1 完成 | 连续 3 轮有完整 traces 且 scorecard 适用维度非空 |
| M1 | 可执行 | traces + verification-protocol | commands + hook scripts + tests | M0 稳定 | 回归测试全通过，commands 覆盖 5 类检查 |
| M2 | 可评估 | M1 的 commands + tests | candidates/ + leaderboard | M1 稳定 | 至少 1 个候选完成 A/B 评估且 leaderboard 有数据 |
| M3 | 可搜索 | M2 的 leaderboard + traces | proposer 自动生成 + promote/reject | M2 稳定 + 至少 1 个 held-out repo | 至少 1 个候选被 promote 且 held-out 不回退 |

### 与现有机制的关系速查

| 现有机制 | Meta Track 怎么用它 | 不动/扩展 |
|---------|-------------------|----------|
| `harness-state.json` state | 控制面，调度决策来源 | 不动 |
| `harness-state.json` learnings | traces 的摘要，继续保留 | 不动，但要求引用 trace 路径 |
| `harness-state.json` denial_tracking | 失败计数和降级 | 不动 |
| `harness-state.json` smoke_tests | scorecard 的一个子维度 | 不动，scorecard 是其超集 |
| `harness-state.json` constraints | Worker 约束注入 | 不动 |
| `verification-protocol.md` | M0 scorecard 的评估维度来源 | 不动，M1 为其添加 command façade |
| `harness-hooks-schema.md` | M1 hook scripts 的语义定义 | 不动，M1 为其添加可执行实例 |
