---
name: magic-docs
description: "文档如何随对话自动演进，而不是写完就过期"
user-invocable: true
argument-hint: "<目标项目路径或模块名>"
---

# 自动维护文档 (Magic Docs)

## 1. Problem — 文档与代码脱节，手动维护成本高

几乎所有项目都有这个问题：文档写完就过期。代码在演进，文档停在上次有人记得更新的那一天。

根本原因是文档维护依赖人的自觉——改完代码后还记得去改文档的人永远是少数。

这个 skill 解决的通用问题是：**如何让文档随 Agent 对话自动演进，变成"活文档"而不是"历史快照"。**

---

## 2. In Claude Code — 源码事实

> `源码事实` — 以下内容可回钉到具体文件和函数。

**入口与注册**

- 初始化入口：`src/services/MagicDocs/magicDocs.ts` → `initMagicDocs()`
- 当前仅对内部用户启用（`USER_TYPE === 'ant'` 门控）
- 通过 `registerFileReadListener()` 监听所有 FileRead 工具调用
- 文件首行匹配 `^#\s*MAGIC\s+DOC:\s*(.+)$` 时自动注册到 `trackedMagicDocs: Map<string, MagicDocInfo>`
- 紧随标题的斜体行（`*...*` 或 `_..._`）被提取为自定义更新指令

**后台更新链**

- 触发点：`registerPostSamplingHook()` 注册的 post-sampling 钩子
- 前置条件：`querySource === 'repl_main_thread'` 且 `!hasToolCallsInLastAssistantTurn(messages)`（仅主线程空闲时）
- 整个更新函数被 `sequential()` 包装，防止并发
- 对每个追踪文档：
  1. `cloneFileStateCache()` 并删除当前文档条目 → 绕过 dedup，确保读到最新内容
  2. `FileReadTool.call()` 读取最新内容；文件不存在或标记被移除则取消追踪
  3. `buildMagicDocsUpdatePrompt()` 构建 Prompt（支持 `{{docContents}}` `{{docPath}}` `{{docTitle}}` `{{customInstructions}}` 变量替换）
  4. `runAgent()` 以 Sonnet 模型 fork 子 Agent 执行更新

**安全约束**

- `canUseTool` 白名单：子 Agent 仅允许使用 `Edit` 工具，且路径严格限制为当前文档
- 子 Agent 不能创建新文件、不能修改其他文件
- `forkContextMessages: messages` 传入完整对话上下文，让子 Agent 能提取相关信息

**Prompt 工程**

- 默认模板在 `src/services/MagicDocs/prompts.ts` → `getUpdatePromptTemplate()`
- 用户可在 `~/.claude/magic-docs/prompt.md` 放置自定义模板，加载失败静默回退
- 变量替换用单遍 `replace()` 实现，避免 `$` 反向引用和双重替换

---

## 3. Transferable Pattern — 标记检测 + 后台增量更新的自动文档演进模式

> `抽象模式` — 从 Claude Code 抽象出来，这个系统的核心是三个机制的组合。

### 核心模式：被动检测 → 延迟更新 → 就地修改

```
文件被读取
  → 检测是否有特殊标记
  → 有标记则注册到追踪列表（去重）

对话空闲时
  → 遍历追踪列表
  → 对每个文档 fork 隔离的更新 Agent
  → Agent 拿到完整对话上下文，就地更新文档
```

### 关键设计原则

1. **被动触发，不是主动扫描**。文档在被自然读取时才注册，不需要启动时扫描全目录。这让成本与使用频率成正比。

2. **空闲时更新，不干扰主流程**。更新发生在对话轮次结束后，不阻塞用户交互。

3. **就地更新，不是追加日志**。文档反映当前状态，过时信息被替换而非保留。这与 changelog 模式相反。

4. **隔离执行，最小权限**。更新 Agent 只能编辑目标文档，不能修改其他文件。这防止后台任务产生意外副作用。

5. **串行防并发**。多个文档按顺序更新，避免竞态条件和资源争抢。

### 关键 Tradeoff

| 选择 | 好处 | 代价 |
|------|------|------|
| 被动检测（读取时注册） | 零配置，按需启动 | 未被读取的文档不会更新 |
| 空闲时触发 | 不干扰主流程 | 更新有延迟 |
| 就地修改 | 文档永远是最新状态 | 丢失历史版本（依赖 git） |
| fork 子 Agent | 隔离风险 | 额外 token 消耗 |

---

## 4. Minimal Portable Version — 最小版：手动触发更新

> `最小版` — 如果目标项目没有 CC 那么复杂，从这里开始。

最小可用版本只需要三个组件：

### 4.1 标记检测器

```
输入：文件内容字符串
输出：{ title, instructions? } | null
逻辑：正则匹配首行标记 + 提取可选指令行
```

### 4.2 手动触发命令

不需要自动监听和后台钩子。提供一个命令（如 `/update-docs`），手动触发时：
1. 扫描工作目录下所有带标记的 Markdown 文件
2. 对每个文件调用 LLM 生成更新
3. 就地写入

### 4.3 更新 Prompt 模板

包含以下要素的 Prompt 即可：
- 当前文档内容
- 文档标题和自定义指令
- 对话上下文（或项目上下文）
- 编辑规则（保留标记头、就地更新、不追加历史）

**不需要的**：
- 不需要 FileRead 监听器（手动触发替代）
- 不需要 post-sampling 钩子（手动触发替代）
- 不需要 FileStateCache 克隆（无 dedup 问题）
- 不需要 fork 子 Agent（直接调用 LLM）

