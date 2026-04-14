---
name: session-memory
description: "会话中途压缩后如何保留工作状态，避免 Agent 失忆"
user-invocable: true
argument-hint: "<目标项目路径或模块名>"
---

# 会话级记忆 (Session Memory)

## 1. Problem — compact 压缩后丢失工作状态

长对话 Agent 在 compact（上下文压缩）后会丢失详细的工作状态——正在修的文件、遇到的错误、做过的决策。摘要能保留"大概在做什么"，但细节（如"UserService.ts:42 的 NPE 已修复，还需要跑测试"）会在压缩中丢失。

通用问题是：**如何在单会话内持续提取关键工作信息，使得即使对话被压缩，Agent 仍能恢复工作状态而不是从头理解。**

---

## 2. In Claude Code — 源码事实

> `源码事实` — 以下内容可回钉到具体文件。

**核心文件**

| 文件 | 职责 |
|------|------|
| `src/services/SessionMemory/sessionMemory.ts` | 主逻辑：阈值检查 + fork Agent 提取 + 初始化 |
| `src/services/SessionMemory/prompts.ts` | 模板管理：10 段模板 + 段落 token 预算 + Prompt 构建 |
| `src/services/SessionMemory/sessionMemoryUtils.ts` | 状态工具：配置管理 + 提取状态机 + 阈值函数 |
| `src/services/compact/sessionMemoryCompact.ts` | Compact 联动：基于 session memory 的替代压缩模式 |

**触发机制（源码验证 `sessionMemory.ts:134-178 shouldExtractMemory()`）**

```
决策链（AND/OR 组合）：
  1. 初始化检查：tokens >= minimumMessageTokensToInit（默认 10,000）
     → 首次满足时 markSessionMemoryInitialized()，后续跳过此检查
  
  2. Token 阈值：tokensSinceLastExtraction >= minimumTokensBetweenUpdate（默认 5,000）
     → 这个条件 ALWAYS REQUIRED，即使 tool call 条件满足也必须等 token 阈值
  
  3. Tool call 阈值：toolCallsSinceLastUpdate >= toolCallsBetweenUpdates（默认 3）
  
  4. 空闲检查：!hasToolCallsInLastAssistantTurn（最后一轮 assistant 无工具调用）
  
  触发条件 = (token阈值 AND tool阈值) OR (token阈值 AND 空闲)
  → 设计理由：token 阈值防止过频提取，空闲条件确保在自然对话间隙提取
```

- 并发防护：`markExtractionStarted()` / `markExtractionCompleted()` + 15 秒超时 + 1 分钟过期检测

**提取执行**

- 使用 `runForkedAgent()` fork 子 Agent 执行
- 共享 `CacheSafeParams` 以复用 prompt cache
- `canUseTool` 白名单：仅允许 `FileEditTool`，仅限 session memory 文件路径
- `skipTranscript: true`（不记录到会话 transcript）
- 记录 token 消耗 + 更新 `lastSummarizedMessageId`

**10 段模板**

```
Session Title | Current State | Task specification
Files and Functions | Workflow | Errors & Corrections
Codebase and System Documentation | Learnings | Key results | Worklog
```

**段落预算**

- 每段上限：2,000 tokens
- 总量上限：12,000 tokens
- 超限时生成警告注入到提取 Prompt

**Session Memory Compact**

- `src/services/compact/sessionMemoryCompact.ts` 提供替代压缩模式
- 条件：session memory 已初始化 + 特性门控
- 逻辑：从 `lastSummarizedMessageId` 之后保留消息（上限 40K tokens）
- 用 session memory 内容作为上下文前缀，无需 API 调用
- 保持 `tool_use`/`tool_result` 对的完整性

---

## 3. Transferable Pattern — 后台周期提取 + 模板化记忆

> `抽象模式` — 从 CC 抽象出来的核心设计。

### 核心模式：阈值触发 → 后台提取 → 模板化存储 → 压缩时恢复

```
对话进行中
  → 累计 token 达到阈值
  → 后台 fork Agent 提取关键信息
  → 按固定模板结构化存储到文件
  → 对话被压缩时，session memory 文件作为上下文恢复

关键循环：提取 → 存储 → 压缩时注入 → 继续对话 → 再次提取
```

### 关键设计原则

1. **提取而非记录**。不是把对话原文存下来，而是用 LLM 提取高价值信息。10,000 tokens 的对话可能只有 500 tokens 值得记住。

2. **模板约束输出**。固定的段落结构（任务/文件/错误/决策）让提取结果可预测、可检索。避免 LLM 自由发挥产生不可控输出。

3. **预算控制体积**。段落 token 上限防止单段膨胀，总量上限防止整体膨胀。超限时 Prompt 中注入警告要求精简。

4. **增量更新而非重写**。每次提取是在已有内容上更新，而非从头重写。这保留了之前提取的信息，同时加入新信息。

5. **压缩联动是核心价值**。Session memory 不仅是"笔记"——它直接参与 compact 决策。有 session memory 时可以跳过完整 API 摘要，直接裁剪到 `lastSummarizedId` 之后。

### 关键 Tradeoff

| 选择 | 好处 | 代价 |
|------|------|------|
| 后台 fork Agent | 不阻塞主对话 | 额外 token 消耗 |
| 固定模板 | 输出可预测 | 可能不适合所有任务类型 |
| Token 预算 | 体积可控 | 可能丢失有价值信息 |
| 增量更新 | 保留历史信息 | 过时信息需要被主动清理 |

