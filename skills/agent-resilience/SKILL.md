---
name: agent-resilience
description: "Agent 运行时恢复：分散在 query.ts 中的独立恢复路径 + services/compact/ 中的真实压缩模块 + feature-gated 的实验性恢复机制"
user-invocable: true
argument-hint: "<目标项目路径或模块名>"
---

# Agent 运行时恢复

> 参考实现：`src/query.ts`（恢复控制流）、`src/services/compact/`（压缩模块）、`src/services/api/withRetry.ts`（模型回退）

## 源码事实

### 1. 没有统一的"恢复链"——是分散的独立路径

源码中不存在 `recovery()` 函数或 `RecoveryChain` 类。恢复逻辑是 `query.ts` 中的 **散落的 if/else 块**，每种错误类型走自己的路径：

```
query.ts 中的恢复分布：

流式 try/catch（lines 894-943）：
  └─ FallbackTriggeredError → 模型回退（完全独立的路径）

流式 withhold 检查（lines 799-825）：
  └─ 4 个 nullable 布尔检查，任一为 true → 不 yield 给用户

后流恢复块（lines 1063-1256）：
  ├─ prompt_too_long withheld → collapse drain (0-1 次) → reactive compact (0-1 次)
  └─ max_output_tokens withheld → escalate 8K→64K (一次) → 多轮恢复 (≤3 次)
```

### 2. Withhold 不是函数——是内联布尔检查

```typescript
// src/query.ts:799-825 — 没有 withhold() 函数
let withheld = false
if (contextCollapse?.isWithheldPromptTooLong(msg)) withheld = true   // nullable
if (reactiveCompact?.isWithheldPromptTooLong(msg)) withheld = true   // nullable
if (reactiveCompact?.isWithheldMediaSizeError(msg)) withheld = true  // nullable
if (isWithheldMaxOutputTokens(msg)) withheld = true                  // 本地函数

if (!withheld) yield message  // 不扣住才输出
```

**`isWithheldMaxOutputTokens` 是唯一的函数化检查**（`query.ts:175-179`），其他三个是 **optional chaining on nullable modules**——如果 feature gate 关了，这些模块是 null，检查静默跳过。

### 3. 模型回退是完全独立的路径，不是"恢复链第 1 级"

```
模型回退的真实机制：

src/services/api/withRetry.ts:
  → 重试逻辑检测到可通过换模型恢复的错误
  → throw FallbackTriggeredError（自定义异常类）

src/query.ts:894-943（流式 try/catch 内）：
  → catch FallbackTriggeredError
  → 清空 assistantMessages、toolResults、toolUseBlocks
  → 重建 StreamingToolExecutor
  → 剥离 thinking 签名块（ANT only，模型不兼容）
  → currentModel = fallbackModel
  → attemptWithFallback = true → 重新进入流式循环
```

**这与 prompt-too-long 和 max-output-tokens 的恢复路径零交叉。** 模型回退在流式 try/catch 里处理，其他恢复在后流块里处理。

### 4. 真实的压缩模块边界

`src/services/compact/` 目录中的**真实模块**：

| 文件 | 稳定性 | 作用 |
|------|--------|------|
| `autoCompact.ts` (13K) | **稳定模块** | 主动压缩：阈值判断 + 触发压缩 |
| `compact.ts` (60K) | **稳定模块** | 完整对话摘要 + `buildPostCompactMessages()` |
| `sessionMemoryCompact.ts` (21K) | **稳定模块** | 替代路径：通过 session memory store 压缩 |
| `microCompact.ts` (20K) | **稳定模块** | 增量压缩：旧工具结果替换为占位符 |
| `postCompactCleanup.ts` (3.7K) | **稳定模块** | 压缩后状态清理 |

**不在此目录中的**（feature-gated lazy require in query.ts）：

| 模块 | 来源 | 状态 |
|------|------|------|
| `reactiveCompact` | `feature('REACTIVE_COMPACT') ? require(...)` | **feature-gated**，非普遍可用 |
| `contextCollapse` | `feature('CONTEXT_COLLAPSE') ? require(...)` | **feature-gated**，非普遍可用 |

### 5. 恢复状态在 State struct 中跨迭代传递