---

## 5. Do Not Cargo-Cult

> `不要照抄` — 以下是 CC 的具体实现选择，不是通用最佳实践。

1. **不要因为 CC 用 `sequential()` 串行更新，就认为所有项目都不能并行更新文档**。CC 串行是因为它的 FileStateCache 需要隔离。如果你的系统没有文件状态缓存，并行更新多个文档完全可行。

2. **不要因为 CC 用 post-sampling 钩子自动触发，就认为必须做自动触发**。对于小项目或低频场景，手动触发（命令 / CI 步骤 / git hook）更简单、更可控、更省 token。

3. **不要因为 CC 用 fork 子 Agent 执行更新，就把简单的文档更新也拆成多 Agent 架构**。如果你的 Agent 运行时不支持 fork，直接用单次 LLM 调用 + 文件写入就够了。

4. **不要因为 CC 的标记格式是 `# MAGIC DOC:`，就照搬这个前缀**。标记格式应该适配你的项目约定。frontmatter 字段、文件名后缀、目录约定都是有效的替代方案。

5. **不要因为 CC 限制子 Agent 只用 Edit 工具，就认为更新文档只能用 patch 式编辑**。对于小文档，整体重写可能比精确 patch 更简单可靠。

---

## 6. Adaptation Matrix

> `迁移建议` — 不同项目形态下的裁剪方案。

| 项目类型 | 建议保留 | 建议简化或删掉 | 注意事项 |
|----------|---------|---------------|---------|
| **单进程 CLI Agent** | 标记检测 + 手动触发更新 | 自动监听、post-sampling 钩子、子 Agent fork | 用命令触发即可，不需要后台机制 |
| **对话式 Agent（类 CC）** | 完整模式：监听 + 自动触发 + 子 Agent | 可简化 FileStateCache 隔离逻辑 | 最接近 CC 原始设计，注意 token 成本 |
| **CI/CD 流水线** | 标记检测 + 批量扫描更新 | 所有运行时监听和钩子 | 在 pipeline 步骤中触发，用 git diff 确定哪些文档需要更新 |
| **IDE 插件** | 标记检测 + 文件保存时触发 | post-sampling 钩子 | 用 IDE 的文件变更事件替代 FileRead 监听 |
| **多人协作项目** | 标记检测 + git hook 触发 + 冲突处理 | 自动后台更新（可能引起 git 冲突） | 考虑在 PR 阶段而非实时更新 |

---

## 7. Implementation Steps

> 让 Agent 在用户项目里落地时的动作顺序。

### Step 1 — 评估需求

- 项目是否有需要持续维护的文档？（架构文档、API 文档、决策日志、入门指南）
- 文档更新频率如何？高频 → 自动触发值得投入；低频 → 手动触发足够
- 项目有无现成的 Agent 运行时？有 → 集成到已有钩子；无 → 独立脚本

### Step 2 — 实现标记检测

- 定义标记格式（可复用 `# MAGIC DOC:` 或自定义）
- 实现检测函数：输入文件内容，输出标题 + 可选指令
- 在现有文档上添加标记，验证检测正确

### Step 3 — 实现更新逻辑

- 编写 Prompt 模板，包含：当前内容、标题、指令、上下文
- 实现变量替换（单遍替换，避免双重替换）
- 选择触发方式：手动命令 / 文件事件监听 / CI 步骤 / git hook
- 实现文件写入（就地更新）

### Step 4 — 添加安全边界

- 限制更新范围：只修改带标记的文件
- 保留标记头不被修改
- 错误处理：文件不存在、标记被移除、写入失败

### Step 5 — 验证

- 在一个文档上测试完整流程
- 检查更新质量：是否反映了最新信息、是否保留了标记头、是否就地更新而非追加
- 检查 git diff：更新内容是否合理、有无意外修改

---

## 8. Source Anchors

> CC 源码锚点，用于追溯和深入阅读。

| 关注点 | 文件 | 关键符号 |
|--------|------|---------|
| 初始化与监听注册 | `src/services/MagicDocs/magicDocs.ts` | `initMagicDocs()`, `registerFileReadListener()` |
| 标记检测 | `src/services/MagicDocs/magicDocs.ts` | `detectMagicDocHeader()`, `MAGIC_DOC_HEADER_PATTERN` |
| 追踪状态 | `src/services/MagicDocs/magicDocs.ts` | `trackedMagicDocs: Map`, `registerMagicDoc()` |
| 后台更新入口 | `src/services/MagicDocs/magicDocs.ts` | `updateMagicDocs` (sequential 包装), `updateMagicDoc()` |
| 子 Agent 定义 | `src/services/MagicDocs/magicDocs.ts` | `getMagicDocsAgent()`, `canUseTool` |
| Prompt 构建 | `src/services/MagicDocs/prompts.ts` | `buildMagicDocsUpdatePrompt()`, `getUpdatePromptTemplate()` |
| 变量替换 | `src/services/MagicDocs/prompts.ts` | `substituteVariables()` |
| 自定义 Prompt 加载 | `src/services/MagicDocs/prompts.ts` | `loadMagicDocsPrompt()` → `~/.claude/magic-docs/prompt.md` |
| FileStateCache 隔离 | `src/utils/fileStateCache.ts` | `cloneFileStateCache()` |
| 串行执行 | `src/utils/sequential.ts` | `sequential()` |
| post-sampling 钩子 | `src/utils/hooks/postSamplingHooks.ts` | `registerPostSamplingHook()` |
