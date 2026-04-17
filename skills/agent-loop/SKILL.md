---
name: agent-loop
description: "指导如何设计 Agent 循环状态机：while(true) + 三类分支（exit/recovery/normal）+ CC 的 10 终态/7 恢复（最小 Agent 仅需 ★3+3）+ 预算分层（turn vs retry）+ 双路压缩（proactive/reactive）+ transcript 修复 + 防螺旋"
user-invocable: false
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

> ★ = 任何 Agent 都需要；其余是 CC 产品特性（IDE 集成 / 企业 Hook / Budget / 多媒体），可按需裁剪。

| ★ | 终态 | 触发条件 | 行号 |
|---|------|---------|------|
| ★ | `completed` | 模型返回文本无工具调用（正常结束） | :1264, :1357 |
| ★ | `max_turns` | `nextTurnCount > maxTurns` | :1711 |
| ★ | `model_error` | API 返回不可恢复错误（含退避耗尽后的瞬时错误） | :996 |
|   | `aborted_streaming` | 用户取消（abort signal） | :1051 |
|   | `aborted_tools` | 工具执行中用户取消 | :1515 |
| ★ | `prompt_too_long` | 上下文超限且恢复失败 | :1175, :1182 |
|   | `image_error` | 图片/媒体过大且恢复失败 | :977, :1175 |
|   | `blocking_limit` | 触发速率限制（服务端硬封） | :646 |
|   | `stop_hook_prevented` | Stop Hook 阻止继续 | :1279 |
|   | `hook_stopped` | 工具执行 Hook 终止循环 | :1520 |

### 7 种恢复续跑（continue 路径）

> ★ = 最小 Agent 必需；其余按产品需要裁剪。cc-python-claude 只保留了 3 条 ★ 项。

| ★ | 恢复路径 | transition.reason | 防螺旋机制 | 行号 |
|---|---------|------------------|-----------|------|
| ★ | 正常下一轮 | `next_turn` | `maxTurns` 上限 | :1725 |
|   | 上下文折叠排水 | `collapse_drain_retry` | 检查上一次 transition 不是自己 | :1110 |
| ★ | 反应式压缩重试 | `reactive_compact_retry` | `hasAttemptedReactiveCompact` 布尔标志 | :1162 |
| ★ | 输出 token 升级 | `max_output_tokens_escalate` | `maxOutputTokensOverride === undefined` 一次性 | :1217 |
| ★ | 输出截断多轮恢复 | `max_output_tokens_recovery` | `maxOutputTokensRecoveryCount < LIMIT` 计数器 | :1247 |
|   | Stop Hook 阻塞重试 | `stop_hook_blocking` | 保留 `hasAttemptedReactiveCompact` 防嵌套螺旋 | :1302 |
|   | Token Budget 续跑 | `token_budget_continuation` | `checkTokenBudget` 含 diminishingReturns 检测 | :1338 |
| ★ | **瞬时错误退避**（skill 补充） | `transient_retry` | 独立 `retry_count`（不消耗 turn 预算）+ 线性/指数退避 | cc-python `query_loop.py:249-254` |

> 最后一行 CC 源码里隐含在 API 调用 try/catch 层（不走 transition），cc-python 把它显式做进主循环——生产必备。

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

**并发控制（关键但容易踩坑）**：流式并行不是"所有工具一起跑"。每个工具自报 `isConcurrencySafe()`（cc-python 同名）：
- Read / Grep / Glob 并发安全，可并行
- Edit / Write / Bash 独占；**一旦启动，后续所有工具必须排队**——哪怕后续是 Read
- 独占标志由执行器维护，不是工具本身

这个策略避免了"Edit 改到一半时另一个 Read 读到不一致的文件"。代价是写类操作序列化。cc-python 对应实现：`streaming_executor.py:72-96`（排队/启动分流）、`:127-130`（进入执行前权限检查）。

---

## 3. Transferable Pattern — 状态机 + Transition Tracking + 分级恢复

> `抽象模式` — 框架无关的可迁移设计。

