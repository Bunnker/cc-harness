---
name: agent-tool-budget
description: "指导如何设计 Agent 工具预算管理：延迟加载 + 结果截断 + 描述预算 + token budget 自动续跑"
user-invocable: true
argument-hint: "<目标项目路径或模块名>"
---

# Agent 工具预算管理 (Agent Tool Budget)

> 参考实现：Claude Code `src/tools/ToolSearchTool/` + `src/utils/api.ts` + `src/query/tokenBudget.ts`
> — 工具 schema 延迟加载、工具结果大小限制、Skill 描述 1% 预算、输出 token 自动续跑

## 核心思想

**Agent 的 context 是稀缺资源——工具描述、工具结果、输出 token 都在争夺同一个窗口。** CC 对每个环节都有独立的预算控制，防止任何一个环节吃掉整个 context。核心策略：**不需要的不加载，太大的截断，用完了自动续跑。**

---

## 一、工具 Schema 延迟加载

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

## 二、工具结果大小限制

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

## 三、Skill 描述预算

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

## 四、Prompt Cache 稳定性 — 排序 + Schema 缓存键

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

## 五、输出 Token Budget 自动续跑

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

## 五、预算分配全景

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

---

## 六、实现模板

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

---

## 七、实施步骤

请分析用户的 $ARGUMENTS 中指定的项目，然后：

1. **盘点 context 消耗**：system prompt、工具描述、工具结果、对话历史各占多少
2. **工具 schema 延迟加载**：工具超过 20 个时，非核心工具标记 shouldDefer
3. **工具结果限制**：每个工具设置 maxResultSize，超出持久化到磁盘
4. **描述预算**：如果有 Skill/Plugin 列表，设置 token 预算 + 三级降级
5. **微压缩**：旧工具结果随时间自动清除，释放空间
6. **输出 token 管理**：支持 max_output_tokens 升级 + 续跑 + 递减收益检测
7. **预算仪表盘**：记录每个组件的 token 消耗，找出优化点

**反模式警告**：
- 不要所有工具的 schema 都在首轮发送 — 延迟加载节省 60%
- 不要让 Read 工具的结果被持久化 — 会造成循环读取
- 不要截断核心功能的描述 — 核心功能可发现性 > 空间节省
- 不要无限续跑 — 递减收益检测防止无意义的 token 消耗
- 不要忘了旧结果的时间衰减 — 10 轮前的 `ls` 结果不再有价值
