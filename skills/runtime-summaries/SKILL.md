---
name: runtime-summaries
description: "Agent 运行时如何让用户看到进度，而不是等到完成才知道结果"
user-invocable: true
argument-hint: "<目标项目路径或模块名>"
---

# 运行时摘要系统 (Runtime Summaries)

## 1. Problem — Agent 运行状态是黑盒，用户不知道它在做什么

Agent 执行任务时，用户面对的是等待。短任务还好，长任务（几分钟甚至更久）如果没有进度信息，用户会焦虑、失去信任、甚至中断任务。

这个问题在三个时间尺度上都存在：
- **秒级**：当前这批工具调用做了什么？
- **分钟级**：后台子 Agent 进展到哪里了？
- **会话级**：我离开一会儿回来，之前在做什么？

通用问题是：**如何在不同粒度上让用户感知 Agent 的运行状态，而不是等到完成才知道结果。**

---

## 2. In Claude Code — 源码事实

> `源码事实` — 以下内容可回钉到具体文件。

### Away Summary（会话级）

- 入口：`src/services/awaySummary.ts` → `generateAwaySummary()`
- 触发：用户离开一段时间后回来
- 输入：最近 30 条消息（`RECENT_MESSAGE_WINDOW = 30`）+ session memory 内容
- 模型：`getSmallFastModel()`（Haiku）
- 输出：1-3 句话，先说高层任务，再说具体下一步
- 工具：无（不给工具）
- Prompt 要求："Skip status reports and commit recaps"

### Agent Summary（分钟级）

- 入口：`src/services/AgentSummary/agentSummary.ts` → `startAgentSummarization()`
- 触发：每 30 秒（`SUMMARY_INTERVAL_MS = 30_000`）
- 输入：子 Agent 的 transcript（过滤不完整 tool_use）
- 模型：主模型（共享 `CacheSafeParams` 以复用 prompt cache）
- 输出：3-5 词，现在进行时（-ing 形式）
- 工具：全部 deny（通过 `canUseTool` 回调）
- Prompt 要求："Name the file or function, not the branch"
- 前一次摘要作为 negative 示例防重复

### Tool Use Summary（秒级）

- 入口：`src/services/toolUseSummary/toolUseSummaryGenerator.ts` → `generateToolUseSummary()`
- 触发：每批工具调用完成后
- 输入：工具 name + input + output 的 JSON
- 模型：`queryHaiku()`
- 输出：~30 字符，过去时态，类似 git commit subject
- Prompt 要求："think git-commit-subject, not sentence"

---

## 3. Transferable Pattern — 多粒度后台摘要 + 模型选择策略

> `抽象模式` — 从 CC 抽象出来的核心设计。

### 核心模式：粒度 × 模型 × 约束

```
每种摘要 = 触发条件 × 输入裁剪 × 模型选择 × 输出约束 × 失败策略
```

### 关键设计原则

1. **粒度决定模型**。高频低价值操作（工具摘要）用最小模型；低频高价值操作（away summary）也用小模型但给更多上下文。Agent summary 用主模型是为了复用 prompt cache，这是经济学优化而非质量需求。

2. **输出约束比输入丰富更重要**。3-5 词、30 字符、1-3 句话——每种摘要都有严格的长度/时态/内容约束。用 few-shot + negative 示例控制，不靠后处理截断。

3. **静默失败，不阻塞主流程**。所有摘要都是后台异步执行，失败时 log 但不抛异常。摘要是增强体验，不是核心功能。

4. **前一次输出作为下一次的 negative**。Agent summary 把上一次摘要告诉模型"说点新的"，避免连续 30 秒输出相同内容。

### 关键 Tradeoff

| 选择 | 好处 | 代价 |
|------|------|------|
| 小模型做摘要 | 低成本、低延迟 | 质量上限有限 |
| 共享 prompt cache | 节省 cache 创建成本 | 耦合主模型选择 |
| 严格长度约束 | UI 可预测 | 可能丢失重要细节 |
| 静默失败 | 不影响主流程 | 摘要缺失时用户无感知 |

---

## 4. Minimal Portable Version — 最小版：只做 Away Summary

> `最小版` — 如果只实现一种，Away Summary 性价比最高。

### 最小实现

```
1. 检测用户回来（idle 超过阈值 → 重新激活）
2. 取最近 N 条消息
3. 小模型非流式生成 1-3 句摘要
4. 显示为欢迎卡片 / 系统消息
```