### 核心模式：带 transition 追踪的状态机循环（**三类分支**）

> 注意：分支不是二分（exit vs recovery），而是**三分**。工具调用（包括被权限拒绝或执行出错的）属于「正常续行」，不走 recovery、不消耗 retry 预算。

```
State = {
  messages, turn_count, retry_count,        // 预算分层：两个独立计数器
  transition: { reason, ...metadata },      // 本轮为什么进入
  recovery_flags: { ... }                   // 各恢复路径的一次性标志
}

while true:
  if state.turn_count >= max_turns:         # 预算守门
    return { exit_reason: "max_turns" }

  response = call_llm(state.messages)

  # ───── 分支 1：normal continuation（最常见）─────
  # 工具调用（包括被权限拒绝返回 is_error=True 的 ToolResult），
  # 都当普通下一轮处理，由模型决定如何继续
  if response.has_tool_calls:
    results = execute_tools(response.tool_calls)   # 含被拒 / 执行报错
    state = state.with_(
      messages = [...state.messages, response, ...results],
      turn_count += 1,
      transition = { reason: "next_turn" },
      # 成功的 next_turn 可重置部分 recovery_flags（但不是全部——见原则 2）
    )
    continue

  # ───── 分支 2：recovery（不消耗 turn_count）─────
  recovery = evaluate_recovery(response, state)   # 413/max_tokens/429/...
  if recovery:
    state = apply_recovery(state, recovery)
    # 注意：state.turn_count 不 +1；仅 transient 类 retry_count +1
    continue

  # ───── 分支 3：exit ─────
  return { messages: state.messages, exit_reason, turn_count, retry_count }
```

### 关键设计原则

1. **Transition Reason 是状态的一部分**。每次 `continue` 都记录原因。恢复路径检查"上一次 transition 是不是我自己"来防螺旋——如果是，跳过该恢复路径，交给下一级或退出。

2. **每条恢复路径有独立的防螺旋机制**。布尔标志（一次性尝试）或计数器（有限次重试）。绝不用"成功就重置所有标志"——那会在 A→B→A 的路径中造成无限循环。

3. **恢复按成本递增排列**。零成本操作（截断、排水）优先，一次 API 调用（压缩）次之，多轮恢复（续跑）最后。任何一级成功就短路。

4. **Error Deferred Emission 隔离调用方**（原名 Withhold）。可恢复错误不立即 yield 给调用方；Phase 3 判定可恢复就直接 `continue`（从不 yield），判定不可恢复才 yield 错误并 return。不需要真实的 `withheld_errors` 队列——条件分支就够。这让对外接口保持简洁：`run() → { messages, exit_reason }`。

5. **恢复失败时不 fall through 到无关逻辑**。如 prompt_too_long 恢复失败后，不执行 stop hooks——模型没产生有效响应，hook 评估无意义且会造成死循环。

6. **预算分层：轮次预算与重试预算独立计数**。`turn_count`（用户感知的有效步数）和 `retry_count`（瞬时错误重试）分别计数、分别有上限。可恢复路径（压缩、输出续写、限流重试）**不消耗用户的 turn 预算**。否则 Anthropic 偶发 429 十次就能把 `max_turns=50` 烧掉五分之一，用户什么有效输出都没看到。

7. **压缩的两条独立入口**：
   - **Proactive**：每轮开始前按 `estimate_messages_tokens()` 估算，达阈值（`context_window - buffer`，CC 用 ~7% buffer）**主动**压缩，省一次 400 往返
   - **Reactive**：API 返回 413 / prompt_too_long 后**被动**压缩，作为恢复路径
   - 两者共享同一个 `compact_fn`，但防螺旋机制**必须独立**：proactive 用连续失败计数器（防"压缩无效就退避"），reactive 用一次性布尔（防"压缩-重试-压缩"螺旋）

