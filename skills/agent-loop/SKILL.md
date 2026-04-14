---
name: agent-loop
description: "指导如何设计 Agent 循环状态机：while(true) + 10 种终态 + 7 种恢复续跑 + transition 追踪 + token budget 自动续跑"
user-invocable: true
argument-hint: "<目标项目路径或模块名>"
---

# Agent 循环状态机 (Agent Loop)

## 1. Problem — 不是"调 API + 执行工具"那么简单

Agent 主循环看起来是 `while(true) { call_llm(); run_tools(); }`，但生产环境中大量复杂度藏在循环边界：

- 模型输出被截断（max_output_tokens），需要自动续跑而不是直接返回残缺结果
- 上下文超过窗口（prompt_too_long），需要按成本递增尝试恢复
- 用户中途取消、Hook 阻止继续、工具执行出错——每种情况的退出语义不同
- 恢复路径可能无限重试（compact 失败 → 重试 → 又失败 → 螺旋），需要防护

通用问题是：**如何设计一个循环，能精确追踪每轮进入原因、区分 10+ 种退出条件、支持多种恢复续跑路径、且每条恢复路径都有防螺旋保护。**

---

## 2. In Claude Code — 源码事实（精简版）

> `源码事实` — 以下回钉到 `query.ts` 具体行号。

### 状态机结构（`query.ts:307-1728`）

整个主循环是一个 `while(true)`，通过 `State` 对象在迭代间传递状态：

```typescript
// query.ts:307
while (true) {
  const { messages, toolUseContext, autoCompactTracking,
          maxOutputTokensRecoveryCount, hasAttemptedReactiveCompact,
          maxOutputTokensOverride, turnCount, transition } = state

  // 1. 组装上下文 + 调用 API（流式）
  // 2. 处理流式返回（工具调用 / 文本 / 错误）
  // 3. 判断退出 or 恢复 or 继续下一轮
  // 4. 构造 next State，continue
}
```

### 10 种终态（return 路径）

| 终态 | 触发条件 | 行号 |
|------|---------|------|
| `completed` | 模型返回文本无工具调用（正常结束） | :1264, :1357 |
| `max_turns` | `nextTurnCount > maxTurns` | :1711 |
| `aborted_streaming` | 用户取消（abort signal） | :1051 |
| `aborted_tools` | 工具执行中用户取消 | :1515 |
| `prompt_too_long` | 上下文超限且恢复失败 | :1175, :1182 |
| `image_error` | 图片/媒体过大且恢复失败 | :977, :1175 |
| `model_error` | API 返回不可恢复错误 | :996 |
| `blocking_limit` | 触发速率限制 | :646 |
| `stop_hook_prevented` | Stop Hook 阻止继续 | :1279 |
| `hook_stopped` | 工具执行 Hook 终止循环 | :1520 |

### 7 种恢复续跑（continue 路径）

| 恢复路径 | transition.reason | 防螺旋机制 | 行号 |
|---------|------------------|-----------|------|
| 正常下一轮 | `next_turn` | `maxTurns` 上限 | :1725 |
| 上下文折叠排水 | `collapse_drain_retry` | 检查上一次 transition 不是自己 | :1110 |
| 反应式压缩重试 | `reactive_compact_retry` | `hasAttemptedReactiveCompact` 布尔标志 | :1162 |
| 输出 token 升级 | `max_output_tokens_escalate` | `maxOutputTokensOverride === undefined` 一次性 | :1217 |
| 输出截断多轮恢复 | `max_output_tokens_recovery` | `maxOutputTokensRecoveryCount < LIMIT` 计数器 | :1247 |
| Stop Hook 阻塞重试 | `stop_hook_blocking` | 保留 `hasAttemptedReactiveCompact` 防嵌套螺旋 | :1302 |
| Token Budget 续跑 | `token_budget_continuation` | `checkTokenBudget` 含 diminishingReturns 检测 | :1338 |

### Withhold-then-Recover 模式（核心设计）

流式过程中遇到可恢复错误（413、输出截断）时，**不立即 yield 给调用方**，而是暂存（withhold）错误消息。流结束后按成本递增尝试恢复：

```
发现 413 → withhold 错误消息
  → 尝试 collapse drain（零成本）
  → 尝试 reactive compact（一次 API）
  → 都失败 → 才 yield 错误并 return
```

