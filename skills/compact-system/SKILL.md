---
name: compact-system
description: "长对话上下文膨胀时，如何通过分级压缩保持 Agent 可用"
user-invocable: false
argument-hint: "<目标项目路径或模块名>"
---

# 多级上下文压缩系统 (Compact System)

## 1. Problem — 上下文膨胀导致 Agent 不可用

LLM 的上下文窗口是有限资源。长对话中工具结果不断累积，最终超过窗口限制，API 拒绝请求。简单的"全部总结"方案成本高且丢失细节。

通用问题是：**如何在上下文逼近窗口极限时，用最小成本裁剪最低价值的内容，同时保留 Agent 继续工作所需的关键信息。**

---

## 2. In Claude Code — 源码事实（源码验证版）

> `源码事实` — 以下内容逐函数回钉到具体文件和行号。

### 压缩触发链（按序评估，首个命中短路）

| 级别 | 名称 | 成本 | 入口 | 触发条件（精确 if 判断） |
|------|------|------|------|---------|
| L1 | Snip | 零 API | `applyToolResultBudget()` | 单个工具结果超过 token 阈值，在 API 调用前截断 |
| L2a | Time-based Micro Compact | 零 API | `microCompact.ts:446 maybeTimeBasedMicrocompact()` | `evaluateTimeBasedTrigger()`: config.enabled && querySource 是 main thread && 距上次 assistant > gapThresholdMinutes（默认 60 分钟）→ 内容替换为占位符 |
| L2b | Cached Micro Compact | 零 API（cache_edits API） | `microCompact.ts:276 cachedMicrocompactPath()` | feature('CACHED_MICROCOMPACT') && isCachedMicrocompactEnabled() && isModelSupported && isMainThreadSource → 通过 cache_edits API 删除旧 tool results，不修改本地消息 |
| L3 | Auto Compact | 一次 API 调用 | `autoCompact.ts:241 autoCompactIfNeeded()` | `shouldAutoCompact()`: 非 session_memory/compact 递归 && isAutoCompactEnabled() && 非 context-collapse 模式 && tokens >= threshold |

**注意**：Context Collapse 是独立的上下文管理系统（feature-gated），当它开启时会**抑制** Auto Compact（`autoCompact.ts:215-223`），不是压缩流水线的一级。

### Micro Compact 源码细节

**COMPACTABLE_TOOLS 白名单**（`microCompact.ts:41-50`，精确列表）：
```
Read, Bash/Shell, Grep, Glob, WebSearch, WebFetch, Edit, Write
```
**不是"跳过只读工具"——是"只压缩这些工具的结果"**。不在白名单中的工具（如 Agent、TodoWrite、NotebookEdit）的结果永远不被微压缩。

**时间驱动路径**（`evaluateTimeBasedTrigger` → `maybeTimeBasedMicrocompact`）：
- 配置：`TimeBasedMCConfig = { enabled: false（默认关）, gapThresholdMinutes: 60, keepRecent: 5 }`
- `keepRecent` 下限强制为 1（`Math.max(1, config.keepRecent)`）——清空所有结果会让模型丧失工作上下文
- 清理后重置 cachedMCState（`resetMicrocompactState()`）——因为内容变化导致 server cache 失效

**Cached MC 路径**（ant-only，feature-gated）：
- 不修改本地消息内容——通过 `cache_edits` API 指令在服务端删除
- 只在 main thread 运行——防止 fork 子 Agent 的 tool_result 注册到全局 state 中污染主线程

### Auto Compact 决策链（`autoCompactIfNeeded` `autoCompact.ts:241-351`）

```
决策顺序：
  1. DISABLE_COMPACT 环境变量 → 直接返回 false
  2. 断路器：consecutiveFailures >= 3 → 跳过（防止 irrecoverable 上下文无限重试）
  3. shouldAutoCompact() → 检查 token 阈值
     3a. 递归防护：querySource 是 session_memory/compact/marble_origami → 返回 false
     3b. isAutoCompactEnabled() → 检查 3 个开关（DISABLE_COMPACT, DISABLE_AUTO_COMPACT, config）
     3c. Context Collapse 开启时 → 返回 false（让 collapse 管理上下文）
     3d. tokens >= autoCompactThreshold
  4. 优先尝试 Session Memory Compact
     成功 → runPostCompactCleanup() + markPostCompaction() + return
  5. 回退到 Full Recompaction（compactConversation）
     成功 → consecutiveFailures = 0
     失败 → consecutiveFailures++ → 达到 3 次触发断路器
```