8. **嵌套 Agent 的封装层次**：子 Agent 的 query_loop 作为一个**工具调用**嵌入父 loop（不是父 loop 的一个 phase）。子循环的终态/恢复/压缩对父不可见，只通过最终 ToolResult 传回结果。父的 turn / retry / compact 状态与子完全独立。前台/后台/worktree 隔离三种模式决定父等待语义，与 loop 结构正交。

9. **压缩策略：摘要 + 保留最近 K 轮原文**。compact_fn 通常不全丢旧消息。K 太小（<3）破坏近因语义，K 太大（>6）省不下 token。cc-python 取 `POST_COMPACT_KEEP_TURNS=4`，CC 类似量级。这是参数而非架构决策，但要有显式上限不要留给 LLM 自己斟酌。

### 关键 Tradeoff

| 选择 | 好处 | 代价 |
|------|------|------|
| while(true) + State 对象 | 每个 continue 点显式构造完整状态 | 状态字段多时构造冗长 |
| transition.reason 追踪 | 防螺旋判断简单精确 | 每个恢复路径需要唯一 reason |
| Error Deferred Emission | 调用方不感知恢复过程 | 流式 yield 延迟（暂存文本直到恢复判定） |
| 独立防螺旋标志 | 各路径解耦，互不影响 | 状态字段膨胀 |
| **Mutable messages**（cc-python 选择）| 原地修改，引用稳定；多工具易共享访问；compact 用 `clear()+extend()` 保持引用 | 同一 messages 不能并发 loop；需警惕"误赋值"破坏引用 |
| **Immutable State**（CC 原版 / skill §4 选择）| 每 `continue` 显式重建，历史快照天然存在 | 长 messages 列表的浅拷贝开销；状态字段多时构造冗长 |

---

## 4. Minimal Portable Version — Python async 最小实现

> `最小版` — 接口：`run(messages, llm_call, *, tool_runner=None, max_turns=100, max_tokens=4096, escalate_tokens=65536, compact_fn=None) -> LoopResult`
>
> `messages` 和 `llm_call` 是位置参数（最小必需）；其余全部 keyword-only（可裁剪）。与 §7 测试骨架调用形式一致。