这保证了调用方只看到最终结果，不会看到中间的恢复尝试。

### 流式工具执行（`query.ts:1366-1408`）

API 流式返回工具调用后，工具在流式过程中已经开始执行（`streamingToolExecutor`）。流结束时调用 `getRemainingResults()` 收集剩余结果。这不是先等流完再执行工具——是边流边执行。

---

## 3. Transferable Pattern — 状态机 + Transition Tracking + 分级恢复

> `抽象模式` — 框架无关的可迁移设计。

### 核心模式：带 transition 追踪的状态机循环

```
State = {
  messages, turn_count,
  transition: { reason, ...metadata },  // 本轮为什么进入
  recovery_flags: { ... }               // 各恢复路径的一次性标志
}

while true:
  response = call_llm(state.messages)

  if response.has_tool_calls:
    results = execute_tools(response.tool_calls)
    state = State(
      messages = [...state.messages, response, results],
      transition = { reason: "next_turn" },
      turn_count = state.turn_count + 1
    )
    continue

  exit_or_recover = evaluate_exit_conditions(response, state)

  if exit_or_recover.is_exit:
    return { messages: state.messages, exit_reason, turn_count }

  if exit_or_recover.is_recovery:
    state = apply_recovery(state, exit_or_recover)
    continue  // 回到循环顶部重试
```

### 关键设计原则

1. **Transition Reason 是状态的一部分**。每次 `continue` 都记录原因。恢复路径检查"上一次 transition 是不是我自己"来防螺旋——如果是，跳过该恢复路径，交给下一级或退出。

2. **每条恢复路径有独立的防螺旋机制**。布尔标志（一次性尝试）或计数器（有限次重试）。绝不用"成功就重置所有标志"——那会在 A→B→A 的路径中造成无限循环。

3. **恢复按成本递增排列**。零成本操作（截断、排水）优先，一次 API 调用（压缩）次之，多轮恢复（续跑）最后。任何一级成功就短路。

4. **Withhold 模式隔离调用方**。可恢复错误不暴露给调用方，直到确认无法恢复。这让 Agent 的对外接口保持简洁：`run() → { messages, exit_reason }`。

5. **恢复失败时不 fall through 到无关逻辑**。如 prompt_too_long 恢复失败后，不执行 stop hooks——模型没产生有效响应，hook 评估无意义且会造成死循环。

### 关键 Tradeoff

| 选择 | 好处 | 代价 |
|------|------|------|
| while(true) + State 对象 | 每个 continue 点显式构造完整状态 | 状态字段多时构造冗长 |
| transition.reason 追踪 | 防螺旋判断简单精确 | 每个恢复路径需要唯一 reason |
| Withhold 错误 | 调用方不感知恢复过程 | 流式 yield 延迟（需暂存） |
| 独立防螺旋标志 | 各路径解耦，互不影响 | 状态字段膨胀 |

---

## 4. Minimal Portable Version — Python async 最小实现

> `最小版` — 接口：`loop.run(config) -> LoopResult`

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

class ExitReason(Enum):
    COMPLETED = "completed"
    MAX_TURNS = "max_turns"
    ABORTED = "aborted"
    PROMPT_TOO_LONG = "prompt_too_long"
    MODEL_ERROR = "model_error"
    OUTPUT_TRUNCATED = "output_truncated"

@dataclass
class Transition:
    reason: str
    attempt: int = 0

@dataclass
class LoopState:
    messages: list
    turn_count: int = 0
    transition: Transition = field(default_factory=lambda: Transition("init"))
    has_attempted_compact: bool = False
    output_recovery_count: int = 0
    max_output_override: int | None = None

@dataclass
class LoopResult:
    messages: list
    exit_reason: ExitReason
    turn_count: int

MAX_OUTPUT_RECOVERY = 3

