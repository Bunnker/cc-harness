---
name: agent-tool-budget
description: "指导如何设计 Agent 工具预算管理：两条独立预算线（工具数量 vs token）+ 三层工具数（Registered Pool / Visible Catalog / Fully-Loaded Schemas）+ Schema 延迟加载 + 结果截断 + 描述 1% 预算 + token budget 自动续跑。工具数量阈值为本仓库工程启发式，非 Anthropic 官方量化。"
user-invocable: false
argument-hint: "<目标项目路径或模块名>"
---

# Agent 工具预算管理 (Agent Tool Budget)

> 参考实现：Claude Code `src/tools.ts` + `src/tools/ToolSearchTool/` + `src/utils/api.ts` + `src/query/tokenBudget.ts`
> — 工具数量控制、schema 延迟加载、工具结果大小限制、Skill 描述 1% 预算、输出 token 自动续跑
>
> **姊妹 skill**：`tool-authoring` 讲"单个工具怎么写"，本 skill 讲"工具集怎么管"。

## 核心思想

**Agent 的 context 是稀缺资源——工具描述、工具结果、输出 token 都在争夺同一个窗口。** CC 对每个环节都有独立的预算控制，防止任何一个环节吃掉整个 context。

### 两条独立的预算线（容易混淆）

```
线 A：token 预算       线 B：工具数量预算
────────────────      ──────────────────
衡量：context 字节     衡量：可见工具条目数
瓶颈：硬上限 200K      瓶颈：模型"选择成本"
对策：延迟加载 + 截断   对策：默认集裁剪 + defer
```

**这两条会互相影响但优化手段不同**：
- 工具描述很短（10 词）但 100 个工具 → 线 A 没爆，但线 B 让模型"选不对"
- 工具只有 3 个但每个 prompt 5000 字 → 线 B 没爆，但线 A 吃 context