```typescript
// src/query.ts:204-215 — State 中的恢复相关字段
type State = {
  hasAttemptedReactiveCompact: boolean      // 一次性标志（防重入）
  maxOutputTokensRecoveryCount: number      // 计数器（≤3）
  maxOutputTokensOverride: number | undefined  // 升级后的上限（64K）
  autoCompactTracking: AutoCompactTrackingState | undefined
  transition: Continue | undefined          // 为什么进入本轮
}
```

**这些是唯一的跨迭代耦合。** 不是协议或链——是防止重复尝试的标志和计数器。

### 6. 压缩的真实执行顺序（不是"5 级"）

query.ts 中每轮 API 调用前的压缩顺序（`lines 379-543`）：

```
1. applyToolResultBudget()        — 工具结果大小裁剪
2. snipModule?.snipCompactIfNeeded()  — 历史裁剪（feature: HISTORY_SNIP）
3. microcompact()                 — 旧工具结果替换为占位符（feature: CACHED_MICROCOMPACT）
4. contextCollapse?.applyCollapsesIfNeeded()  — 上下文折叠（feature: CONTEXT_COLLAPSE）
5. autoCompactIfNeeded()          — 完整摘要（稳定模块，但有断路器）
```

**不是"5 级渐进式"——是按固定顺序执行，每步独立判断是否需要。** 步骤 2、3、4 是 feature-gated，在外部构建中可能不存在。

---

## 可迁移设计

### 散落恢复路径 + 防重入标志

这是 CC 实际用的模式——不是框架化的恢复链，而是在主循环中用标志变量防止每种恢复重复执行：

```python
class AgentLoopState:
    has_attempted_compact: bool = False
    output_recovery_count: int = 0
    output_limit_override: int | None = None

async def handle_recovery(state, error, messages):
    """每种错误类型走独立路径，标志变量防重入"""
    
    if isinstance(error, ContextTooLongError):
        if not state.has_attempted_compact:
            state.has_attempted_compact = True
            messages = await compact(messages)
            return 'retry'
        return 'surface'  # 已试过，暴露错误
    
    if isinstance(error, MaxOutputTokensError):
        if state.output_limit_override is None:
            state.output_limit_override = 64000  # 一次性升级
            return 'retry'
        if state.output_recovery_count < 3:
            state.output_recovery_count += 1
            messages.append(nudge_message())  # 注入续跑提示
            return 'retry'
        return 'surface'  # 耗尽重试
    
    return 'surface'  # 未知错误直接暴露
```

### Withhold 模式（延迟错误暴露）

```python
# 在流式输出循环中
withheld = False
for msg in stream:
    if is_recoverable_error(msg):
        withheld_errors.append(msg)
        withheld = True
        continue  # 不输出给用户
    yield msg

# 流式结束后
if withheld:
    recovery_result = await handle_recovery(state, withheld_errors[-1], messages)
    if recovery_result == 'retry':
        continue  # 重新进入主循环
    else:
        yield withheld_errors[-1]  # 恢复失败，暴露
```

### 压缩模块应该是真实模块，恢复逻辑可以是内联的

CC 的压缩是真实模块（`compact.ts`、`autoCompact.ts`、`microCompact.ts`），但恢复逻辑是内联在主循环中的 if/else。你的项目可以：
- 压缩：抽成独立模块（有明确的输入/输出）
- 恢复：保持内联（因为每种错误的上下文不同，强行统一反而增加复杂度）

---

## 不要照抄的实现细节

- CC 的 `reactiveCompact` 和 `contextCollapse` 是 feature-gated 实验性模块，不是稳定 API
- `FallbackTriggeredError` 是 CC 特定的异常类，你的项目用普通异常 + 类型判断就够
- `snipModule` 的历史裁剪是 CC 特有的（ANT-only），你的项目用 autoCompact 就够
- `buildPostCompactMessages()` 的重组顺序（boundary → summary → kept → attachments → hooks）是 CC 对话协议特定的

---

## 反模式

- 不要把分散的恢复路径包装成统一的"恢复链"——CC 实际不是这样做的，强行统一会掩盖每种错误的特殊处理逻辑
- 不要假设所有压缩步骤都存在——feature-gated 步骤在不同构建中可能不可用
- 不要无限重试——CC 的每种恢复都有硬上限（compact 1 次、output 升级 1 次、多轮 3 次）
- 不要在压缩后忘了清理——`postCompactCleanup.ts` 重置模块级状态，子 Agent 不能污染主线程