```python
import asyncio
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
    turn_count: int = 0              # 用户感知的有效轮次
    retry_count: int = 0             # 瞬时错误重试（独立预算）
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
MAX_RETRY = 5                        # 瞬时错误（429/529/5xx）重试上限

# 续写消息的措辞会影响模型续写质量。参考三个版本：
# - CC 原版（query.ts:1226）: "Output token limit hit. Resume directly — no apology,
#   no recap... Pick up mid-thought if that is where the cut happened. Break remaining
#   work into smaller pieces."  最详细，明确禁止模型浪费 token 在道歉/总结。
# - cc-python (query_loop.py:246): "Please continue from where you left off."  最温和。
# - 最简可用: "Output truncated. Resume directly."
# 三者都能工作，CC 原版抗退化最好（模型少写废话）。
CONTINUE_MSG = (
    "Output token limit hit. Resume directly — no apology, no recap. "
    "Pick up mid-thought if that's where the cut happened."
)

async def run(
    messages: list,
    llm_call,
    *,
    tool_runner=None,
    max_turns: int = 100,
    max_tokens: int = 4096,
    escalate_tokens: int | None = 65536,
    compact_fn=None,
) -> LoopResult:
    """Keyword-only 参数。保持 messages/llm_call 为位置参数是最小易用界面。"""
    state = LoopState(messages=list(messages))   # 浅拷贝，避免 mutate 调用方列表

    while True:
        if state.turn_count >= max_turns:
            return LoopResult(state.messages, ExitReason.MAX_TURNS, state.turn_count)

        response = await llm_call(
            state.messages,
            max_tokens=state.max_output_override or max_tokens,
        )

        # 瞬时错误退避（429/529/5xx）：生产必备。独立 retry_count，不消耗 turn 预算。
        if response.error_type in ("rate_limit", "overloaded", "transient"):
            if state.retry_count < MAX_RETRY:
                state.retry_count += 1
                await asyncio.sleep(min(2.0 * state.retry_count, 10.0))  # 线性退避，上限 10s
                state.transition = Transition("transient_retry", state.retry_count)
                continue
            return LoopResult(state.messages, ExitReason.MODEL_ERROR, state.turn_count)

        if response.error == "prompt_too_long":
            if not state.has_attempted_compact and compact_fn is not None:
                compacted = await compact_fn(state.messages)
                if compacted:
                    state.messages = compacted
                    state.has_attempted_compact = True
                    state.transition = Transition("reactive_compact_retry")
                    continue
            return LoopResult(state.messages, ExitReason.PROMPT_TOO_LONG, state.turn_count)

        if response.error:
            return LoopResult(state.messages, ExitReason.MODEL_ERROR, state.turn_count)

        if response.output_truncated:
            if state.max_output_override is None and escalate_tokens:
                # 第一次截断：一次性提高 max_tokens 到硬上限 64K（ESCALATED_MAX_TOKENS）。
                # CC 默认从 32K（src/utils/context.ts MAX_OUTPUT_TOKENS_DEFAULT）或
                # slot 预留时的 cap 8K（CAPPED_DEFAULT_MAX_TOKENS）跳到 64K；
                # cc-python 从 16K（query_loop.py:127 current_max_tokens=16384）跳到 64K。
                # 两者共同点：**一次性跳，不渐进**。
                state.max_output_override = escalate_tokens
                state.transition = Transition("output_escalate")
                continue
            if state.output_recovery_count < MAX_OUTPUT_RECOVERY:
                # 保留 response.message（含其 usage 统计，续写不能丢失之前的 token 消耗）
                state.messages = [*state.messages, response.message,
                    {"role": "user", "content": CONTINUE_MSG}]
                state.output_recovery_count += 1
                state.transition = Transition("output_recovery", state.output_recovery_count)
                continue
            return LoopResult(state.messages, ExitReason.OUTPUT_TRUNCATED, state.turn_count)

        # ─── 成功的一次有效模型轮次：不论是否触发工具，turn_count 都 +1 ───
        # 这是"用户感知的有效轮次"语义：只有可恢复错误（retry/recovery/compact）不算；
        # 模型成功返回（无论 completed 还是 tool_use）都算一次。
        state.turn_count += 1
        state.retry_count = 0             # 成功后重置瞬时错误计数

        if not response.tool_calls:
            state.messages.append(response.message)
            return LoopResult(state.messages, ExitReason.COMPLETED, state.turn_count)

        # Execute tools — fail-fast 守护：tool_runner 默认 None 是为了让"不会触发工具"
        # 的最小用例（比如只测 compact / retry 分支）不必提供 runner。一旦模型真的返回
        # tool_calls，就必须要求 runner；否则 `None(...)` 会神秘崩溃。
        if tool_runner is None:
            raise RuntimeError(
                "Model returned tool_calls but tool_runner was not provided. "
                "Pass tool_runner= when calling run() if llm_call may emit tools."
            )
        # （被权限拒绝的工具会返回 is_error=True 的 ToolResult，不会走到这里抛异常）
        tool_results = await tool_runner(response.tool_calls)
        state.messages = [*state.messages, response.message, *tool_results]
        state.max_output_override = None
        state.output_recovery_count = 0
        state.has_attempted_compact = False
        state.transition = Transition("next_turn")
```

> 注意：上述最小版省略了**流式处理、流式工具并发控制、transcript 修复、嵌套子 Agent**。§7 给出补全顺序。

---

## 5. Do Not Cargo-Cult

> `不要照抄` — CC 的具体实现选择，不适合直接搬。

1. **不要因为 CC 有 7 种恢复路径就全部实现**。CC 的 collapse_drain、stop_hook_blocking、token_budget_continuation 是为特定产品需求（IDE 集成、企业 Hook、长任务预算）服务的。大多数 Agent 只需要 3 种：正常续轮、输出截断恢复、上下文压缩恢复。