Anthropic 官方对线 A（格式/上下文开销）的建议见 [Building Effective Agents](https://www.anthropic.com/research/building-effective-agents)；对线 B（MCP 工具 defer 加载）的记录见 [How Claude Code Works](https://code.claude.com/docs/en/how-claude-code-works) 的 *"MCP tool definitions are deferred by default and loaded on demand via tool search"*。**官方并没有给出"多少工具太多"的硬数字**——下文的具体阈值（Simple = 3 / 默认完整 schema 集 ≈ 15-20）来自本仓库对 CC 源码（`src/tools.ts`）的实测读数，属**本项目的工程启发式**，不是 Anthropic 指南。

核心策略：**不需要的不加载（线 A+B），看得见的要精选（线 B），太大的截断（线 A），用完了自动续跑（线 A 输出侧）。**

---

## 一、工具数量预算（线 B）

### 三个必须区分的"工具数"

讨论规模前先锁术语。工具数有三层，**数量从大到小，混用就会互相打架**：

| 术语 | 含义 | 数量来源 | 典型量级 |
|------|------|---------|---------|
| **注册池 (Registered Pool)** | 代码里声明并注册过的全部 Tool 实例（含特性门控/MCP server 全部暴露的） | `src/tools.ts:getAllBaseTools()` + `_build_registry()` 返回值 | CC：40+，cc-python：26+ |
| **可见目录 (Visible Catalog)** | 初始 prompt 里模型**能看到的条目**（含 deferred 的名字和短描述） | 注册池 − 被 deny rule / feature gate 屏蔽的 | CC：30-50，cc-python：~26 |
| **完整 Schema 集 (Fully-Loaded Schemas)** | 初始 prompt 里**带 `input_schema` 的条目**（deferred 工具不算，只有 ToolSearch 激活后才加入） | 可见目录 − deferred 条目 | **这是选择成本最敏感的指标** |

**本 skill 下文所有"N 个工具"都特指"完整 Schema 集"，除非标注。**

### 三种阈值的职责

| 阈值 | 针对层 | 性质 | 来源 |
|------|-------|------|------|
| Simple 档 = **3**（Bash/Read/Edit） | 完整 Schema 集 | 硬编码常量 | `src/tools.ts:272-298` 读码 |
| 推荐默认 = **完整 Schema 集控制在 <20** | 完整 Schema 集 | **本项目工程启发式** | 本仓库经验，非 Anthropic |
| 注册池可以 **40+** | 注册池 | 无上限（靠 defer 控制暴露） | 实测 CC 行为 |

> **注意**：前一版本把 "<20" 当成 Anthropic 官方量化。核查后，Anthropic 官方文档只给"MCP 默认 defer"的定性说法，**没有给具体数字**。本 skill 用的 <20 是**本仓库工程实测经验**，不是引用。如果你要用到生产，建议自己在目标场景做 eval 确认。

### 问题

当**完整 Schema 集**超过 ~20 条，模型倾向于：
1. 在工具选择上消耗更多"思考 token"（推理前反复列举、对比）
2. 选错工具（特别是语义接近的，比如多个 MCP server 都有 `Read`）
3. 放弃调用工具（直接用自然语言回答，明明有工具可用）

这是**选择成本随工具数超线性增长**的经验现象，不仅是 token 字节的问题。

### CC 的三档规模

CC 源码用**环境变量 + 特性门控**把三层工具数分成三档（`src/tools.ts:272-298`）。下表**严格区分"初始 prompt 带 schema 的"与"runtime 扩展后的"**，避免 §一 定义被自己违反。

| 档位 | 触发方式 | 初始 Schema 集（Fully-Loaded） | Runtime 扩展可达 | 注册池 | 场景 |
|------|---------|-----------------------------|-----------------|--------|------|
| **Simple** | `CLAUDE_CODE_SIMPLE=1` | 基础 **3**：`Bash / Read / Edit`；**COORDINATOR_MODE=on 时 6**（追加 `AgentTool / TaskStopTool / SendMessageTool`） | 同左（Simple 档不启用 ToolSearch 和 MCP） | 基础 3 / coordinator 模式 6 | 学习 / 最小 agent / 单目的脚本 |
| **默认** | 普通启动（非 simple） | **~15-20**（无条件 base + 符合条件的特性门控） | 初始 Schema 集 **+ ToolSearch 激活的 deferred 内置工具 + Skill 展开的** | **40+**（含未激活的 feature-gated 和所有 `shouldDefer=true` 的内置） | 日常开发 |
| **Enterprise** | 默认档 + MCP servers | **~15-20**（**MCP 工具也默认 `defer`**，不进初始 Schema 集，与默认档相同） | 默认档 Runtime 扩展 **+ ToolSearch 激活的 MCP 工具**（`mcp__<srv>__*`） | **40-60+**（全部 registered，含未加载的 MCP + 未激活的特性门控） | 多工具协作、IDE 集成 |

> **两个要点**：
> 1. **默认档本身就有 deferred 内置工具**（`shouldDefer=true` 的 built-in），通过 ToolSearch 激活。不是"必须装 MCP 才能用 defer"。
> 2. **Enterprise 档和默认档的初始 Schema 集量级相同**（都 ~15-20），差异只在 Runtime 扩展列里是否包含 MCP。"15-20"不是因为 Enterprise 没工具，而是 MCP 工具默认 defer 不进"初始 Schema 集"——这正是 §一 三层术语想说清楚的事。
>
> Simple 档的意义不是"给小白用"，而是**提示最小可运行集合是什么**。写新 agent 从 Simple 档起步，按需加工具，比从 40 个里删更清晰。

**源码引用**（`src/tools.ts:287-296`）：

```typescript
const simpleTools: Tool[] = [BashTool, FileReadTool, FileEditTool]
// When coordinator mode is also active, include AgentTool and TaskStopTool
if (feature('COORDINATOR_MODE') && coordinatorModeModule?.isCoordinatorMode()) {
  simpleTools.push(AgentTool, TaskStopTool, getSendMessageTool())  // +3 → 共 6
}
return filterToolsByDenyRules(simpleTools, permissionContext)
```

### 三种规模裁剪的技术手段

```
技术手段              → 效果
─────────────────    ─────────────────────────────────
1. 特性门控             → 按环境变量 on/off 整批工具
2. Deny rules (config) → 用户/管理员静态禁用某工具
3. shouldDefer + ToolSearch → 进 prompt 但不含 schema
4. 命名空间前缀        → `mcp__<srv>__*` 避免跨源冲突
5. Skill 声明式         → Skill 只在被调用时展开到工具
```

四种手段可组合。CC 的 MCP 工具同时用了 2（可 deny）、3（默认 defer）、4（前缀隔离）。

### MCP 工具的特殊处理

**默认所有 MCP 工具 defer**，因为：
1. MCP 服务器数量可变（一个开发机可能连 10+ 个 server）
2. 每个 server 可能暴露 5-20 个工具
3. 累积起来很容易超过 40 个条目
4. 模型一次用到的通常只是一两个 server

```typescript
// src/tools.ts — isDeferredTool()
function isDeferredTool(tool): boolean {
  if (tool.alwaysLoad) return false
  if (tool.isMcp) return true              // ← MCP 默认 defer
  if (tool.name === 'ToolSearch') return false
  return tool.shouldDefer === true
}
```

**效果**：初始 prompt 里 MCP 工具只有**名字和一句短描述**（~10 token/工具），schema 不加载。模型需要时用 `ToolSearch` 发现并激活。

### 命名空间与冲突避免

MCP 工具的 name 强制前缀 `mcp__<server>__<tool>`：

```
内置：        Read
MCP server A: mcp__filesystem__read
MCP server B: mcp__s3__read
```

这让**三个"Read"共存**不互相干扰。代价是 token 多占一点，收益是跨源可并存。Skill 内部定义的工具通常不加前缀（由 Skill 加载器保证无冲突）。

### 选择成本的反面：可发现性

裁剪不是越狠越好。反向陷阱：**工具藏太深模型永远想不到去用**。

CC 的平衡：
- **核心工具**（Bash/Read/Edit）**永不 defer**，一定在初始 prompt
- **Skill 列表**常驻（1% 预算，详见 §四）——让模型至少知道"有这些可能性"
- **MCP server 列表**（不是工具）常驻——`/mcp` 命令可查

**设计原则**：**入口常驻，细节按需**。模型要能看到"有没有"，用的时候再看"怎么用"。

---

## 二、工具 Schema 延迟加载

### 问题

50 个工具 × 每个 ~200 token 的 schema = ~10,000 token。首轮 API 请求就吃掉 5% 的 context。

### CC 的解决方案：shouldDefer + ToolSearch

```typescript
// 标记为延迟的工具 → 首轮只发名字，不发 schema
{
  name: "SQLTool",
  defer_loading: true    // ← API 只看到名字
  // 没有 input_schema → 模型不能直接调用
}

// 模型需要时 → 调用 ToolSearch
ToolSearch({ query: "SQL" })
  → 返回 SQLTool 的完整 schema
  → 模型现在可以调用 SQLTool 了
```

### 哪些工具该延迟

```typescript
function isDeferredTool(tool): boolean {
  if (tool.alwaysLoad) return false       // 明确标记"始终加载"
  if (tool.isMcp) return true             // MCP 工具默认延迟
  if (tool.name === 'ToolSearch') return false  // 搜索工具本身不延迟
  if (tool.name === 'Agent' && forkSubagentExperimentEnabled()) return false
  if (tool.name === 'Brief') return false
  if (tool.name === 'SendUserFile') return false
  return tool.shouldDefer === true
}
```

**效果**：50 个工具 → 首轮只发 15 个完整 + 35 个只有名字。token 降低 ~60%。

### 自动判断是否启用延迟加载

```typescript
// 只在 deferred tools 的描述 token 超过阈值时启用
const threshold = contextWindowTokens * 0.10  // 10% 的 context
const deferredTools = tools.filter(isDeferredTool)
const descriptionTokens = deferredTools.reduce((sum, t) => sum + estimateTokens(t.description), 0)

if (descriptionTokens < threshold && pendingMcpServers === 0) {
  useToolSearch = false  // 工具不多，全部内联
}
```

**源码边界**：

- 真实阈值统计的是 **deferred tools 的描述体积**，不是所有工具
- 只要还有 `pending` MCP servers，ToolSearch 也不能关，否则服务器连上后模型失去发现新工具的入口
- 还要满足模型支持 `tool_reference`，否则 ToolSearch 直接禁用

---

## 三、工具结果大小限制

### 问题

`cat large_file.ts` 返回 500KB → 占满整个 context 窗口。

### CC 的解决方案：maxResultSizeChars + 磁盘持久化

```typescript
// 不同工具有不同的结果上限
FileReadTool:  maxResultSizeChars = Infinity  // 特例：永不持久化（会造成循环读）
BashTool:      maxResultSizeChars = 100_000   // 100K 字符
MCPTool:       maxResultSizeChars = 100_000
GrepTool:      maxResultSizeChars = 100_000

// 超过阈值 → 保存到磁盘 + 模型收到摘要
if (result.length > tool.maxResultSizeChars) {
  const diskPath = saveToSessionFile(result)
  return `结果过大（${result.length} 字符），已保存到 ${diskPath}。
前 1000 字符预览：
${result.slice(0, 1000)}
...
使用 Read 工具读取完整内容。`
}
```

**为什么 FileReadTool 是 Infinity**：如果 Read 结果也被持久化到磁盘，模型会再调 Read 读那个文件 → 又持久化 → 无限循环。所以 Read 的结果永远内联返回。

### 工具结果的时间衰减（微压缩）

```typescript
// 旧的工具结果随时间被替换为占位符
const TIME_BASED_CLEARED = '[Old tool result content cleared]'

// 超过 maxAge 轮次的 Read/Bash/Grep 结果 → 替换
for (const msg of messages) {
  if (msg.type === 'tool_result' && msg.age > config.maxAge) {
    msg.content = TIME_BASED_CLEARED
  }
}
```

---

## 四、Skill 描述预算

### 问题

100 个 Skill 的描述 → 占满 context 的 10%。

### CC 的解决方案：1% 预算 + 三级降级

```typescript
const SKILL_BUDGET_PERCENT = 0.01  // 上下文的 1%
const MAX_PER_ENTRY = 250           // 每个 Skill ≤250 字符

function formatSkillsWithinBudget(skills, contextTokens) {
  const budget = contextTokens * 4 * 0.01  // 1% × 4 chars/token

  // Level 1: 尝试完整描述
  const full = skills.map(s => `- ${s.name}: ${s.description}`).join('\n')
  if (full.length <= budget) return full

  // Level 2: 内置 Skill 保留完整，其他均分
  const bundled = skills.filter(s => s.source === 'bundled')
  const rest = skills.filter(s => s.source !== 'bundled')
  const bundledText = bundled.map(s => `- ${s.name}: ${s.description}`)
  const remaining = budget - bundledText.join('\n').length
  const perSkill = Math.floor(remaining / rest.length)

  if (perSkill >= 20) {
    return [...bundledText, ...rest.map(s =>
      `- ${s.name}: ${s.description.slice(0, perSkill)}`
    )].join('\n')
  }

  // Level 3: 极端情况 → 非内置只显示名字
  return [...bundledText, ...rest.map(s => `- ${s.name}`)].join('\n')
}
```

**核心原则**：内置 Skill 的描述永不截断（核心功能可发现性 > 空间节省）。

---

## 五、Prompt Cache 稳定性 — 排序 + Schema 缓存键

### 工具列表排序保证 Cache Hit

```typescript
// src/tools.ts — assembleToolPool()
const byName = (a, b) => a.name.localeCompare(b.name)
return uniqBy(
  [...builtIn].sort(byName).concat(allowedMcp.sort(byName)),
  'name',
)
```

**为什么排序**：Prompt cache 对工具列表的顺序敏感。如果 MCP 服务器每次返回工具的顺序不同（很常见），不排序 → cache miss → 重新计费。排序后无论返回顺序如何，最终顺序都一致。

### Schema 缓存键策略

```typescript
// src/utils/api.ts — toolToAPISchema()
const cacheKey =
  'inputJSONSchema' in tool && tool.inputJSONSchema
    ? `${tool.name}:${jsonStringify(tool.inputJSONSchema)}`  // MCP: name + schema
    : tool.name                                                // 内置: 只用 name

toolSchemaCache.set(cacheKey, schema)
```

**为什么 MCP 工具用 name + schema**：MCP 服务器可能动态改变工具的 schema（比如添加新字段）。如果只用 name 做缓存键，schema 变了但缓存没失效 → 模型用旧 schema 调用 → 参数不匹配。

**为什么内置工具只用 name**：内置工具的 schema 在编译期固定，不会运行时变。用 name 做键更简单。

### 已发现工具状态要跨 compact 保留

ToolSearch 不是“搜完就结束”，它会把结果写成 `tool_reference` blocks。

后续请求会从历史里提取这些 `tool_reference`，只把已经发现过的 deferred tools 继续发给 API。

这会碰到一个问题：

- 原始 `tool_reference` 消息一旦被 compact 摘要掉
- 系统就会失去“哪些 deferred tools 已经加载过”的状态

CC 的解法是：

- compact 前先提取 discovered tool set
- 写进 `compact_boundary.compactMetadata.preCompactDiscoveredTools`
- compact 后从 boundary 把状态读回来

**设计含义**：动态工具加载要保留的不是“原消息本身”，而是“已加载工具状态”。

### 双层描述系统

```typescript
// Tool 接口有两个描述方法
description(input, options): string   // 短描述（工具列表用，≤250 字符）
prompt(options): string               // 完整提示（发给 API 的 tool description）

// 短描述：用于 ToolSearch 列表、UI 显示
// 完整提示：包含使用指南、参数说明、示例。缓存到 session 级。
```

**为什么分两层**：ToolSearch 列表需要简短（节省 token），但模型调用工具时需要详细指导。分层让两个场景各自优化。

---

## 六、输出 Token Budget 自动续跑

### 问题

模型生成到一半被 max_output_tokens 截断 → 结果不完整。

### CC 的解决方案：Token Budget + 递减收益检测

```typescript
// 用户指定预算："+500k"、"spend 1M tokens"
// 解析为 token 数
const budget = parseTokenBudget(userMessage)  // 500000

// 每轮结束检查
function checkTokenBudget(tracker, agentId, budget, turnTokens) {
  // 子代理不参与这条续跑机制
  if (agentId) return { action: 'stop' }

  const pct = turnTokens / budget

  // 90% 以下 → 继续
  if (pct < 0.9) {
    return {
      action: 'continue',
      nudgeMessage: `Token budget ${Math.round(pct * 100)}% used. Continue.`
    }
  }

  // 递减收益检测：3+ 次续跑后，连续两轮增量 < 500 token
  if (tracker.continuationCount >= 3) {
    const delta1 = turnTokens - tracker.lastGlobalTurnTokens
    const delta2 = tracker.lastDeltaTokens
    if (delta1 < 500 && delta2 < 500) {
      return { action: 'stop', diminishingReturns: true }
    }
  }

  return { action: 'stop' }
}
```

**源码边界**：

- token budget continuation 只对顶层对话生效，`agentId` 存在时直接停用
- 递减收益检测不是“一低就停”，而是 **至少 3 次 continuation 之后**，连续两轮增量都 `<500` token 才停

### 续跑提示注入

当决定继续时，系统注入一条 meta user message：

```
"Output token limit reached. You have used 45% of your budget (225,000/500,000 tokens).
Resume directly from where you stopped. Do not repeat previous content."
```

模型不知道这是系统注入的——它看起来就像用户说"继续"。

### Max Output Tokens 升级

```
默认 max_output_tokens = 8K
  ↓
模型输出到 8K 被截断
  ↓
Level 1: 升级到 64K（一次性）
  ↓
模型输出到 64K 被截断
  ↓
Level 2: 注入续跑消息（最多 3 次）
  ↓
3 次都用完 → 停止
```

---

## 七、预算分配全景（两条预算线的会合）

### 线 A：Token 预算（字节视角）

```
┌─────────────── Context Window（200K tokens）──────────────┐
│                                                            │
│  System Prompt     ≈ 5-10K  （静态段缓存，动态段每次重建）  │
│  工具 Schema       ≈ 2-5K   （延迟加载后首轮减少 60%）     │
│  Skill 列表        ≈ 2K     （1% 预算，三级降级）          │
│  CLAUDE.md         ≈ 1-5K   （用户指令）                   │
│  MEMORY.md 索引    ≈ 0.5-1K （≤200 行）                    │
│  附件              ≈ 1-3K   （记忆、任务、Agent 列表）     │
│  ─────────────────────────────────────────                │
│  对话历史 + 工具结果  ≈ 剩余所有空间                        │
│  （工具结果有 per-tool maxResultSizeChars 限制）           │
│  （旧结果随时间被微压缩清除）                              │
│                                                            │
└────────────────────────────────────────────────────────────┘

输出预算：
  默认 8K → 可升级到 64K → 可续跑 3 次
  用户指定 +500K → 自动续跑到 90% + 递减收益检测
```

### 线 B：工具数量预算（条目视角）

> 下图按"**完整 Schema 集** → **可见目录** → **注册池**"三层展开。数字是本仓库对 CC 的实测建议，不是 Anthropic 官方量化。

```
┌─── 完整 Schema 集（模型能直接调用）──────────┐
│                                              │
│  ★ 核心工具（永不 defer）      3-6   条      │
│      Bash / Read / Edit / Grep / Glob        │
│      + 项目高频自定义工具                    │
│                                              │
│  ○ 默认集（初始 prompt 含 schema）+ ~12-15 条 │
│      Write / Agent / WebFetch / Notebook     │
│      + 按特性门控激活的工具                  │
│                                              │
│  合计建议上限 < 20 条（工程启发式）           │
└──────────────────────────────────────────────┘
           ↑ 以下不计入"完整 Schema 集"
┌─── 可见目录（名字 + 短描述可见）──────────┐
│                                            │
│  ▸ Skill 列表（描述常驻 / 内容按需）1% 预算│
│                                            │
│  ▸ MCP 工具（默认 defer）                  │
│      `mcp__<server>__*` name + search_hint │
│      ToolSearch 激活后才加入完整 Schema 集 │
└────────────────────────────────────────────┘
           ↑ 以下不计入"可见目录"
┌─── 注册池（代码里声明但未暴露给模型）────┐
│  feature-gated 未激活的工具               │
│  deny-rule 屏蔽的工具                     │
│  全量 MCP server 里 ToolSearch 未加载的   │
└───────────────────────────────────────────┘
```

### 两条线的互相影响矩阵

| 场景 | 线 A 压力 | 线 B 压力 | 典型对策 |
|------|----------|----------|---------|
| 工具少（<10）但 prompt 很长 | 高 | 低 | 精简 prompt；启用 defer 只发名字 |
| 工具多（>40）但每个描述短 | 中 | 高 | 裁剪默认集到核心；MCP 全 defer |
| Skill/MCP 爆炸（100+ 条目） | 高 | 高 | Skill 1% 预算；MCP defer；ToolSearch |
| 单轮工具结果巨大（500KB） | 高 | — | `maxResultSizeChars` 持久化到磁盘 |
| 对话多轮累积 | 高 | — | 旧结果微压缩清除 + 主动 compact |
| 模型选错工具频率高 | — | 高 | 裁剪语义相近工具；强化 prompt 边界说明 |

---

## 八、实现模板

### 工具结果预算

```python
class ToolResultBudget:
    DEFAULT_MAX_CHARS = 100_000
    EXEMPT_TOOLS = {'Read'}  # 不限制的工具（防循环读）

    def apply(self, tool_name: str, result: str) -> str:
        if tool_name in self.EXEMPT_TOOLS:
            return result

        max_chars = self.DEFAULT_MAX_CHARS
        if len(result) <= max_chars:
            return result

        # 持久化到磁盘
        path = self._save_to_disk(result)
        preview = result[:1000]
        return f"结果过大（{len(result)} 字符），已保存到 {path}。\n预览：\n{preview}\n..."

    def clear_old_results(self, messages: list, max_age_turns: int) -> list:
        """微压缩：清除旧工具结果"""
        for i, msg in enumerate(messages):
            if (msg.get('type') == 'tool_result' and
                msg.get('age', 0) > max_age_turns and
                msg.get('tool_name') not in self.EXEMPT_TOOLS):
                msg['content'] = '[旧工具结果已清除]'
        return messages
```

### 描述预算

```python
class DescriptionBudget:
    def __init__(self, context_tokens: int, budget_pct: float = 0.01):
        self.budget_chars = int(context_tokens * 4 * budget_pct)
        self.max_per_entry = 250

    def format(self, items: list[dict], core_names: set[str]) -> str:
        """三级降级：完整 → 均分 → 只显示名字"""
        # Level 1: 完整
        full = '\n'.join(f"- {i['name']}: {i['desc'][:self.max_per_entry]}" for i in items)
        if len(full) <= self.budget_chars:
            return full

        # Level 2: 核心完整 + 其他均分
        core = [i for i in items if i['name'] in core_names]
        rest = [i for i in items if i['name'] not in core_names]
        core_text = '\n'.join(f"- {i['name']}: {i['desc']}" for i in core)
        remaining = self.budget_chars - len(core_text)
        per_item = max(20, remaining // max(len(rest), 1))

        if per_item >= 20:
            rest_text = '\n'.join(f"- {i['name']}: {i['desc'][:per_item]}" for i in rest)
            return core_text + '\n' + rest_text

        # Level 3: 只显示名字
        return core_text + '\n' + '\n'.join(f"- {i['name']}" for i in rest)
```

### 工具数量预算（线 B）

```python
from dataclasses import dataclass, field

@dataclass
class ToolScaleBudget:
    """按"条目预算"裁剪工具集，与 token 预算正交。"""
    max_always_loaded: int = 20          # 初始 prompt 里完整 schema 的工具上限
    core_tools: set[str] = field(default_factory=set)  # 核心工具，永不 defer

    def classify(self, tools: list) -> tuple[list, list]:
        """返回 (always_loaded, deferred) 两组。"""
        always, deferred = [], []
        for t in tools:
            # 1. 核心 + alwaysLoad 永不 defer
            if t.name in self.core_tools or getattr(t, 'always_load', False):
                always.append(t)
                continue
            # 2. MCP 工具默认 defer
            if getattr(t, 'is_mcp', False):
                deferred.append(t)
                continue
            # 3. 显式标记的 defer
            if getattr(t, 'should_defer', False):
                deferred.append(t)
                continue
            always.append(t)

        # 4. 超出上限 → 把 always 末尾的（非核心）移到 deferred
        if len(always) > self.max_always_loaded:
            overflow = [t for t in always if t.name not in self.core_tools]
            overflow = overflow[self.max_always_loaded:]
            deferred.extend(overflow)
            always = [t for t in always if t not in overflow]

        return always, deferred

    def render_for_prompt(self, always: list, deferred: list) -> dict:
        """初始 prompt 里展示的两段。"""
        return {
            "full_tools": [t.get_schema() for t in always],   # 完整 schema
            "deferred_catalog": [                             # 只有名字+一句描述
                {"name": t.name, "hint": t.search_hint or t.short_description}
                for t in deferred
            ],
        }

# 用法：
budget = ToolScaleBudget(
    max_always_loaded=20,
    core_tools={"Bash", "Read", "Edit", "Grep", "Glob"},
)
always, deferred = budget.classify(all_tools)
# always 进初始 prompt，deferred 通过 ToolSearch 激活
```

---

## 九、实施步骤

请分析用户的 $ARGUMENTS 中指定的项目，然后**按两条预算线分别盘点与实施**：

### 线 B：工具数量预算（先做，影响 A）

1. **数核心工具** — 用户 90% 时间用哪 3-6 个？这是"永不 defer"名单。
2. **列默认集** — **完整 Schema 集**上限建议 < 20（本仓库工程启发式）。超出的按规则（MCP 默认 / shouldDefer 标记 / 语义相近合并）移到"可见目录"层（走 ToolSearch）或直接留在"注册池"（feature gate off）。
3. **MCP 工具默认 defer** — 只在初始 prompt 暴露 `name + search_hint`，schema 由 ToolSearch 按需加载。
4. **命名空间隔离** — 多源工具加前缀（`mcp__<srv>__*`）防冲突。
5. **Skill 入口常驻** — Skill 列表给 1% 预算（三级降级），Skill 内容只在被激活时展开。

### 线 A：Token 预算（后做，精细化）

6. **盘点 context 消耗**：system prompt、工具 schema（按 §七 的分段）、工具结果、对话历史各占多少 token。
7. **工具结果限制**：每个工具设置 `max_result_size_chars`，超出持久化到磁盘 + 模型收到摘要。Read 工具例外（`Infinity`）防循环读。
8. **描述预算**：Skill/Plugin 列表走 1% 预算 + 三级降级。内置优先级永远保留完整描述。
9. **微压缩**：旧工具结果（>10 轮）自动替换为占位符。
10. **输出 token 管理**：支持 `max_output_tokens` 升级（8K → 64K 一次性）+ 续跑（最多 3 次）+ 递减收益检测（连续两轮增量 <500 才停）。
11. **预算仪表盘**：`/context` 类命令显示每组件的 token 占用，找优化点。

### 反模式警告

**线 B 相关**：
- ❌ 不要把所有可能用到的工具都加进默认集 — 选择成本比 token 成本更隐蔽
- ❌ 不要一次 defer 核心工具 — 看不见就不会被用
- ❌ 不要让工具命名语义相近（`read` / `fetch` / `load` 三个工具都能读文件）— 模型会猜错

**线 A 相关**：
- ❌ 不要所有工具的 schema 都在首轮发送 — 延迟加载节省 60%
- ❌ 不要让 Read 工具的结果被持久化 — 会造成循环读取
- ❌ 不要截断核心功能的描述 — 核心功能可发现性 > 空间节省
- ❌ 不要无限续跑 — 递减收益检测防止无意义的 token 消耗
- ❌ 不要忘了旧结果的时间衰减 — 10 轮前的 `ls` 结果不再有价值

---

## 十、与 `tool-authoring` 的协同

两个 skill 是"**微观 + 宏观**"的关系：

| 维度 | `tool-authoring`（单个工具） | `agent-tool-budget`（工具集） |
|------|----------------------------|----------------------------|
| 关注点 | 一个工具的四层合同、三层 prompt、错误语义 | 多个工具的规模控制、加载策略、预算 |
| 输出 | 一个高质量工具定义 | 一个高效可扩展的工具池 |
| 关键字段 | `isReadOnly / isConcurrencySafe / isDestructive / description / prompt` | `shouldDefer / alwaysLoad / maxResultSizeChars / searchHint` |
| 反面 | 写成万能工具（`file_op` 做 Read+Edit+Delete） | 把所有工具都加进默认集 |
| 成本度量 | 单次调用 token + 调用正确率 | 总工具数 + 常驻 schema token |

**协同的决策顺序**：

```
1. tool-authoring：把每个工具写得精简且职责单一
        ↓
2. agent-tool-budget：把这些工具分三档（核心 / 默认 / defer）
        ↓
3. tool-authoring（回看）：如果 token 吃不消，回去精简 prompt
```

两者**不可相互替代**：
- 只做 tool-authoring：工具很好但集合臃肿，模型选不对
- 只做 agent-tool-budget：裁剪干净但每个工具写得糟，模型调不对

### 何时看哪个

| 症状 | 先看 |
|------|------|
| 模型频繁选错工具 | `tool-authoring` §2「三层 Prompt 结构」Level 2 段（使用指南/边界说明） |
| 模型不用本该用的工具 | `agent-tool-budget` §一 可发现性 或 `tool-authoring` §2「三层 Prompt 结构」Level 1 段（description） |
| 首轮 API 请求 context 已超 10% | `agent-tool-budget` §二 Schema 延迟加载 |
| 工具结果单次超 50K | `agent-tool-budget` §三 maxResultSizeChars |
| 模型对同名工具混淆（多 MCP server） | `agent-tool-budget` §一 命名空间前缀 |
| 工具参数格式错误率高 | `tool-authoring` §2「三层 Prompt 结构」Level 3 段（字段 `.describe()`） |