async def run(config: dict, llm_call, tool_runner) -> LoopResult:
    state = LoopState(messages=config["messages"])
    max_turns = config.get("max_turns", 100)

    while True:
        if state.turn_count >= max_turns:
            return LoopResult(state.messages, ExitReason.MAX_TURNS, state.turn_count)

        response = await llm_call(
            state.messages,
            max_tokens=state.max_output_override or config.get("max_tokens", 4096),
        )

        if response.error == "prompt_too_long":
            if not state.has_attempted_compact and config.get("compact_fn"):
                compacted = await config["compact_fn"](state.messages)
                if compacted:
                    state.messages = compacted
                    state.has_attempted_compact = True
                    state.transition = Transition("reactive_compact_retry")
                    continue
            return LoopResult(state.messages, ExitReason.PROMPT_TOO_LONG, state.turn_count)

        if response.error:
            return LoopResult(state.messages, ExitReason.MODEL_ERROR, state.turn_count)

        if response.output_truncated:
            if state.max_output_override is None and config.get("escalate_tokens"):
                state.max_output_override = config["escalate_tokens"]
                state.transition = Transition("output_escalate")
                continue
            if state.output_recovery_count < MAX_OUTPUT_RECOVERY:
                state.messages = [*state.messages, response.message,
                    {"role": "user", "content": "Output truncated. Resume directly."}]
                state.output_recovery_count += 1
                state.transition = Transition("output_recovery", state.output_recovery_count)
                continue
            return LoopResult(state.messages, ExitReason.OUTPUT_TRUNCATED, state.turn_count)

        if not response.tool_calls:
            state.messages.append(response.message)
            return LoopResult(state.messages, ExitReason.COMPLETED, state.turn_count)

        # Execute tools and continue
        tool_results = await tool_runner(response.tool_calls)
        state.messages = [*state.messages, response.message, *tool_results]
        state.turn_count += 1
        state.max_output_override = None
        state.output_recovery_count = 0
        state.has_attempted_compact = False
        state.transition = Transition("next_turn")
```

---

## 5. Do Not Cargo-Cult

> `不要照抄` — CC 的具体实现选择，不适合直接搬。

1. **不要因为 CC 有 7 种恢复路径就全部实现**。CC 的 collapse_drain、stop_hook_blocking、token_budget_continuation 是为特定产品需求（IDE 集成、企业 Hook、长任务预算）服务的。大多数 Agent 只需要 3 种：正常续轮、输出截断恢复、上下文压缩恢复。

2. **不要因为 CC 用 generator（yield）就必须用 generator**。CC 用 `async function*` 是为了流式 yield 中间消息给 UI。如果你的 Agent 不需要流式中间状态，普通 async 函数更简单。Generator 引入了"谁消费 yield 值"的复杂度。

3. **不要因为 CC 的 Withhold 模式就暂存所有错误**。Withhold 在 CC 中是因为流式场景下错误和正常内容混在同一个流中。如果你的 LLM 调用是非流式的，错误就是返回值，不需要 withhold。

4. **不要因为 CC 在恢复时保留 `hasAttemptedReactiveCompact` 就照搬跨恢复路径的标志传播逻辑**。CC 这样做是因为发现 stop_hook_blocking → reactive_compact → stop_hook_blocking 的死循环（数千次 API 调用）。如果你没有 stop hooks，这个问题不存在。

5. **不要因为 CC 每次 continue 都构造完整 State 对象就照搬**。CC 这样做是为了避免部分更新导致的状态不一致。如果你的状态字段少于 5 个，直接 mutate 一个对象更清晰。

---

## 6. Adaptation Matrix

> `迁移建议` — 不同框架/场景的裁剪方案。

| 项目类型 | 建议保留 | 建议简化或删掉 | 注意事项 |
|----------|---------|---------------|---------|
| **单轮问答 API** | 不需要循环 | 全部 | 单次调用，无状态 |
| **CLI Agent** | 基础循环 + 输出截断恢复 | Withhold、stop hooks、budget | 对话不长，简单方案足够 |
| **IDE Agent（类 CC）** | 完整状态机 + 全部恢复路径 | 可简化 transition 追踪为日志 | 最接近 CC 原始设计 |
| **后台批处理 Agent** | 循环 + max_turns + 压缩恢复 | 流式、Withhold、Hook | 无 UI，不需要中间状态 |
| **多 Agent 编排** | 每个子 Agent 独立循环 | 子 Agent 不需要 token budget | 父循环管理子循环生命周期 |

### Zero Magic LangGraph 适配案例

LangGraph 的 StateGraph 已经是状态机，适配重点在于把 transition tracking 映射到 graph state：

```python
# LangGraph adaptation sketch (not complete code)
class AgentState(TypedDict):
    messages: list
    transition_reason: str          # maps to transition.reason
    output_recovery_count: int      # anti-spiral counter
    has_attempted_compact: bool     # one-shot boolean flag