**断路器**（`MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES = 3`，`autoCompact.ts:70`）：BQ 数据显示 1,279 个会话有 50+ 连续失败（最高 3,272 次），浪费 ~250K API 调用/天。

### Session Memory Compact 决策链（`sessionMemoryCompact.ts:514-630`）

```
判断条件（全部满足才执行）：
  1. shouldUseSessionMemoryCompaction() → session_memory + sm_compact 两个 feature flag 都开
  2. session memory 文件存在且非空模板
  3. lastSummarizedMessageId 存在且能在消息中找到（找不到 → 回退 legacy）
  
保留消息的计算（calculateMessagesToKeepIndex，:324-397）：
  起点 = lastSummarizedIndex + 1
  向后扩展直到同时满足：
    - totalTokens >= minTokens（默认 10,000）
    - textBlockMessageCount >= minTextBlockMessages（默认 5）
  硬上限：maxTokens（默认 40,000）
  下限：不超过上一次 compact boundary
  最后：adjustIndexToPreserveAPIInvariants() 保证 tool_use/tool_result 对和 thinking 块完整
  
安全检查：如果压缩后 token > autoCompactThreshold → 返回 null（SM-compact 不够，交给 Full）
```

### Full Recompaction 重试策略（`compact.ts`）

| 重试类型 | 上限 | 策略 |
|---------|------|------|
| PTL（Prompt Too Long） | `MAX_PTL_RETRIES = 3` | 截断头部最老的 API-round groups，直到 tokenGap 被覆盖 |
| 流式中断 | `MAX_COMPACT_STREAMING_RETRIES = 2` | 重新发起流式请求 |
| 图片处理 | 压缩前 | `stripImagesFromMessages()` 替换为文本标记（防止图片导致 PTL） |

### 后压缩恢复（`compact.ts:533-561, 1415-1450`）

**文件恢复**：
- 从 `readFileState` 按 timestamp 倒序取最近 `POST_COMPACT_MAX_FILES_TO_RESTORE = 5` 个文件
- 每个文件上限 `POST_COMPACT_MAX_TOKENS_PER_FILE = 5,000` tokens
- 排除：plan 文件、所有 claude.md 类型文件、task output 路径
- 排除已在 preservedMessages 中通过 Read 工具读取过的文件

**状态恢复**：
- plan attachment（如果有活跃 plan）
- plan mode instructions（如果在 plan mode 中）
- skill attachment（如果本 session 调用过 skill，上限 `POST_COMPACT_MAX_TOKENS_PER_SKILL = 5,000`，总预算 `POST_COMPACT_SKILLS_TOKEN_BUDGET = 25,000`）
- async agent attachments（如果有后台 Agent）
- deferred tools delta、MCP instructions delta、agent listing delta

### `runPostCompactCleanup()` 清理的完整列表（`postCompactCleanup.ts:31-77`）

```
所有 compact 路径共享（无条件执行）：
  1. resetMicrocompactState() — 重置 cached MC 的 tool 注册和 pinned edits
  2. clearSystemPromptSections() — 清空系统提示段落缓存
  3. clearClassifierApprovals() — 清空分类器审批缓存
  4. clearSpeculativeChecks() — 清空投机执行检查缓存
  5. clearBetaTracingState() — 清空 beta 追踪状态
  6. clearSessionMessagesCache() — 清空会话消息缓存

仅主线程 compact 执行（子 Agent compact 不执行，防止污染主线程状态）：
  7. resetContextCollapse() — 重置 context collapse（feature-gated）
  8. getUserContext.cache.clear() — 清空 getUserContext 记忆缓存
  9. resetGetMemoryFilesCache('compact') — 重置 CLAUDE.md 文件缓存
  10. sweepFileContentCache() — 清理 commit attribution 文件内容缓存（feature-gated）

刻意不清理的：
  - invoked skill content（技能内容必须跨 compact 存活，供后续 compact attachment 使用）
  - sentSkillNames（避免每次 compact 后重新注入 ~4K tokens 的 skill_listing）
```

### 有效窗口计算（`autoCompact.ts:33-49`）

```
effectiveWindow = contextWindowForModel - min(maxOutputTokens, 20_000)
autoCompactThreshold = effectiveWindow - 13_000（AUTOCOMPACT_BUFFER_TOKENS）

// 可通过环境变量覆盖：
// CLAUDE_CODE_AUTO_COMPACT_WINDOW → 覆盖 contextWindow 上限
// CLAUDE_AUTOCOMPACT_PCT_OVERRIDE → 按百分比设阈值（取 min(百分比阈值, 默认阈值)）
```