不需要：定时器、子 Agent transcript 读取、prompt cache 共享、工具 JSON 序列化

### 升级路径

```
Level 0: Away Summary（用户回来时一次性摘要）
Level 1: + Tool Use Summary（每批工具后一行标签）
Level 2: + Agent Summary（子 Agent 定时进度）
Level 3: + prompt cache 共享优化成本
```

---

## 5. Do Not Cargo-Cult

> `不要照抄` — 以下是 CC 的具体实现选择。

1. **不要因为 CC 的 Agent Summary 间隔是 30 秒就照搬**。30 秒是 CC 基于 prompt cache TTL 和 token 成本权衡的结果。你的项目可能 10 秒或 60 秒更合适，取决于模型成本和用户期望。

2. **不要因为 CC 用 fork 子进程做 Agent Summary 就必须 fork**。CC fork 是为了隔离执行和共享 cache。如果你的 Agent 没有子进程概念，直接在主进程里做异步调用即可。

3. **不要因为 CC 有三种摘要就必须三种都做**。大多数项目只需要 Away Summary。Tool Use Summary 主要服务 SDK/移动端场景。Agent Summary 只在多 Agent 架构中有意义。

4. **不要因为 CC 的 Tool Use Summary 限制 30 字符就照搬这个数字**。30 字符是为了移动端 UI truncation。桌面端可以更长。

5. **不要因为 CC 把 session memory 注入 Away Summary 就认为必须有记忆系统**。没有 session memory 时，直接从最近消息生成摘要完全可行，只是质量略低。

---

## 6. Adaptation Matrix

> `迁移建议` — 不同项目形态下的裁剪方案。

| 项目类型 | 建议保留 | 建议简化或删掉 | 注意事项 |
|----------|---------|---------------|---------|
| **单进程 CLI Agent** | Away Summary | Agent Summary（无子 Agent）、Tool Use Summary（CLI 有完整输出） | 用户能看到工具输出，不需要额外摘要 |
| **对话式 Agent（类 CC）** | 三种全保留 | 可简化 prompt cache 共享 | 最接近 CC 原始设计 |
| **移动端 SDK** | Tool Use Summary + Away Summary | Agent Summary（移动端少用多 Agent） | 关注 30 字符 UI 约束 |
| **多 Agent 编排** | Agent Summary（核心需求） | Tool Use Summary（内部工具不需要展示） | 重点是子 Agent 进度可见性 |
| **Web 应用** | 三种都可用 | 可用更丰富的 UI（进度条、timeline） | WebSocket 推送实时摘要 |
| **轻量脚本** | Away Summary（如果有会话恢复） | 其他全删 | print 语句可能就够了 |

---

## 7. Implementation Steps

1. **识别用户等待点** — 列出所有用户需要等待的场景：API 调用、工具执行、子任务
2. **选择起始粒度** — 从 Away Summary 开始（最简单、性价比最高）
3. **实现摘要生成** — 选模型 + 写 Prompt（含长度/时态约束 + few-shot 示例）
4. **集成到 UI** — 决定展示位置（状态栏 / 卡片 / 系统消息 / toast）
5. **添加更多粒度** — 按需增加 Tool Use Summary 和 Agent Summary
6. **验证效果** — 检查：摘要是否准确？长度是否合适？用户是否真的在看？

---

## 8. Source Anchors

> CC 源码锚点，用于追溯和深入阅读。

| 关注点 | 文件 | 关键符号 |
|--------|------|---------|
| Away Summary 生成 | `src/services/awaySummary.ts` | `generateAwaySummary()`, `RECENT_MESSAGE_WINDOW` |
| Agent Summary 定时器 | `src/services/AgentSummary/agentSummary.ts` | `startAgentSummarization()`, `SUMMARY_INTERVAL_MS` |
| Agent Summary Prompt | `src/services/AgentSummary/agentSummary.ts` | `buildSummaryPrompt()` |
| Tool Use Summary 生成 | `src/services/toolUseSummary/toolUseSummaryGenerator.ts` | `generateToolUseSummary()` |
| Tool Use Summary Prompt | `src/services/toolUseSummary/toolUseSummaryGenerator.ts` | `TOOL_USE_SUMMARY_SYSTEM_PROMPT` |
| Session Memory 集成 | `src/services/SessionMemory/sessionMemoryUtils.ts` | `getSessionMemoryContent()` |
