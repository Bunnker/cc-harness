---
name: unified-tool-interface
description: "指导如何设计统一工具契约：定义层与运行层分离、内置与外部工具双轨 schema、稳定组装、权限/执行管道解耦"
user-invocable: true
argument-hint: "<目标项目路径或模块名>"
---

# 统一工具接口 (Unified Tool Interface)

## 1. Problem — 工具系统不是“函数列表 + JSON Schema”

Agent Runtime 里的工具通常同时包含：

- 内置工具
- 外部工具（MCP / plugin / HTTP capability）
- 权限与安全属性
- 面向模型的 schema
- 面向执行器的运行时方法

常见错误是把它们揉成一个结构体，然后在不同地方不断追加字段。结果就是：

- 定义层和运行层耦合
- 内置工具与外部工具协议混写
- tool list 顺序不稳定，影响 cache 与回归
- 安全默认值缺失，作者忘填字段就直接放开

通用问题是：**如何把“工具定义”“工具组装”“工具 schema 序列化”“工具执行管道”拆成清晰的层次，并且能同时容纳本地工具与外部工具。**

---

## 2. In Claude Code — 源码事实（精简版）

> `源码事实` — 这里保留的是结构，不是要求照抄 CC 的 50+ 字段工具类型。

### CC 区分 ToolDef 和 Tool

核心思想是：

- 作者编写的是精简定义（类似 `ToolDef`）
- 框架通过工厂补齐安全默认值，产出完整运行时工具（类似 `Tool`）

这样做的目的不是省几行代码，而是 fail-closed：

- 没声明并发安全 -> 默认不安全
- 没声明只读 -> 默认可能写入
- 没声明权限逻辑 -> 走框架默认策略

### CC 同时支持两类 schema 来源

- 内置工具：本地类型系统 / schema 对象
- 外部工具：远端直接返回的 JSON Schema

这意味着“工具的输入 schema”不能只用一种表示。定义层必须能表达：

- 本地静态 schema
- 远端动态 schema

### 工具列表有专门的组装路径

CC 里真正发给模型的工具池不是“哪里需要哪里拼”，而是有集中 assembly。这里做了两件关键事：

- 同名去重，避免外部工具覆盖内置工具
- 稳定排序，避免 cache key 漂移

### 工具执行不是 `tool.call()` 一步

实际执行链至少涉及：

- 工具查找与别名解析
- 输入验证
- 权限检查 / hook
- 真正调用
- 结果包装与遥测

如果把这些逻辑写在工具本体里，工具系统会立刻失去统一边界。

---

## 3. Transferable Pattern — Definition / Assembly / Execution Pipeline

### 核心模式

把工具系统拆成四层：

1. `ToolDefinition`
   作者声明的最小必要信息。
2. `ToolRuntime`
   由工厂补齐默认值后的可执行对象。
3. `ToolAssembly`
   把 builtin / external / filtered tools 组装为稳定工具池。
4. `ToolExecutionPipeline`
   统一处理验证、权限、调用、结果包装和日志。

### 推荐数据模型

```text
ToolDefinition:
  name
  description
  input_schema | input_json_schema
  call()
  capability_flags

ToolRuntime:
  definition
  safety_defaults
  permission_strategy
  classification_metadata
```

### 关键原则

1. 定义层和运行层必须分开，安全默认值由框架提供。
2. 内置工具与外部工具共用抽象接口，但 schema 来源允许不同。
3. 发给模型的工具池必须统一组装并稳定排序。
4. API schema 序列化发生在组装/请求阶段，而不是混进工具定义本体。
5. 执行链统一进 pipeline，不要把权限、hook、telemetry 散落到每个工具里。

---

## 4. Minimal Portable Version — Python 最小实现

```python
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class ToolDefinition:
    name: str
    description: str
    call: Callable[[dict[str, Any]], Any]
    input_schema: dict[str, Any] | None = None
    input_json_schema: dict[str, Any] | None = None
    is_read_only: bool | None = None
    is_concurrency_safe: bool | None = None


@dataclass
class ToolRuntime:
    name: str
    description: str
    call: Callable[[dict[str, Any]], Any]
    input_schema: dict[str, Any] | None
    input_json_schema: dict[str, Any] | None
    is_read_only: bool
    is_concurrency_safe: bool


def build_tool(defn: ToolDefinition) -> ToolRuntime:
    return ToolRuntime(
        name=defn.name,
        description=defn.description,
        call=defn.call,
        input_schema=defn.input_schema,
        input_json_schema=defn.input_json_schema,
        is_read_only=bool(defn.is_read_only) if defn.is_read_only is not None else False,
        is_concurrency_safe=bool(defn.is_concurrency_safe) if defn.is_concurrency_safe is not None else False,
    )


def assemble_tool_pool(builtin: list[ToolRuntime], external: list[ToolRuntime]) -> list[ToolRuntime]:
    merged = {tool.name: tool for tool in builtin}
    for tool in external:
        merged.setdefault(tool.name, tool)
    return sorted(merged.values(), key=lambda tool: tool.name)


def tool_to_api_schema(tool: ToolRuntime) -> dict[str, Any]:
    schema = tool.input_json_schema or tool.input_schema or {"type": "object", "properties": {}}
    return {
        "name": tool.name,
        "description": tool.description,
        "input_schema": schema,
    }


def run_tool(tool: ToolRuntime, payload: dict[str, Any], permission_check) -> Any:
    permission_check(tool, payload)
    return tool.call(payload)
```

这个最小版表达的是：

- 作者定义与框架运行时分离
- 双轨 schema
- 稳定组装
- 权限检查走统一 pipeline

---

## 5. Do Not Cargo-Cult

不要照抄这些 CC 细节：

- 50+ 字段的超大 `Tool` 类型
- 所有 UI 渲染相关方法
- `searchHint`、`cache_control`、`defer_loading` 等 CC 特定字段
- MCP annotation 的具体字段名
- CC 的遥测或 hook 事件命名

真正该迁移的是：

- fail-closed 默认值
- definition/runtime 分层
- 内置与外部工具双轨 schema
- 稳定 assembly
- 统一 execution pipeline

---

## 6. Adaptation Matrix

| 场景 | 推荐策略 | 特别注意 |
|------|----------|----------|
| 个人 CLI Agent | builtin 为主，少量外部工具 | 先把安全默认值和执行管道做对 |
| MCP / Plugin 生态 | builtin + external 双轨 | 外部 schema 不要强制转本地类型系统 |
| 多租户平台 | tool pool 按租户过滤 | assembly 与权限策略要可审计 |
| 高并发服务端 | 工具执行器独立 | `is_concurrency_safe` 需要真正参与调度 |

---

## 7. Implementation Steps

请分析用户的 `$ARGUMENTS`，然后：

1. 定义 `ToolDefinition` 与 `ToolRuntime` 两层结构。
2. 为缺省安全属性设置 fail-closed 默认值。
3. 设计双轨 schema：本地 schema 与外部 JSON Schema。
4. 实现统一的 tool assembly：去重、排序、过滤。
5. 实现 `tool_to_api_schema()`，把面向模型的字段放到序列化层。
6. 实现执行 pipeline：查找、校验、权限、调用、结果包装、日志。
7. 用测试覆盖：同名冲突、排序稳定性、外部 schema、默认并发安全值。

验收标准：

- 新增工具时作者只需声明最小定义
- 外部工具可以不依赖本地类型系统直接接入
- 同一批工具重复组装时顺序稳定
- 权限与执行策略不会散落到每个工具实现里