---

## 3. Transferable Pattern — 分级递进压缩

> `抽象模式` — 从 CC 抽象出来的核心设计。

### 核心模式：从最廉价的操作开始，逐级升级

```
上下文预算检查
  → Level 1: 裁剪（单条超大结果截断，零成本）
  → Level 2: 清理（旧工具结果替换占位符，零成本）
  → Level 3: 折叠（中间段结构化折叠，零成本）
  → Level 4: 摘要（API 调用生成总结，高成本）
     → 优先 Session Memory Compact（无 API 调用）
     → 回退 Full Recompaction（一次 API 调用）
```

### 关键设计原则（源码验证版）

1. **分级递进，首个命中短路**。`microcompactMessages()` 中 time-based 路径命中后直接 return，不再走 cached MC。`autoCompactIfNeeded()` 中 SM-compact 成功后不再走 Full Recompaction。

2. **保护边界完整性**。`adjustIndexToPreserveAPIInvariants()`（sessionMemoryCompact.ts:232-314）向后回溯保证 tool_use/tool_result 对 + 同 message.id 的 thinking 块不被拆分。

3. **双路径策略 + 安全降级**。SM-compact 如果压缩后仍超过 threshold → 返回 null → 交给 Full Recompaction。这不是"优先"而是"能做就做，不能做就让路"。

4. **压缩后清理区分主线程和子 Agent**。`runPostCompactCleanup()` 检查 `isMainThreadCompact`——子 Agent 压缩只做 6 项通用清理，不碰 7-10 项主线程状态。否则子 Agent 的 compact 会破坏主线程的 getUserContext 缓存。

5. **三层断路器保护**。(a) autoCompact 连续失败 ≥ 3 次 → 停止重试（autoCompact.ts:70）；(b) PTL 截断重试 ≤ 3 次（compact.ts:227）；(c) 流式重试 ≤ 2 次（compact.ts:131）。

6. **递归防护**。`shouldAutoCompact()` 明确排除 `querySource` 为 session_memory / compact / marble_origami 的请求——防止压缩子 Agent 触发自身的压缩。

7. **keepRecent 下限为 1**。time-based MC 强制 `Math.max(1, keepRecent)`——清空所有 tool results 等于让模型失去全部工作上下文。

### 关键 Tradeoff

| 选择 | 好处 | 代价 |
|------|------|------|
| 分 4 级 | 大多数情况零 API 成本 | 实现复杂度高 |
| 时间驱动微压缩 | 自适应用户使用模式 | 需要追踪时间间隔 |
| Session Memory Compact | 零 API 调用压缩 | 依赖 session memory 系统 |
| 后压缩文件恢复 | 保留最近工作上下文 | 额外 token 消耗 |

---

## 4. Minimal Portable Version — 最小版：token 监控 + 单级压缩

> `最小版` — 如果目标项目没有 CC 那么复杂，从这里开始。

### 最小实现

```
1. 每轮 API 调用前估算当前 token 数
2. 超过阈值（如 80% 窗口）→ 触发压缩
3. 把所有消息发给模型 → 生成摘要
4. 用摘要替换旧消息
5. 保持 tool_use/tool_result 对完整性
```

不需要：分级流水线、时间驱动微压缩、Session Memory Compact、文件恢复、缓存清理

### 升级路径

```
Level 0: 单级压缩（全量摘要）
Level 1: + 结果截断（超大单条结果先裁剪）
Level 2: + 时间清理（旧结果替换占位符）
Level 3: + Session Memory 联动（零成本压缩路径）
Level 4: + 后压缩恢复（文件/plan/skill 状态恢复）
```

---

## 5. Do Not Cargo-Cult

> `不要照抄` — 以下是 CC 的具体实现选择。

1. **不要因为 CC 有 4 级就照搬 4 级结构**。如果你的 Agent 对话通常不超过窗口的 50%，一个简单的全量摘要就够了。分级是为了高频长对话场景的成本优化。

2. **不要因为 CC 的微压缩跳过只读工具结果就照搬这个白名单**。CC 的白名单是基于"哪类工具结果信息密度最高"的经验判断。你的项目可能有不同的工具类型和信息价值分布。

3. **不要因为 CC 用 fork 子 Agent 做摘要就必须 fork**。直接在主循环中做一次非流式 LLM 调用即可。CC fork 是为了隔离和 cache 共享。