2. **不要因为 CC 用 generator（yield）就必须用 generator**。CC 用 `async function*` 是为了流式 yield 中间消息给 UI。如果你的 Agent 不需要流式中间状态，普通 async 函数更简单。Generator 引入了"谁消费 yield 值"的复杂度。

3. **不要因为 CC 的 Withhold 模式就暂存所有错误**。Withhold 在 CC 中是因为流式场景下错误和正常内容混在同一个流中。如果你的 LLM 调用是非流式的，错误就是返回值，不需要 withhold。

4. **不要因为 CC 在恢复时保留 `hasAttemptedReactiveCompact` 就照搬跨恢复路径的标志传播逻辑**。CC 这样做是因为发现 stop_hook_blocking → reactive_compact → stop_hook_blocking 的死循环（数千次 API 调用）。如果你没有 stop hooks，这个问题不存在。

5. **不要因为 CC 每次 continue 都构造完整 State 对象就照搬**。CC 这样做是为了避免部分更新导致的状态不一致。如果你的状态字段少于 5 个，直接 mutate 一个对象更清晰（cc-python 就这么干）。

6. **不要照抄 abort 实现**。CC TS 用 `AbortSignal`（协作式，观测点主动检查）；cc-python 用 `asyncio.Task.cancel()`（通过 CancelledError 异步抛出）；LangGraph 用 checkpoint 回滚。三者的资源清理（打开的文件、流式连接、子进程）写法不同：
   - TS：`if (signal.aborted) return { reason: 'aborted_tools' }` — 主动分支
   - asyncio：`try: ... except CancelledError: await cleanup(); raise` — 异常捕获
   - LangGraph：interrupt + checkpoint 机制，依赖框架的回滚
   迁移时把 abort 点位写具体（API 调用前、每个工具完成后、流式每帧），别指望一个"通用 abort"抽象。

7. **不要把 max_output_tokens escalate 写成渐进**。CC 和 cc-python **都是一次性跳到 64K**（`ESCALATED_MAX_TOKENS=65536` / `=64_000`），不是 2×→4×。起点不同：CC 从 32K（`MAX_OUTPUT_TOKENS_DEFAULT`）或 slot 预留时的 8K cap（`CAPPED_DEFAULT_MAX_TOKENS`，见 `src/utils/context.ts:14-24`）；cc-python 从 16K（`query_loop.py:127`）。理由：Claude 的 max_tokens 档位离散且 64K 是硬上限，中间值既不省钱也不解决截断。第一次截断直接升到最高档，之后再靠"续写"多轮恢复，更干净。

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

0. **（仅在支持 session 恢复时）实现 transcript 修复** — 进入 loop 前 `validate_transcript(messages)`，处理两种破损：
   - **末尾截断**：最后一条是含 tool_use 的 assistant 消息（进程在工具执行前崩溃）→ 追加合成 user 消息，内含 `ToolResultBlock(is_error=True, content="[Tool result missing due to internal error]")`
   - **中间孤立**：某条 assistant 的 tool_use 没有配对 tool_result → 在后续 user 消息**前**插入合成 result
   不修就连不上 API（Anthropic 会直接 400）。参考 cc-python `session/recovery.py:29-130`。

1. **实现基础循环** — `while True: call_llm -> 有工具则执行 -> 无工具则返回`。先跑通最简单的路径。

2. **添加 max_turns 上限** — 防止无限循环。这是最基本的安全网。

3. **添加瞬时错误退避**（生产必备）— `response.error_type in (rate_limit, overloaded)` 时独立 `retry_count`，线性/指数退避，不消耗 `max_turns` 预算。

4. **添加 abort 支持** — 用户取消信号。检查 abort flag 的位置：API 调用前、工具执行后、流式每帧。asyncio 下通过 CancelledError 传播，记得在 finally 里清理流式连接。

5. **添加输出截断恢复** — 分两步：第一次截断一次性 escalate max_tokens 到 64K（起点 CC 是 32K 或 8K cap，cc-python 是 16K），之后截断注入续写 user 消息多轮恢复。加计数器上限（CC/cc-python 都是 3）。

