---
name: unified-tool-interface
description: "工具契约由多层共同形成：Tool/ToolDef 分型 + buildTool 默认值 + MCP 适配器 + assembleToolPool 组装 + toolToAPISchema 两阶段序列化"
user-invocable: true
argument-hint: "<目标项目路径或模块名>"
---

# 工具契约：多层形成，不是单一接口

> 参考实现：`src/Tool.ts`（类型定义）、`src/tools.ts`（组装）、`src/services/mcp/client.ts`（MCP 适配）、`src/utils/api.ts`（API schema 生成）、`src/services/tools/toolExecution.ts`（执行管道）

## 源码事实

### 1. Tool 和 ToolDef 是两个类型，不是一个

```
Tool（完整类型，50+ 字段）
  ↕ buildTool() 填充默认值
ToolDef（作者写的，省略 7 个可默认的方法）
```

`buildTool()` 做的事（`src/Tool.ts:783`）：

```typescript
const TOOL_DEFAULTS = {
  isEnabled: () => true,
  isConcurrencySafe: () => false,  // fail-closed
  isReadOnly: () => false,         // fail-closed
  isDestructive: () => false,
  checkPermissions: async (input) => ({ behavior: 'allow', updatedInput: input }),
  toAutoClassifierInput: () => '',
  userFacingName: () => '',
}

function buildTool(def: ToolDef): Tool {
  return { ...TOOL_DEFAULTS, userFacingName: () => def.name, ...def }
}
```

**设计含义**：工具作者只写 ToolDef（核心逻辑），安全默认值由框架提供。忘了声明 `isConcurrencySafe` → 系统按最保守方式运行（串行 + 需要权限）。

### 2. inputJSONSchema 是真实字段，不是从 Zod 计算的

```
内置工具：inputSchema（Zod）→ toolToAPISchema() 用 zodToJsonSchema() 转换
MCP 工具：inputJSONSchema（原始 JSON Schema）→ toolToAPISchema() 直接使用

// src/utils/api.ts:169-178
input_schema = ('inputJSONSchema' in tool && tool.inputJSONSchema)
  ? tool.inputJSONSchema        // MCP：直接用
  : zodToJsonSchema(tool.inputSchema)  // 内置：从 Zod 转换
```

**设计含义**：两种 schema 来源共存。MCP 工具的 schema 来自远程服务器，不需要也不应该经过 Zod 转换。

### 3. 四条工具组装路径，不是一个注册表

| 函数 | 位置 | 作用 | 谁调用 |
|------|------|------|--------|
| `getAllBaseTools()` | `src/tools.ts:193` | 静态清单，60+ 工具，含 feature flag 过滤 | 内部 |
| `getTools(permCtx)` | `src/tools.ts:271` | 内置工具过滤（deny 规则 + REPL 模式 + isEnabled） | 内部 |
| `assembleToolPool(permCtx, mcpTools)` | `src/tools.ts:345` | **真正发给模型的工具池**：内置 + MCP 去重 + 按名排序 | queryModel |
| `getMergedTools(permCtx, mcpTools)` | `src/tools.ts:383` | 简单拼接（无去重无排序），仅用于 token 阈值计算 | ToolSearch 判断 |

**`assembleToolPool` 是唯一到达模型的路径。** 它做两件关键事：
- `uniqBy(name)` 同名内置优先于 MCP（防覆盖）
- 两个分区各自按名排序（prompt cache 稳定性）

### 4. MCP 适配器不是"展开默认值"——是构建一个完全不同的工具

```typescript
// src/services/mcp/client.ts:1766-1813
return {
  ...MCPTool,                              // 模板默认值
  name: `mcp__${serverName}__${toolName}`,
  mcpInfo: { serverName, toolName },
  inputJSONSchema: tool.inputSchema,       // 服务器的 JSON Schema，不是 Zod

  // 以下全部映射到 MCP annotations，不是本地逻辑
  isConcurrencySafe: () => tool.annotations?.readOnlyHint ?? false,
  isReadOnly: () => tool.annotations?.readOnlyHint ?? false,
  isDestructive: () => tool.annotations?.destructiveHint ?? false,
  checkPermissions: () => ({ behavior: 'passthrough' }),  // 不做判断，交给规则层
  call: (args) => callMCPToolWithUrlElicitationRetry(...), // 远程 RPC
}
```

