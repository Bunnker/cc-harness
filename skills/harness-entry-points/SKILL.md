---
name: harness-entry-points
description: "指导如何设计多入口 Agent Runtime：交互式 CLI / Headless SDK / Bridge 或 API 入口共用同一条 query 主链，I/O 与会话生命周期在 adapter 层解耦"
user-invocable: true
argument-hint: "<目标项目路径或模块名>"
---

# 多入口架构 (Harness Entry Points)

## 1. Problem — 多入口不是多套执行核心

很多 Agent Runtime 会同时支持：

- 交互式 CLI / REPL
- Headless CLI / SDK
- HTTP / WebSocket / Bridge
- 后台任务或队列消费者

常见错误是为每个入口各写一套执行逻辑。这样一旦 query loop、权限、工具回流、session 恢复发生变化，所有入口都会漂移。

通用问题是：**如何让不同入口共享同一条执行主链，只把输入、输出、权限交互、生命周期管理留在 adapter 层。**

---

## 2. In Claude Code — 源码事实（精简版）

> `源码事实` — 下面是对 CC 入口设计的提炼，不是要求照抄目录结构。

### 入口并不只有一个

- CLI 交互模式：`cli.tsx -> main.tsx -> launchRepl() -> REPL.tsx`
- Headless 模式：`cli.tsx -> main.tsx -> runHeadless() -> print.ts`
- Bridge 模式：`cli.tsx -> bridgeMain() -> initReplBridge()`

### 真正的汇合点不是 `QueryEngine`，而是 `query()`

- REPL 通过 `useQueueProcessor()` 走到 `query()`
- Headless / SDK 通过 `QueryEngine.submitMessage()` 走到 `query()`
- Bridge 也是为每条消息创建 `QueryEngine`，最终仍然调用 `query()`

也就是说：

- `query()` 才是统一执行核心
- `QueryEngine` 只是某些入口使用的有状态封装
- 入口差异主要在 adapter 层，而不是主链

### 渲染器和核心逻辑是分开的

CC 至少有三类输出适配层：

- REPL：React/Ink 交互 UI
- Print：Headless / SDK 的文本或 JSON 输出
- Bridge：浏览器端消费的远程协议

### 会话状态不一定跟入口实例共生

Bridge 模式下每条消息都会新建 `QueryEngine`。这说明：

- 入口对象未必长期存活
- 会话状态必须能脱离入口对象持久化
- query 主链不能偷偷依赖“这个 adapter 一直在内存里”

---

## 3. Transferable Pattern — Core Query + Entry Adapter + Session Store

### 核心模式

把系统拆成三层：

1. `query core`
   负责消息流、模型调用、工具执行、恢复与退出语义。
2. `entry adapter`
   负责把 CLI / HTTP / SDK / Bridge 的输入翻译成统一请求，再把事件流渲染回各自协议。
3. `session store`
   负责消息历史、metadata、resume token、transcript。

### 推荐边界

```text
user / client
  -> entry adapter
  -> query core
  -> tool / model / policy layers
  -> event stream
  -> renderer / transport adapter
```

### 关键原则

1. `query()` 只接受标准化输入，不直接读终端、socket 或 HTTP 请求对象。
2. 权限交互通过 callback / policy interface 注入，不写死在核心循环里。
3. 会话恢复依赖独立存储，不依赖 REPL/Bridge 实例生命周期。
4. 输出用 event stream 表达，不让核心决定“是 print、UI 还是 JSON”。
5. 每个入口都只是 adapter，不拥有独立业务规则。

---

## 4. Minimal Portable Version — Python 伪实现

```python
from dataclasses import dataclass, field
from typing import Any, AsyncIterator


@dataclass
class QueryRequest:
    session_id: str
    messages: list[dict[str, Any]]
    metadata: dict[str, Any] = field(default_factory=dict)


class SessionStore:
    def load(self, session_id: str) -> list[dict[str, Any]]:
        return []

    def append(self, session_id: str, events: list[dict[str, Any]]) -> None:
        pass


async def query(request: QueryRequest, runtime) -> AsyncIterator[dict[str, Any]]:
    state = runtime.restore(request)
    while True:
        response = await runtime.call_model(state)
        yield {"type": "model_response", "payload": response}

        if not response.get("tool_calls"):
            return

        tool_events = await runtime.run_tools(response["tool_calls"])
        for event in tool_events:
            yield {"type": "tool_event", "payload": event}
        state = runtime.advance(state, response, tool_events)


class CliAdapter:
    def __init__(self, runtime, store: SessionStore):
        self.runtime = runtime
        self.store = store

    async def handle(self, session_id: str, user_text: str) -> None:
        history = self.store.load(session_id)
        request = QueryRequest(session_id=session_id, messages=[*history, {"role": "user", "content": user_text}])
        emitted = []
        async for event in query(request, self.runtime):
            emitted.append(event)
            self.render(event)
        self.store.append(session_id, emitted)

    def render(self, event: dict[str, Any]) -> None:
        print(event)


class HttpAdapter:
    def __init__(self, runtime, store: SessionStore):
        self.runtime = runtime
        self.store = store

    async def handle(self, body: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        history = self.store.load(body["session_id"])
        request = QueryRequest(session_id=body["session_id"], messages=[*history, *body["messages"]])
        async for event in query(request, self.runtime):
            yield event
```

这个最小版表达的是：

- 统一请求对象
- 统一 query core
- adapter 只做协议翻译与渲染
- session 持久化与 adapter 解耦

---

## 5. Do Not Cargo-Cult

不要照抄这些 CC 特有细节：

- React/Ink REPL 组件树
- Commander.js 的启动与路由方式
- Bridge 的 FlushGate、浏览器同步协议
- 每条消息是否新建 `QueryEngine` 的具体策略
- SDK 的 `stream-json` 子进程协议

真正该迁移的是边界：

- 一个 query 主链
- 多个 adapter
- 独立 session store
- 权限 / 渲染 / transport 通过接口注入

---

## 6. Adaptation Matrix

| 场景 | 推荐入口 | 核心注意点 |
|------|----------|------------|
| 个人 CLI 工具 | REPL + Headless | session 可用本地文件，权限可交互 |
| SDK / Embedding | Headless / stream API | 保证输出事件稳定，避免 UI 耦合 |
| Web IDE / 远程控制 | Bridge / WebSocket | adapter 可短生命周期，session 必须外置 |
| 队列或批处理 | Headless worker | query core 不应依赖用户实时确认 |

---

## 7. Implementation Steps

请分析用户的 `$ARGUMENTS`，然后：

1. 列出你需要支持的入口类型，而不是先写某个 CLI 框架。
2. 定义统一的 `QueryRequest / QueryEvent / SessionStore` 契约。
3. 把核心执行链收敛到一个 `query()` 或等价主循环。
4. 为每个入口实现 adapter：输入解析、权限回调、输出渲染、错误映射。
5. 确认 session 恢复不依赖 adapter 生命周期。
6. 用同一组 smoke tests 覆盖 REPL、headless、remote 三类入口。

验收标准：

- 新增入口时不需要复制 query 主链
- Headless / REPL / Bridge 的行为差异只存在于 adapter 层
- 会话恢复和 transcript 不依赖某个入口对象常驻内存