6. **添加 transition tracking** — 在 State 中加 `transition.reason` 字段。每次 continue 时记录原因。

7. **添加上下文压缩恢复** — **两个入口都要实现**：Phase 1 主动（按 token 估算）+ Phase 3 被动（413/prompt_too_long）。共享 compact_fn，防螺旋机制**独立**：proactive 用连续失败计数器，reactive 用一次性布尔。

8. **添加 Error Deferred Emission**（原名 Withhold，可选）— 仅流式场景需要。判定可恢复时 `continue` 直接重试（从不 yield 错误事件）；判定不可恢复才 yield 错误并 return。

9. **验证防螺旋** — 模拟每条恢复路径连续触发的场景。确认：(a) 每条路径最终会退出循环，(b) 恢复路径 A 不会无限触发恢复路径 B。参考测试骨架：

    ```python
    # 验证 reactive_compact 只尝试一次，压缩无效时退出而不循环压缩
    async def test_reactive_compact_single_attempt():
        call_model = MockModel(always_returns_error="prompt_too_long")
        compact_fn = MockCompact(always_same_length=True)  # 压缩无效
        result = await run(messages, call_model, compact_fn=compact_fn)
        assert result.exit_reason == ExitReason.PROMPT_TOO_LONG
        assert compact_fn.call_count == 1   # 只调用一次

    # 验证瞬时错误不消耗 turn 预算
    async def test_transient_retry_not_consumes_turns():
        # 前 3 次 rate_limit（都不 +turn_count），第 4 次 completed（+1）
        call_model = MockModel(fails_n_times=3, error_type="rate_limit")
        result = await run(messages, call_model, max_turns=2)
        assert result.exit_reason == ExitReason.COMPLETED
        assert result.turn_count == 1  # 没被 retry 吃掉

    # 验证 tool-use 路径不崩（带 tool_runner）
    async def test_tool_use_happy_path():
        # 第 1 轮返回 tool_use，第 2 轮返回 completed
        call_model = MockModel(turns=[
            {"tool_calls": [{"id": "t1", "name": "echo", "args": {"x": 1}}]},
            {"tool_calls": None, "message": {"role": "assistant", "content": "done"}},
        ])
        async def tool_runner(calls):
            return [{"tool_use_id": c["id"], "content": f"ok:{c['args']['x']}"} for c in calls]
        result = await run(messages, call_model, tool_runner=tool_runner, max_turns=5)
        assert result.exit_reason == ExitReason.COMPLETED
        assert result.turn_count == 2  # 两轮成功：tool_use + completed

    # 验证 tool_runner 缺失时 fail-fast（而不是 None 崩溃）
    async def test_missing_tool_runner_raises():
        call_model = MockModel(turns=[{"tool_calls": [{"id": "t1"}]}])
        import pytest
        with pytest.raises(RuntimeError, match="tool_runner was not provided"):
            await run(messages, call_model)  # 没传 tool_runner
    ```

---

## 8. Source Anchors

> 两份源码并列：CC 原版（TS）与 cc-python-claude 复现（Python）。读 skill 学思路，读 TS 看完整实现，读 Python 看简化版本如何取舍。