**MCP 工具与内置工具的本质差异**：
- Schema：JSON Schema from server vs Zod from code
- 执行：远程 RPC vs 本地函数调用
- 权限：passthrough（我不发表意见）vs 工具自行判断
- 安全属性：从 server annotations 读 vs 工具代码里写

### 5. 延迟加载是 MCP 的默认行为，不是可选优化

```typescript
// src/tools/ToolSearchTool/prompt.ts:62-108
function isDeferredTool(tool): boolean {
  if (tool.alwaysLoad) return false       // 唯一的 opt-out
  if (tool.isMcp) return true             // 所有 MCP 工具默认延迟
  // ... 其他豁免（Agent, Brief, SendUserFile）
  return tool.shouldDefer === true        // 内置工具可选延迟
}
```

**设计含义**：MCP 工具不问你要不要延迟——它们全部延迟，除非服务器通过 `_meta['anthropic/alwaysLoad']` 显式 opt-out。

### 6. defer_loading / strict / cache_control 不在 Tool 类型上

```typescript
// src/utils/api.ts:215-230 — toolToAPISchema()
// 这些字段由 schema 生成函数在请求时添加，不是 Tool 的属性
{
  ...base,  // name, description, input_schema（会话级缓存）
  ...(options.deferLoading && { defer_loading: true }),    // ToolSearch 决定
  ...(options.cacheControl && { cache_control: ... }),     // prompt cache 策略
  // strict, eager_input_streaming 也是这里加的
}
```

### 7. 工具执行是 5 层管道，不是"call() 完事"

```
src/services/tools/toolExecution.ts — runToolUse() generator

Layer 1: 工具解析 → findToolByName + alias fallback
Layer 2: 权限检查 → PreToolUse hooks → validateInput → canUseTool → checkPermissions
Layer 3: 工具调用 → tool.call() + 错误捕获
Layer 4: Hook 执行 → PostToolUse / PostToolUseFailure hooks → contextModifier → newMessages
Layer 5: 遥测 → classifyToolError + logEvent + OTel span
```

**ToolResult** 携带的不只是 data：
```typescript
{ data, newMessages[], contextModifier, mcpMeta: { _meta, structuredContent } }
```

### 8. searchHint 是真实字段

```typescript
// src/Tool.ts — 3-10 词的策展短语，用于 ToolSearch 关键词匹配评分
searchHint?: string  // 例："notebook jupyter cell"
```

Skill 原版完全没提到这个字段。

---

## 可迁移设计

### buildTool() fail-closed 模式

你的项目应该做的：

```python
# 安全默认值由框架提供，工具作者只声明自己真正知道的
DEFAULTS = {
    "is_concurrency_safe": lambda _: False,  # 假设不安全
    "is_read_only": lambda _: False,         # 假设有写入
    "check_permissions": lambda _, __: "allow",
}

def build_tool(definition: dict) -> Tool:
    return {**DEFAULTS, **definition}  # 工具声明覆盖默认值
```

### 内置 vs 外部的分轨 schema

```python
# 内置工具：用 Pydantic/dataclass 定义 schema（编译期可验证）
# 外部工具：直接接收 JSON Schema dict（运行时动态获取）
class Tool:
    input_schema: BaseModel | None = None       # 内置
    input_json_schema: dict | None = None        # 外部（优先使用）
```

### 组装时排序

```python
# 工具列表必须按名字排序，否则 prompt cache key 不稳定
def assemble_tool_pool(builtin, external):
    combined = {t.name: t for t in builtin}  # 内置优先
    for t in external:
        combined.setdefault(t.name, t)       # 外部不覆盖同名内置
    return sorted(combined.values(), key=lambda t: t.name)
```

---

## 不要照抄的实现细节

- `Tool.ts` 的 50+ 字段中大部分是 UI 渲染方法（`renderToolUseMessage` 等）——你的项目不需要
- `searchHint` 只在 ToolSearch 生态内有意义，除非你也做延迟加载否则不需要
- `mcpMeta` 的 `structuredContent` 是 MCP 协议特定的，不是通用工具契约
- `strict` 模式是 API 侧 feature flag 控制的，不是工具自身属性

---

## 反模式

- 不要把 `defer_loading` 当成 Tool 的属性——它是 API 请求时按策略添加的
- 不要给 MCP 工具写 Zod schema——直接用服务器返回的 JSON Schema
- 不要跳过 `assembleToolPool` 的去重排序——cache miss 的成本远大于排序开销
- 不要把所有字段都设为必填——`ToolDef` 省略的 7 个方法有安全默认值
