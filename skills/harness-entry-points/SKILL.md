---
name: harness-entry-points
description: "多入口接入同一主链：CLI 交互/Headless/Bridge/SDK 三个入口 + REPL/print/bridge 三个渲染器 + query() 是真正的汇合点"
user-invocable: true
argument-hint: "<目标项目路径或模块名>"
---

# 多入口架构

> 参考实现：`src/entrypoints/cli.tsx`（CLI 路由）、`src/main.tsx`（主初始化）、`src/screens/REPL.tsx`（交互渲染）、`src/cli/print.ts`（Headless 渲染）、`src/QueryEngine.ts`（执行核心）、`src/bridge/bridgeMain.ts`（Bridge 入口）

## 源码事实

### 1. 三个入口，不是一个

```
入口 1: CLI 交互模式
  cli.tsx → main.tsx:main() → Commander → launchRepl() → REPL.tsx
  REPL.tsx 是 React/Ink 组件，用 useQueueProcessor() 驱动 query()

入口 2: CLI Headless 模式（也是 SDK 的实际入口）
  cli.tsx → main.tsx:main() → Commander → runHeadless() → print.ts
  print.ts 中的 ask() 函数实例化 QueryEngine → submitMessage()

入口 3: Bridge 模式（远程控制）
  cli.tsx → 快速路径检测 → bridgeMain() → initReplBridge()
  每条消息创建新的 QueryEngine 实例
  不经过 main.tsx 的完整初始化路径
```

### 2. QueryEngine 不是"唯一执行引擎"——query() 才是汇合点

```
REPL.tsx:
  → useQueueProcessor() 
  → 内部调用 query() 函数
  → 不直接实例化 QueryEngine

print.ts (Headless/SDK):
  → ask() generator 
  → 实例化 QueryEngine
  → QueryEngine.submitMessage() → 内部调用 query()

Bridge:
  → createQueryEngineForMessage()
  → 每条消息新建 QueryEngine 实例
  → QueryEngine.submitMessage() → 内部调用 query()
```

**真正的汇合点是 `query()` 函数**（`src/query.ts`），不是 QueryEngine 类。QueryEngine 是 query() 的有状态封装——管理消息历史、文件缓存、usage 追踪——但三个入口接入 query() 的方式不同。

### 3. SDK 没有独立入口——复用 CLI Headless 路径

```
SDK（@anthropic-ai/claude-agent-sdk）:
  → 生成子进程: claude -p --output-format stream-json
  → 走 cli.tsx → main.tsx → runHeadless() → print.ts → ask()
  → stdin: JSON 消息
  → stdout: JSON 响应

SDK 不是一个独立的代码路径。它是 CLI Headless 模式 + JSON 格式化输出。
```

### 4. Bridge 的 QueryEngine 是每消息新建的

```
Bridge 模式下：
  claude.ai/code 发一条消息 → bridgeMain 接收
  → 为这条消息创建新的 QueryEngine
  → QueryEngine 处理 → 返回结果
  → QueryEngine 实例销毁

会话状态不靠 QueryEngine 实例保持——靠 recordTranscript() 和 restoreSessionMetadata()
```

### 5. 三个渲染器各自独立

| 渲染器 | 文件 | 用途 | 特点 |
|--------|------|------|------|
| **REPL** | `src/screens/REPL.tsx` | 交互式 CLI | React/Ink TUI，实时渲染 |
| **Print** | `src/cli/print.ts` | Headless + SDK | 文本/JSON 输出，无 UI |
| **Bridge UI** | claude.ai/code（浏览器端） | 远程控制 | Bridge 进程发 WebSocket |

---

## 可迁移设计

### 核心逻辑和入口解耦

你的项目应该做的：

```python
# 核心：纯逻辑，不含 I/O 和 UI
async def query(messages, tools, model, ...):
    """所有入口最终都调用这个函数"""
    while True:
        response = await call_model(messages)
        tool_calls = extract_tool_calls(response)
        if not tool_calls:
            yield response
            return
        results = await execute_tools(tool_calls)
        messages.extend(results)
        yield response

# 入口 1: 交互式
class InteractiveREPL:
    async def run(self):
        while True:
            user_input = await get_input()
            async for msg in query(self.messages + [user_input], ...):
                self.render(msg)

# 入口 2: Headless / SDK
class HeadlessRunner:
    async def run(self, prompt: str):
        async for msg in query([prompt], ...):
            print(json.dumps(msg))

# 入口 3: API 服务
class APIHandler:
    async def handle(self, request):
        async for msg in query([request.prompt], ...):
            yield msg
```

**关键原则**：`query()` 是纯函数（输入消息 → 输出消息），入口负责 I/O 和 UI。

### 权限回调解耦

不同入口的权限机制不同，用回调抽象：

```python
# 交互式：弹终端对话框
async def interactive_permission(tool, input):
    answer = await prompt_user(f"允许 {tool.name}?")
    return answer

# Headless/SDK：调用方提供的回调
async def sdk_permission(tool, input):
    return config.permission_callback(tool, input)

# 无人值守：Hook 接管或自动拒绝
async def headless_permission(tool, input):
    hook_result = await run_hooks(tool, input)
    if hook_result: return hook_result
    return "deny"  # 没有人可以点"允许"
```

---

## 不要照抄的实现细节

- REPL.tsx 是 5000+ 行的 React/Ink 组件——你的项目大概率不需要这个级别的终端 UI
- print.ts 的 ask() 函数处理了很多 CC 特有的 SDK 协议细节（output-format, input-format）
- Bridge 的 FlushGate 机制（启动时排队新消息等历史同步）是分布式特有的
- Commander.js 的 preAction hook 用于懒初始化——你可以用更简单的启动逻辑

---

## 反模式

- 不要说"QueryEngine 是唯一执行引擎"——它是 query() 的有状态封装，REPL 不直接用它
- 不要为每种入口写独立的 Agent 逻辑——一个 query() + 多个 adapter
- 不要在 query() 里写 I/O 代码——输出通过 yield/generator，让 adapter 决定怎么渲染
- 不要假设 QueryEngine 实例在整个会话中存活——Bridge 模式每消息新建