| 关注点 | CC 原版 (`src/query.ts`) | cc-python 复现 |
|--------|--------------------------|------------------|
| while(true) 主循环 | `:307` `while (true)` + `State` 类型 | `cc/core/query_loop.py:130` `while turn_count < max_turns` |
| State 解构 / 状态变量 | `:308-321` State 对象解构 | `query_loop.py:121-128` 局部变量（turn_count / retry_count / recovery 标志） |
| 10 种终态 return | `:646, :977, :996, :1051, :1175, :1264, :1279, :1515, :1520, :1711` | `query_loop.py:130, 203-262, 344-351`（合并为 4 类） |
| transition.reason 赋值 | `:1110-1725` 每次 `continue` 前构造 | cc-python 未显式追踪 transition（用 `last_error` + 局部布尔代替） |
| Error Deferred Emission | `:1070, :1188` `isWithheldMaxOutputTokens` / `isPromptTooLongMessage` | `query_loop.py:203-262` 判定可恢复就不 yield，等价效果 |
| Collapse drain 恢复 | `:1094` `contextCollapse.recoverFromOverflow()` | **未实现**（可省略） |
| **Proactive compact**（每轮开始前主动） | CC 通过 autoCompactTracking 判断 | `query_loop.py:140-164` `should_auto_compact()` + `compact_consecutive_failures` 计数器 |
| **Reactive compact**（API 拒绝后被动） | `:1120` `reactiveCompact.tryReactiveCompact()` | `query_loop.py:214-228` 一次性布尔 `has_attempted_reactive_compact` |
| 输出 token 升级（escalate） | `:1206-1221` `maxOutputTokensOverride = ESCALATED_MAX_TOKENS` (64K)；默认起点见 `src/utils/context.ts:14-25` (32K default / 8K capped / 64K upper) | `query_loop.py:91, 232-237` 从 16K (`current_max_tokens=16384`) 一次性跳到 64K (`ESCALATED_MAX_TOKENS=65536`) |
| 输出截断多轮恢复 | `:1223-1251` `MAX_OUTPUT_TOKENS_RECOVERY_LIMIT`, 续写 meta 消息 | `query_loop.py:90, 238-247` 同上限 3 次，续写消息用 `"Please continue from where you left off."` |
| 瞬时错误退避（429/529） | 在 callModel 层，非 loop-level | `query_loop.py:249-254` 线性退避 2s/4s/...(上限 10s)，独立 `retry_count`，上限 5 |
| Stop Hook 阻塞恢复 | `:1267-1306` `handleStopHooks()` | **未实现** |
| Token Budget 续跑 | `:1308-1355` `checkTokenBudget()` | **未实现** |
| 流式工具执行 | `:1380-1382` `streamingToolExecutor.getRemainingResults()` | `cc/tools/streaming_executor.py` 整模块 |
| 流式并发控制（读/写区分） | TS 工具自报 `isConcurrencySafe` | `streaming_executor.py:72-96` 独占标志 + 排队 |
| 权限拒绝作为工具结果 | CC 通过 permission system 返回 is_error | `streaming_executor.py:127-130` 拒绝即返回 `ToolResult(is_error=True)` |
| max_turns 检查 | `:1705` `maxTurns && nextTurnCount > maxTurns` | `query_loop.py:130` 循环条件直接检查 |
| 正常下一轮 | `:1725` `transition: { reason: 'next_turn' }` | `query_loop.py:308-341` 追加 ToolResult 后 `continue` |
| 防螺旋：compact 一次性 | `:1157` `hasAttemptedReactiveCompact: true` | `query_loop.py:125` 同名布尔 |
| 防螺旋：drain 不重复 | `:1092` `state.transition?.reason !== 'collapse_drain_retry'` | N/A（没实现 drain） |
| **Transcript 修复**（进入 loop 前的前置步骤） | `utils/conversationRecovery.ts` | `cc/session/recovery.py:29-130` `validate_transcript()` |
| **子 Agent 嵌套**（作为工具调用） | `Task.ts` / AgentTool | `cc/tools/agent/agent_tool.py:35-200` execute() 内嵌 query_loop() |
| **续写消息措辞** | `:1226-1227` "Resume directly — no apology, no recap. Pick up mid-thought..." | `query_loop.py:246` "Please continue from where you left off." |

### 阅读建议

- **想抓核心**：先读 cc-python `query_loop.py:120-262`（140 行覆盖主循环 + 3 种恢复），理清骨架后再跳到 CC `query.ts:307-1728`
- **想看产品级完整度**：直接读 CC TS，重点看 CC 而 cc-python 没实现的几项（drain、stop hook 阻塞恢复、budget 续跑）
- **想迁移到其它语言**：读 cc-python 简化取舍后 +skill §5 Do Not Cargo-Cult 过滤产品特性