---

## 4. Minimal Portable Version — 最小版：手动 /summary 命令

> `最小版` — 如果目标项目没有 CC 那么复杂，从这里开始。

### 最小实现

```
1. 定义一个命令（如 /summary）
2. 触发时把最近 N 条消息 + 一段 Prompt 发给 LLM
3. LLM 按模板提取关键信息
4. 写入一个 Markdown 文件
5. Compact 时读取该文件作为上下文前缀
```

不需要：自动阈值检测、后台 fork、段落 token 预算、并发防护

### 升级路径

```
Level 0: 手动 /summary（用户主动触发）
Level 1: + 自动阈值触发（token 数达标时自动提取）
Level 2: + 模板结构化（固定段落 + 段落预算）
Level 3: + 后台异步执行（不阻塞主对话）
Level 4: + Compact 联动（session memory 参与压缩决策）
```

---

## 5. Do Not Cargo-Cult

> `不要照抄` — 以下是 CC 的具体实现选择。

1. **不要因为 CC 有 9 个段落就照搬 9 个段落**。段落数量和内容应该适配你的使用场景。编码助手可能需要"Files and Functions"，但客服 Agent 可能需要"Customer Context"和"Resolution History"。

2. **不要因为 CC 用 fork Agent 提取就必须 fork**。如果你的 Agent 没有 fork 能力，直接在主循环的空闲时段做一次非流式 LLM 调用即可。Fork 是为了隔离和 cache 共享，不是必需的。

3. **不要因为 CC 的阈值是 10K/5K tokens 就照搬这些数字**。这些数字是 CC 基于 Opus 模型的上下文窗口和 compact 阈值调出来的。你的模型和窗口大小不同，阈值也应该不同。

4. **不要因为 CC 用 Markdown 文件存储就认为必须用文件**。数据库、内存、KV store 都是有效的存储方案。CC 用文件是因为它的记忆系统整体基于文件系统。

5. **不要因为 CC 有 Session Memory Compact 模式就认为 session memory 必须和 compact 深度耦合**。最简单的集成方式是：compact 时把 session memory 文件内容插到摘要 prompt 里，不需要替代整个 compact 流程。

---

## 6. Adaptation Matrix

> `迁移建议` — 不同项目形态下的裁剪方案。

| 项目类型 | 建议保留 | 建议简化或删掉 | 注意事项 |
|----------|---------|---------------|---------|
| **单进程 CLI Agent** | 手动 /summary + 模板 | 自动阈值、fork、并发防护 | 先从手动触发开始 |
| **对话式 Agent（类 CC）** | 完整模式 | 可减少段落数 | 最接近 CC 原始设计 |
| **API 服务（无状态）** | 不适用 | 全部 | 每次请求独立，不需要会话记忆 |
| **多轮对话 Bot** | 自动阈值 + 简单模板 | fork、段落预算 | 重点关注"上次聊到哪"而非编码细节 |
| **IDE Agent** | 自动阈值 + 文件/函数段落 | Worklog、Learnings | 段落设计围绕编码上下文 |
| **轻量脚本** | 不适用 | 全部 | 对话太短不需要 |

---

## 7. Implementation Steps

1. **评估需求** — 你的对话通常多长？如果很少超过模型上下文窗口，可能不需要 session memory
2. **设计模板** — 列出 3-5 个最有价值的信息类别（如 Task / Files / Errors / Decisions）
3. **实现手动提取** — 一个命令 + 一段 Prompt + 文件写入
4. **集成到 compact** — compact 时读取 session memory 文件，插入到摘要 prompt 或作为上下文前缀
5. **添加自动触发** — 监控 token 数，达到阈值时自动提取
6. **添加预算控制** — 段落 token 上限 + 总量上限 + 超限警告
7. **验证恢复质量** — compact 后 Agent 是否能继续工作？丢失了哪些信息？

---

## 8. Source Anchors

> CC 源码锚点，用于追溯和深入阅读。

| 关注点 | 文件 | 关键符号 |
|--------|------|---------|
| 提取主逻辑 | `src/services/SessionMemory/sessionMemory.ts` | `extractSessionMemory()`, `shouldExtractMemory()` |
| 手动触发 | `src/services/SessionMemory/sessionMemory.ts` | `manuallyExtractSessionMemory()` |
| 阈值检查 | `src/services/SessionMemory/sessionMemoryUtils.ts` | `hasMetInitializationThreshold()`, `hasMetUpdateThreshold()` |
| 并发防护 | `src/services/SessionMemory/sessionMemoryUtils.ts` | `markExtractionStarted()`, `markExtractionCompleted()` |
| 模板与预算 | `src/services/SessionMemory/prompts.ts` | `DEFAULT_TEMPLATE`, `analyzeSectionSizes()`, `buildSessionMemoryUpdatePrompt()` |
| Compact 联动 | `src/services/compact/sessionMemoryCompact.ts` | `trySessionMemoryCompaction()`, `shouldUseSessionMemoryCompaction()` |
| 自定义模板加载 | `src/services/SessionMemory/prompts.ts` | `loadSessionMemoryTemplate()` → `~/.claude/session-memory/config/` |