def should_continue(state: AgentState) -> str:
    """LangGraph conditional edge: maps CC exit/recovery decisions"""
    last = state["messages"][-1]
    if last.get("error") == "prompt_too_long":
        if not state["has_attempted_compact"]:
            return "compact_and_retry"      # -> compact node
        return "exit_prompt_too_long"       # -> END
    if last.get("output_truncated"):
        if state["output_recovery_count"] < 3:
            return "output_recovery"         # -> recovery node
        return "exit_truncated"             # -> END
    if last.get("tool_calls"):
        return "execute_tools"              # -> tools node
    return "exit_completed"                 # -> END

# Key: transition_reason is written to state, conditional edges read state
# Anti-spiral flags and counters are part of state, LangGraph auto-persists
```

---

## 7. Implementation Steps

1. **实现基础循环** — `while True: call_llm -> 有工具则执行 -> 无工具则返回`。先跑通最简单的路径。

2. **添加 max_turns 上限** — 防止无限循环。这是最基本的安全网。

3. **添加 abort 支持** — 用户取消信号。检查 abort flag 的位置：API 调用前、工具执行后。

4. **添加输出截断恢复** — 检测 `stop_reason == "max_tokens"`，注入 meta 消息让模型续写。加计数器上限。

5. **添加 transition tracking** — 在 State 中加 `transition.reason` 字段。每次 continue 时记录原因。

6. **添加上下文压缩恢复** — 检测 prompt_too_long，调用压缩函数，加一次性布尔标志。

7. **添加 Withhold 模式**（可选）— 仅流式场景需要。暂存可恢复错误，恢复成功则调用方不感知。

8. **验证防螺旋** — 模拟每条恢复路径连续触发的场景。确认：(a) 每条路径最终会退出循环，(b) 恢复路径 A 不会无限触发恢复路径 B。

---

## 8. Source Anchors

> CC 源码锚点，用于追溯和深入阅读。

| 关注点 | 文件 | 关键符号 | 行号参考 |
|--------|------|---------|---------|
| while(true) 主循环 | `query.ts` | `while (true)` + `State` 类型 | :307 |
| State 解构 | `query.ts` | `messages, toolUseContext, autoCompactTracking, ...` | :308-321 |
| 10 种终态 return | `query.ts` | `return { reason: ... }` | :646-1711 |
| transition.reason 赋值 | `query.ts` | `transition: { reason: '...' }` | :1110-1725 |
| Withhold 413 判断 | `query.ts` | `isWithheldMaxOutputTokens`, `isPromptTooLongMessage` | :1070, :1188 |
| Collapse drain 恢复 | `query.ts` | `contextCollapse.recoverFromOverflow()` | :1094 |
| Reactive compact 恢复 | `query.ts` | `reactiveCompact.tryReactiveCompact()` | :1120 |
| 输出 token 升级 | `query.ts` | `ESCALATED_MAX_TOKENS`, `maxOutputTokensOverride` | :1206-1221 |
| 输出截断多轮恢复 | `query.ts` | `MAX_OUTPUT_TOKENS_RECOVERY_LIMIT`, recovery message | :1223-1251 |
| Stop Hook 阻塞恢复 | `query.ts` | `handleStopHooks()`, `stopHookResult.blockingErrors` | :1267-1306 |
| Token Budget 续跑 | `query.ts` | `checkTokenBudget()`, `budgetTracker` | :1308-1355 |
| 流式工具执行 | `query.ts` | `streamingToolExecutor.getRemainingResults()` | :1380-1382 |
| max_turns 检查 | `query.ts` | `maxTurns && nextTurnCount > maxTurns` | :1705 |
| 正常下一轮 | `query.ts` | `transition: { reason: 'next_turn' }` | :1725 |
| 防螺旋：compact 一次性 | `query.ts` | `hasAttemptedReactiveCompact: true` | :1157 |
| 防螺旋：drain 不重复 | `query.ts` | `state.transition?.reason !== 'collapse_drain_retry'` | :1092 |