4. **不要因为 CC 恢复最近 5 个文件就照搬这个数字**。文件恢复数量取决于你的上下文窗口大小和用户工作模式。有些项目可能需要恢复 10 个文件，有些不需要恢复任何文件。

5. **不要因为 CC 有 GrowthBook 远程配置阈值就必须做远程配置**。本地硬编码阈值完全可行。CC 用远程配置是为了 A/B 测试不同阈值的效果。

6. **不要因为 CC 在压缩后清理十几种缓存就认为你也需要这么多**。CC 的缓存种类多是因为它的系统复杂度高。你的项目可能只需要清理 prompt cache 一种。

---

## 6. Adaptation Matrix

> `迁移建议` — 不同项目形态下的裁剪方案。

| 项目类型 | 建议保留 | 建议简化或删掉 | 注意事项 |
|----------|---------|---------------|---------|
| **单进程 CLI Agent** | 单级压缩 + 结果截断 | 微压缩、Session Memory Compact、文件恢复 | 对话通常不长，简单方案足够 |
| **对话式 Agent（类 CC）** | 完整 4 级 | 可简化后压缩恢复逻辑 | 最接近 CC 原始设计 |
| **API 服务（无状态）** | 不适用 | 全部 | 每次请求独立，不需要压缩 |
| **长会话 Bot** | 单级压缩 + 微压缩 | Session Memory Compact、4 级流水线 | 关注成本控制 |
| **多 Agent 编排** | 每个子 Agent 独立压缩 | 跨 Agent 共享压缩 | 子 Agent 生命周期短，可能不需要压缩 |

---

## 7. Implementation Steps

1. **测量对话长度** — 你的典型对话会超过模型窗口吗？不超过则不需要压缩
2. **实现 token 估算** — 每轮 API 调用前估算当前消息的 token 总量
3. **确定阈值** — 有效窗口 = 总窗口 - 输出预留。建议在 80% 时触发压缩
4. **实现单级压缩** — 全量消息 → 模型摘要 → 替换旧消息。注意保持 tool_use/tool_result 对
5. **添加结果截断** — 单条超大结果（如大文件内容）先裁剪到合理大小
6. **添加时间清理** — 旧工具结果替换为占位符（可选，长会话场景收益高）
7. **添加后压缩清理** — 压缩后清理所有受影响的缓存
8. **验证** — 压缩后 Agent 是否能继续工作？丢失了哪些关键信息？

---

## 8. Source Anchors（源码验证版）

> CC 源码锚点，用于追溯和深入阅读。

| 关注点 | 文件 | 关键符号 | 行号参考 |
|--------|------|---------|---------|
| Auto Compact 触发 | `autoCompact.ts` | `shouldAutoCompact()`, `autoCompactIfNeeded()` | :160, :241 |
| 断路器 | `autoCompact.ts` | `MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES = 3` | :70 |
| 有效窗口 | `autoCompact.ts` | `getEffectiveContextWindowSize()`, `getAutoCompactThreshold()` | :33, :72 |
| Time-based MC | `microCompact.ts` | `evaluateTimeBasedTrigger()`, `maybeTimeBasedMicrocompact()` | :422, :446 |
| Cached MC | `microCompact.ts` | `cachedMicrocompactPath()`, `COMPACTABLE_TOOLS` | :305, :41 |
| 时间配置 | `timeBasedMCConfig.ts` | `TimeBasedMCConfig`, `getTimeBasedMCConfig()` | :18, :36 |
| Full Recompaction | `compact.ts` | `compactConversation()`, `MAX_PTL_RETRIES = 3` | :387, :227 |
| SM Compact 主逻辑 | `sessionMemoryCompact.ts` | `trySessionMemoryCompaction()`, `calculateMessagesToKeepIndex()` | :514, :324 |
| SM Compact 配置 | `sessionMemoryCompact.ts` | `DEFAULT_SM_COMPACT_CONFIG`, `SessionMemoryCompactConfig` | :57, :47 |
| 边界完整性 | `sessionMemoryCompact.ts` | `adjustIndexToPreserveAPIInvariants()` | :232 |
| 后压缩清理 | `postCompactCleanup.ts` | `runPostCompactCleanup()` | :31 |
| 文件恢复 | `compact.ts` | `createPostCompactFileAttachments()`, `POST_COMPACT_MAX_FILES_TO_RESTORE = 5` | :1415, :122 |
| 恢复排除 | `compact.ts` | `shouldExcludeFromPostCompactRestore()` | :1674 |
| 状态恢复总预算 | `compact.ts` | `POST_COMPACT_TOKEN_BUDGET = 50_000` | :123 |
