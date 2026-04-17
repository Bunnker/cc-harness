---
name: tool-authoring
description: "指导如何撰写高质量 Agent 工具（ACI = Agent-Computer Interface）：四层合同（类型/语义/权限/UI） + 三层 prompt 结构（description / prompt / 字段 .describe）+ fail-safe 默认值 + 错误语义分层（前置验证 / 运行时 throw / 业务失败）。工具规模三层术语与 agent-tool-budget §一 保持一致。Anthropic 在《Building Effective Agents》里把 ACI 设计摆到和 HCI 同等优先级。"
user-invocable: false
argument-hint: "<目标项目路径或工具名>"
---

# Tool Authoring — ACI Design

## 1. Problem — "注册一个函数" 不等于"写好一个工具"

Anthropic 在《Building Effective Agents》里有句话：

> *One rule of thumb is to think about how much effort goes into human-computer interfaces (HCI), and plan to invest just as much effort in creating good **agent-computer interfaces (ACI)**.*

工程团队在 SWE-bench 上的经验验证了这点——*"spent more time optimizing our tools than the overall prompt."* 把工具路径参数从相对路径改绝对路径，错误率显著下降。

**"注册一个函数"只完成了 10%**。生产级工具要处理：

- **Prompt 工程**：工具描述是 context 的常驻消耗。150 词和 800 词的差别是每轮数百 token
- **命名冲突**：`read` / `Read` / `read_file` / `FileRead` — 同义词过多让模型选错
- **格式歧义**：相对路径 vs 绝对路径、UTF-8 vs bytes、JSON vs YAML，每种歧义都是失败率
- **默认值灾难**：`isConcurrencySafe` 默认 true 会让 Edit 并行改同一文件；默认 false 会让纯查询串行化
- **错误语义**：验证失败、运行时异常、模型误用——三种性质不同，要分别处理
- **规模失控**：工具数量超过 20 个后，"工具选择成本"成为 agent 新瓶颈

**通用问题**：如何设计一个工具契约，让工具的**类型契约 / 语义契约 / 权限契约 / UI 契约**各自独立可演进，同时让模型能高准确率地选用它。

---

## 2. In Claude Code — 源码事实

> `源码事实` — 具体回钉到 `src/Tool.ts` 和各工具文件行号。

### 四层合同（CC 设计的核心）

```
┌─────────────────────────────────────────────┐
│ 1. 类型契约（Tool.ts）                        │
│    name, inputSchema, call, prompt          │
│    → 保证接口一致，由 buildTool() 补全默认    │
├─────────────────────────────────────────────┤
│ 2. 语义契约（tools/*/prompt.ts）              │
│    description (短) + prompt (长 md) +       │
│    每字段 .describe()                        │
│    → 告诉模型"何时用、怎么用、别怎么用"       │
├─────────────────────────────────────────────┤
│ 3. 权限契约（isReadOnly / isDestructive）     │
│    checkPermissions(), validateInput()      │
│    → 驱动权限系统的 Tier 1 自动批准           │
├─────────────────────────────────────────────┤
│ 4. UI 契约（renderToolXxx）                   │
│    mapToolResultToToolResultBlockParam       │
│    → 工具结果与模型 context 分离              │
└─────────────────────────────────────────────┘
```

关键是 **UI 契约独立于语义契约**：模型看到的是 `mapToolResultToToolResultBlockParam()` 的纯文本，UI 层渲染是另一回事。这让"UI 好看"和"模型 context 省"两个目标不互相拖累。

### Tool 必需项与可选项（`Tool.ts:362-695`）

**必需**（6 项）：

| 字段/方法 | 类型 | 责任 |
|-----------|------|------|
| `name` | `string` | 工具唯一标识（对模型可见的 API 名） |
| `inputSchema` | `z.ZodType` | 参数的 Zod schema（自动转 JSON Schema） |
| `call(args, ctx)` | `Promise<ToolResult>` | 核心执行 |
| `description()` | `async => string` | 一句简介 |
| `prompt()` | `async => string` | 完整使用说明 markdown |
| `checkPermissions()` | `Promise<PermissionDecision>` | 权限决策 |

**可选（带 fail-safe 默认）**：由 `buildTool()` 在 `Tool.ts:757-769` 补全：

```typescript
const TOOL_DEFAULTS = {
  isEnabled:         () => true,
  isConcurrencySafe: (_input) => false,    // ⚠️ 默认假设不安全（串行）
  isReadOnly:        (_input) => false,    // ⚠️ 默认假设有写（问权限）
  isDestructive:     (_input) => false,
  checkPermissions:  () => ({ behavior: 'allow' }),
  toAutoClassifierInput: () => '',         // 分类器跳过
  userFacingName:    () => '',             // 用 name
}
```

**fail-safe 默认值是 ACI 的核心安全网**：忘了声明 `isConcurrencySafe` 的新工具会默认串行执行（慢但安全），不会意外并发破坏状态。

### 三层 Prompt 结构

CC 把"描述"拆成三层（具体字数统计自 `FileReadTool/prompt.ts`）：

> **关于下文词数的说明**：下面给出的"5-15 词 / 250-800 词 / 50-100 词"是**本仓库对 CC 现有工具的实测观察**，不是 CC/Anthropic 规定的硬约束。`Tool.ts` 里没有长度不变式，`FileReadTool/prompt.ts` 也只是一个具体实例。把它当作"健康范围参考"而不是"规范要求"——实际长度应由**工具边界复杂度**决定，简单工具可以短，有陷阱的工具需要详细。

**Level 1 — `description()`**（典型 5-15 词）  
`"Read a file from the local filesystem."`  
一句话说"这个工具是干什么的"。

**Level 2 — `prompt()`**（CC 实测典型 250-800 词 markdown；非硬规则）  
多段 markdown，运行时渲染（可插入配置值）。典型结构：

```markdown
Reads a file from the local filesystem. Assume this tool is able to
read all files on the machine. If the user provides a path, assume
that path is valid.

Usage:
- The file_path parameter must be an absolute path, not a relative path
- By default, it reads up to ${MAX_LINES_TO_READ} lines...
- ${offsetInstruction}
- ${lineFormat}
- This tool allows Claude Code to read images (PNG, JPG, etc.)
- For large PDFs (more than 10 pages), you MUST provide the pages parameter
- This tool can only read files, not directories. To read a directory, use an ls command.
```

典型小节（**按此顺序**最有效）：
1. 一句简介 + 能力范围
2. Usage 清单：参数必需/可选 + 默认行为
3. 边界：不能做什么（"only reads files, not directories"）
4. 与其他工具的关联（"use Bash for directory traversal"）
5. 特殊格式（图片、PDF、notebook）

**Level 3 — 每字段 `.describe()`**（CC 实测典型 50-100 词；非硬规则）

```typescript
z.strictObject({
  file_path: z.string().describe('The absolute path to the file to read'),
  offset: z.number().int().nonnegative().optional().describe(
    'The line number to start reading from. Only provide if the file is too large to read at once',
  ),
  limit: z.number().int().positive().optional().describe(
    'The number of lines to read. Only provide if the file is too large to read at once.',
  ),
})
```

每字段说**什么时候该传、什么时候别传**，不重复字段名本身的含义。

### 命名三层映射

| 层 | 风格 | 示例 |
|----|------|------|
| 类名 | PascalCase | `FileReadTool`, `BashTool`, `FileEditTool` |
| API name | 首字母大写单词 | `"Read"`, `"Bash"`, `"Edit"` |
| 常量 | SCREAMING_SNAKE_CASE | `FILE_READ_TOOL_NAME = "Read"` |

三者通过常量集中定义（`tools/FileReadTool/prompt.ts:5`），避免硬编码字符串散落。

**别名支持**（`Tool.ts:371`）：`aliases?: string[]`。重命名工具时保留旧名兼容旧 session。

### 工具规模与默认集

> **术语以 `agent-tool-budget` §一 为准**：**注册池 (Registered Pool)** / **可见目录 (Visible Catalog)** / **完整 Schema 集 (Fully-Loaded Schemas)**，数量由大到小。以下数字都是**本仓库对 CC 的实测读数**，不是 Anthropic 官方量化。

**注册池**（`src/tools.ts:193-250` 的 `getAllBaseTools()`）：**40+** 条（含特性门控未激活的和所有 MCP server 暴露的）

**可见目录**（默认配置下，用户 `/mcp` 或 ToolSearch 能看到的）：**30-40** 条（视 MCP 连接数）

**完整 Schema 集**（初始 prompt 里带 `input_schema` 的，即模型能直接调的）：
- 简化模式 `CLAUDE_CODE_SIMPLE=1`（`tools.ts:272-298`）：**3** — `const simpleTools: Tool[] = [BashTool, FileReadTool, FileEditTool]`
- 默认模式：**~15-20**（无条件 base + 符合条件的特性门控，不含 MCP）
- MCP 激活的工具通过 ToolSearch 按需加入

**Deferred 加载**：`shouldDefer: true` 或 `isMcp: true` 的工具不进初始 prompt 的完整 Schema 集。只在 `ToolSearchTool` 搜索并 reference 后才暴露 `input_schema`。这是把"注册池/可见目录"大、"完整 Schema 集"小同时成立的关键机制。

**阈值建议（本仓库工程启发式，非 Anthropic 官方）**：**完整 Schema 集 < 20**。超过这个量级后经验上模型的工具选择成本显著上升；但这是启发式，实际阈值取决于任务、模型和工具语义相似度，生产前建议自己做 eval。Anthropic 官方文档（Building Effective Agents、How Claude Code Works）只给"MCP 工具 default defer"的定性说法，没有给具体数字。

### 元数据驱动调度

三个布尔字段是并发调度与权限系统的真正驱动力：

```typescript
// FileReadTool.ts:373-378
isConcurrencySafe: () => true,   // 多 Read 可并行
isReadOnly:        () => true,   // 免权限询问（Tier 1 自动批准）

// FileEditTool 未声明 → 两者都默认 false
// 效果：独占调度 + 每次问权限

// BashTool.tsx —— 动态判断
isConcurrencySafe(input) {
  return this.isReadOnly?.(input) ?? false
},
isReadOnly(input) {
  return checkReadOnlyConstraints(input, ...).behavior === 'allow'
  // 逐命令语义检查：ls/cat/grep → readonly; rm/git push → not
},
```

**关键**：这些字段**可以依赖输入动态判断**，不是 class-level 常量。BashTool 就是典范——同一个工具根据 `command` 不同，可能 concurrency-safe 也可能不是。

### 错误语义的三种模式

CC 把错误分成**结构化的三类**，别混用：

**Pattern A — `validateInput()` 前置验证（无 I/O）**  
返回 `{result: false, message, errorCode, behavior?}`：

```typescript
// FileEditTool.ts:200-360
if (matches > 1 && !replace_all) {
  return {
    result: false,
    behavior: 'ask',            // 'allow' | 'ask' | 'deny'
    message: `Found ${matches} matches of the string to replace, but replace_all is false.`,
    errorCode: 9,               // 业务错误码
  }
}
```

**特征**：
- 消息面向**模型**（告诉它怎么修）
- `errorCode` 用于日志分类
- `behavior` 三值：允许继续 / 弹出询问 / 直接拒绝

**Pattern B — `call()` / `execute()` 运行时 I/O 失败**

两种对等实现，**整个 tool 内要一致，不要一个方法里混用**：

**B-TS**（CC 原版风格）：直接 `throw new Error()`，上层框架 catch 后转 `ToolResult(is_error=True)`：

```typescript
// FileReadTool.ts:609-650
if (code === 'ENOENT') {
  const similarFilename = findSimilarFile(fullFilePath)
  const cwdSuggestion = await suggestPathUnderCwd(fullFilePath)
  let message = `File does not exist.`
  if (cwdSuggestion) {
    message += ` Did you mean ${cwdSuggestion}?`
  }
  throw new Error(message)    // 依赖 orchestrator try/catch
}
```

**B-Py**（cc-python 风格，本 skill §4 Minimal 采用）：在 `execute()` 内 try/except，直接返回 `ToolResult(is_error=True, content=...)`；orchestrator 的 try/except 只兜底真正未预期的异常：

```python
# cc-python 风格
try:
    text = Path(file_path).read_text(...)
except FileNotFoundError:
    suggestion = find_similar(file_path)
    hint = f" Did you mean {suggestion}?" if suggestion else ""
    return ToolResult(content=f"File does not exist: {file_path}.{hint}", is_error=True)
```

cc-python `cc/tools/orchestration.py:157-161` 做最终兜底：任何工具未捕获的异常都统一转 `ToolResult(is_error=True, content=f"Error: {e}")`，防止 agent 循环崩溃。

**怎么选**：
- TS 项目沿用 throw（CC 惯例）。
- Python 项目**优先 B-Py**——Python 没有 `throw in async generator` 的惯用清理点，异常和 return 的路径混在一起不好推理。统一 return 让 tool 实现心智模型简单。
- 但**无论选哪种，都必须让 orchestrator 有兜底 try/except**，否则某个工具的意外异常会把整个主循环打挂。

**关键共通点**：错误消息不是"抱歉失败了"，而是"我试过了，但找不到；你是不是想说 X？"——给模型可操作的建议。

**Pattern C — 业务失败**  
工具**成功执行完**，但结果是"没找到/测试失败/编译错误"这类。用 `ToolResult(is_error=False)` 正常返回，把失败信息写进 content，让**模型自己解读**。**不要**把这类归为 Pattern A（不是参数错）或 Pattern B（不是 I/O 故障）——它们是"基础设施 OK，结果不如预期"。

### 案例对比：Read / Edit / Bash 的四种画像

| 维度 | FileReadTool | FileEditTool | BashTool |
|------|--------------|--------------|----------|
| `isConcurrencySafe` | **true**（恒真） | **false**（默认） | 动态（依赖命令） |
| `isReadOnly` | **true** | **false** | 动态 |
| `maxResultSizeChars` | `Infinity`（不持久化） | `100_000` | 默认 |
| `validateInput` | 轻量（路径+pages） | 繁重（6 层 TOCTOU 防护） | `checkReadOnlyConstraints`+rule |
| `call` 返回 | 文件内容 | `"File X has been updated..."` 不返原文 | 命令 stdout/stderr |
| 错误风格 | throw + 启发式建议 | validateInput 前置拒绝 | ValidateResult + behavior |

---

## 3. Transferable Pattern — 框架无关的工具设计

> `抽象模式` — 迁移到任何语言/框架都适用的核心。

### 核心原则（来自 Anthropic 官方）

**Principle 1**：*Give the model enough tokens to "think" before it writes itself into a corner.*  
→ 工具名简短、prompt 精炼，腾出空间让模型思考。

**Principle 2**：*Keep the format close to what the model has seen naturally occurring in text on the internet.*  
→ 参数用常见的自然形式（绝对路径、标准日期格式），不要自造格式。

**Principle 3**：*Make sure there's no formatting 'overhead'.*  
→ 不要让模型处理转义、计数、模板占位这些机械工作。

### 四层合同的可迁移结构

```
# 类型契约（强制）
name: str
input_schema: JSON Schema 或 Pydantic
execute(input) -> ToolResult

# 语义契约（分三层；词数为 CC 实测典型值，非硬规则）
description: 一句简介（5-15 词）
prompt: 使用指南 markdown（250-800 词典型，实际视边界复杂度自定）
每字段 .describe(): 使用边界（50-100 词典型）

# 权限契约（可选，默认 fail-safe）
is_read_only(input) -> bool = False     # 默认有写，问权限
is_concurrency_safe(input) -> bool = False  # 默认独占
is_destructive(input) -> bool = False   # 默认无需特殊警告

# UI 契约（可选）
render_result(result) -> UINode         # 给用户看
result_to_block(result) -> ToolResult   # 给模型看（节省 context）
```

### 命名的三层映射（可迁移）

```python
# 常量集中定义，类名/注册名/API name 都引用同一个
FILE_READ_TOOL_NAME = "Read"

class FileReadTool(Tool):
    def get_name(self) -> str:
        return FILE_READ_TOOL_NAME  # 永远不硬编码字符串
```

**为什么重要**：重命名工具是高频操作（产品演进）。散落各处的字符串会导致遗漏，集中常量让重命名是一次 grep + rename。

### 元数据驱动调度

把"这个工具是什么性质"从工具代码里抽出来交给调度层：

```
工具声明元数据     调度层消费
───────────────  ──────────────
is_concurrency_safe → StreamingExecutor 并发调度
is_read_only       → PermissionSystem Tier 1 免问
is_destructive     → UI 警告级别
search_hint        → ToolSearch 按需加载
should_defer       → 初始 prompt 是否包含完整 schema
```

**benefit**：工具的"性质"成为声明式数据，而不是散落在调度器各处的 if-else。添加新工具只要填字段，不改调度逻辑。

### 错误分层

| 错误类型 | 何时使用 | 传播方式 | 消息受众 |
|---------|---------|---------|---------|
| **前置验证** | 参数非法、策略拒绝 | `return {result: false, message, behavior}` | 模型（给修复建议） |
| **运行时 I/O 失败** | 文件不存在、网络错、超时 | TS 风格：`throw` → orchestrator catch；Python 风格：`try/except` → `return ToolResult(is_error=True)`。**两种整 tool 内择一，不混用**。orchestrator 必须兜底未捕获异常。 | 模型（启发式建议） |
| **业务失败** | 工具执行成功但结果是"失败"（tests failed、grep 无结果） | `ToolResult(is_error=False)` 正常返回 | 模型（自由解读） |

**关键反模式**：用异常表达业务失败（"tests failed → throw"），会让上层 retry 逻辑误以为是基础设施故障。

### 关键 Tradeoff

| 选择 | 好处 | 代价 |
|------|------|------|
| Zod/Pydantic schema | 自动生成 JSON Schema，编译期类型检查 | 额外依赖，schema 与 description 两处维护 |
| 手写 dict schema（cc-python 方式） | 零依赖，直接看 API 期望格式 | 无类型检查，易手误 |
| `isConcurrencySafe: true` 默认 | 多工具并行，快 | 踩到 Edit 并发灾难的风险 |
| `isConcurrencySafe: false` 默认（CC 方式） | 安全（默认串行） | 性能略差，需要显式声明 read 类工具 |
| 工具名短（"Read"） | 省 token，模型好选 | 跨项目冲突（MCP 多个 server 都有 Read） |
| 工具名前缀（"mcp__xyz__read"） | 命名空间隔离，无冲突 | 占 token，影响模型选择 |
| UI 渲染与模型 context 分离 | 可以展示 diff 美化，模型看纯文本 | 多一层 mapping 函数 |

---

## 4. Minimal Portable Version — 一个工具的完整模板

> `最小版` — Python async 版本的 FileReadTool，够完整到直接拿去改。

```python
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Any
from pathlib import Path

# === 元数据常量（集中定义，避免散落字符串）===
FILE_READ_TOOL_NAME = "Read"
MAX_LINES_DEFAULT = 2000

# === ToolResult 结构 ===
@dataclass
class ToolResult:
    content: str | list[dict[str, Any]]   # 支持纯文本或富内容（图片、表格）
    is_error: bool = False
    # 可选：metadata 用于 UI 渲染，模型不可见
    metadata: dict[str, Any] | None = None

# === 工具定义 ===
class FileReadTool:
    """读文件的最小实现。体现四层合同。"""

    # ─── 1. 类型契约 ───
    def get_name(self) -> str:
        return FILE_READ_TOOL_NAME

    def get_schema(self) -> dict:
        return {
            "name": FILE_READ_TOOL_NAME,
            "description": self._description(),       # Level 1
            "input_schema": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": (              # Level 3
                            "The absolute path to the file to read. "
                            "Must NOT be a relative path."
                        ),
                    },
                    "offset": {
                        "type": "integer",
                        "description": (
                            "The line number to start reading from. "
                            "Only provide if the file is too large to read at once."
                        ),
                    },
                    "limit": {
                        "type": "integer",
                        "description": (
                            "The number of lines to read. Default: 2000."
                        ),
                    },
                },
                "required": ["file_path"],
            },
        }

    # ─── 2. 语义契约 ───
    def _description(self) -> str:
        return "Read a file from the local filesystem."   # Level 1: 5-15 词

    def get_prompt(self) -> str:
        # Level 2: markdown，按固定节序（本例约 150 词；典型 250-800，视工具边界复杂度自定）
        return f"""\
Reads a file from the local filesystem. Assume this tool is able to
read all files on the machine.

Usage:
- The file_path parameter must be an absolute path, not a relative path
- By default, reads up to {MAX_LINES_DEFAULT} lines from the beginning
- Results use `cat -n` format with line numbers starting at 1
- Use offset + limit for files larger than {MAX_LINES_DEFAULT} lines

Limitations:
- This tool can only read files, not directories
  (to read a directory, use a Bash `ls` command instead)
- Binary files are not supported

Related tools:
- Use Grep to search file contents by regex
- Use Glob to find files by name pattern
"""

    # ─── 3. 权限契约（三个元数据）───
    def is_concurrency_safe(self, tool_input: dict) -> bool:
        return True            # 多个 Read 可并行

    def is_read_only(self, tool_input: dict) -> bool:
        return True            # 权限系统自动 Tier 1 批准

    def is_destructive(self, tool_input: dict) -> bool:
        return False

    # ─── 4. 执行 ───
    async def execute(self, tool_input: dict) -> ToolResult:
        file_path = tool_input["file_path"]

        # 前置验证（Pattern A）
        if not Path(file_path).is_absolute():
            return ToolResult(
                content=(
                    f"file_path must be absolute. Got: {file_path!r}. "
                    f"Convert to absolute path and retry."
                ),
                is_error=True,
            )
        if Path(file_path).is_dir():
            return ToolResult(
                content=f"{file_path} is a directory, not a file. "
                        f"Use Bash `ls` to list directory contents.",
                is_error=True,
            )

        # 运行时 I/O 失败（Pattern B-Py 风格）—— tool 内捕获并 return ToolResult，带启发式建议
        try:
            text = Path(file_path).read_text(encoding="utf-8", errors="replace")
        except FileNotFoundError:
            suggestion = self._find_similar(file_path)
            hint = f" Did you mean {suggestion}?" if suggestion else ""
            return ToolResult(
                content=f"File does not exist: {file_path}.{hint}",
                is_error=True,
            )

        # 业务结果：成功，正常返回
        offset = tool_input.get("offset", 0)
        limit = tool_input.get("limit", MAX_LINES_DEFAULT)
        lines = text.splitlines()[offset:offset + limit]
        numbered = "\n".join(f"{i+offset+1:6d}\t{line}" for i, line in enumerate(lines))
        return ToolResult(content=numbered, is_error=False)

    def _find_similar(self, path: str) -> str | None:
        # ... 实现略：找同级目录下最接近的文件名
        return None


# === UI 契约（可选）===
def render_tool_use(tool_input: dict) -> str:
    """给用户看的单行摘要"""
    return f"Read {tool_input['file_path']}"

def render_tool_result(result: ToolResult) -> str:
    """给用户看的结果（可折叠显示）"""
    if result.is_error:
        return f"❌ {result.content}"
    lines = result.content.count("\n") + 1
    return f"✓ Read {lines} lines"
```

**这份模板体现了**：
- 三层 prompt（description / get_prompt / 每字段 description）
- 四层合同（类型 / 语义 / 权限 / UI）都显式存在
- 三种错误模式各有对应分支
- 元数据 is_concurrency_safe / is_read_only / is_destructive 显式声明
- UI 渲染与模型可见的 content 分离

---

## 5. Do Not Cargo-Cult

> `不要照抄` — CC 的具体选择，搬之前想想要不要。

1. **不要给每个工具都写 800 词 prompt**。Read/Edit/Bash 是高频核心工具，值得重投入；一个只被模型调用几次的边缘工具 200 词足够。prompt 长度和调用频次要成正比。

2. **不要硬编码工具名字符串**。cc-python 把 `FILE_READ_TOOL_NAME = "Read"` 集中常量化——这是产品级做法。散落的 `"Read"` 字符串在重命名时是个坑。即便是小项目也值得做。

3. **不要把"业务失败"混进运行时异常分支**。"测试失败"、"grep 无结果"是**基础设施 OK + 结果不如预期**，用 `ToolResult(is_error=False)` 正常返回让模型自己解读。运行时异常（I/O、网络、OOM）的处理策略看**语言选择**（见 §3 Pattern B 的 B-TS / B-Py 对比）：Python 项目推荐在 tool 内 try/except + return ToolResult；TS 项目 throw 让 orchestrator 兜底。但无论哪种，都**必须和业务失败语义分开**——三类混用会让上层 retry 逻辑失灵。

4. **不要把所有工具塞进完整 Schema 集**。官方文档给的定性原则是"MCP 工具 default defer"；量化的 <20 建议是**本仓库工程启发式**，请自己在目标场景做 eval 确认。实操上：核心工具进完整 Schema 集，其余走 ToolSearch / Skill / MCP defer 到"可见目录"或"注册池"。

5. **不要复制 CC 的 UI 渲染层**。`renderToolUseMessage / renderToolResultMessage` 是为 Ink + 终端 UI 设计的；Web UI、Slack bot、CI 场景都不适用。只保留**模型可见/不可见**的二分就够：`mapToolResultToToolResultBlockParam` 决定模型看到什么，其它归 UI。

6. **不要用同一个工具做"读"和"写"**。CC 为什么把 `Read` 和 `Edit` 分开？因为它们的**并发/权限/错误语义完全不同**。一个 `file_op` 万能工具会让这四层合同全部退化为"最坏情况"（not concurrency-safe + needs permission + 复杂 validateInput）。

7. **不要让 `isConcurrencySafe` 默认 true**。默认 false（CC 选择）是正确的 fail-safe：忘了声明的新工具默认串行，慢但安全。反过来则会在 Edit + Edit 并发时破坏状态。

8. **不要用 Zod/Pydantic 就忽视 `.describe()`**。schema 自动转换只解决了**机器可读**；`.describe()` 是给**模型可读**的。Zod 自动转换出的 JSON Schema 如果没加 description 字段，模型只能看到字段名猜用途。

---

## 6. Adaptation Matrix

> `迁移建议` — 不同项目的工具设计裁剪方案。

下表的"工具集规模"指**完整 Schema 集**（模型能直接调用的条目数），术语见 `agent-tool-budget` §一。数字均为启发式建议。

| 项目类型 | 完整 Schema 集 | Prompt 层级 | 元数据字段 | UI 渲染 | 注意事项 |
|----------|---------------|-----------|-----------|---------|---------|
| **玩具/学习项目** | 3-5 个 | 只要 Level 1 (description) | 省略，都默认 false | 省略 | 专注核心功能，不堆料 |
| **CLI Agent** | 10-15 个 | Level 1 + Level 3 必备 | is_concurrency_safe + is_read_only | 行文本足够 | 参考 cc-python 简化版 |
| **生产 IDE Agent（类 CC）** | 15-20 个 + defer 池 | 三层完整 | 四字段 + searchHint + shouldDefer | 丰富（diff、图片、表格） | 参考 CC 完整契约 |
| **批处理/后台 Agent** | 5-10 个，集中域 | 描述偏"机器能做什么" | is_idempotent（自定义）最重要 | 仅日志 | 幂等 > 并发 |
| **多租户 SaaS** | 按租户过滤 | 每个工具加 tenant 边界说明 | + is_tenant_scoped | 按用户偏好 | Prompt 里显式声明租户边界 |
| **MCP 服务端** | 每 server <10 | 每工具必 prompt 完整 | 必须 is_concurrency_safe | 交给客户端 | 命名前缀（`mcp__<srv>__<tool>`） |

### 具体场景：小项目加 Skill-style 工具

如果项目是给 LLM 提供 10 个以内的工具，一个轻量做法：

```python
def tool(name: str, description: str, is_read_only: bool = False,
         is_concurrency_safe: bool = False):
    """装饰器形式，最小契约"""
    def decorator(func):
        func._tool_name = name
        func._description = description
        func._is_read_only = is_read_only
        func._is_concurrency_safe = is_concurrency_safe
        return func
    return decorator

@tool("Read", "Read a file", is_read_only=True, is_concurrency_safe=True)
async def read_tool(file_path: str, offset: int = 0, limit: int = 2000):
    ...
```

这是"最小可用"版本，适合原型。产品化时再升级到完整 Tool 基类。

---

## 7. Implementation Steps

一个工具从零到完整的 10 步：

1. **先写用途句** — 一句话说清这个工具是干什么。如果写不出简洁一句话，说明工具边界不清，**先拆**。

2. **定常量名** — `FILE_READ_TOOL_NAME = "Read"` 集中常量，永远不散字符串。

3. **写 Level 1 description** — 5-15 词，与常量同文件。

4. **写 input schema** — 每字段必加 `.describe()` 或等价。描述应回答"什么时候传、什么时候别传"，不要重复字段名。

5. **显式声明三个元数据** — `is_concurrency_safe / is_read_only / is_destructive`。**别依赖默认值**——显式声明是给读者（和自己）看的。

6. **实现 execute** — 分三类错误分支：
   - 前置验证失败 (Pattern A) → `ToolResult(is_error=True, content="告诉模型怎么修")`
   - 运行时 I/O 失败 (Pattern B) → 语言选择：Python 用 try/except + `return ToolResult(is_error=True)` 带启发式建议（B-Py，推荐）；TS 用 `throw` 依赖 orchestrator 兜底（B-TS）
   - 业务失败（"grep 无结果"等；Pattern C） → `ToolResult(is_error=False)` 正常返回

7. **写 Level 2 prompt**（高频工具） — markdown 按固定节序：简介 → Usage 清单 → 边界 → 相关工具 → 特殊格式。CC 实测典型 250-800 词，但**实际长度由工具边界复杂度决定**：有 TOCTOU / 并发 / 路径歧义等陷阱的工具需要多写；简单 getter 100 词足够。先上线再按调用失败案例迭代加长。

8. **加 UI 渲染**（如有终端/Web UI） — 两个函数：`render_tool_use`（调用时）+ `render_tool_result`（结果时）。这两个**不影响模型 context**。

9. **注册进工具集** — 决定是进完整 Schema 集、可见目录（defer）、还是只留注册池（feature-gate off）。完整 Schema 集建议 < 20（本仓库工程启发式，见 `agent-tool-budget` §一）。

10. **写 3-5 个 eval 样本** — 模型应该用这个工具的 3 个正面场景 + 2 个反面场景（不应该用这个工具的情况）。eval 驱动 prompt 迭代。

---

## 8. Source Anchors

> 两份源码并列对照。想学"为什么这样设计"读 TS；想学"最小怎么实现"读 Python。

| 关注点 | CC TS (`src/`) | cc-python |
|--------|----------------|-----------|
| Tool 基类/接口 | `Tool.ts:362-695`（Tool / ToolDef 分型 + buildTool 补全） | `cc/tools/base.py:69-111`（抽象 4 方法） |
| fail-safe 默认值 | `Tool.ts:757-769` `TOOL_DEFAULTS` | `base.py:88-98` 只有 `is_concurrency_safe` 默认 false |
| 元数据字段（完整集） | `isConcurrencySafe / isReadOnly / isDestructive / searchHint / maxResultSizeChars / shouldDefer` | 仅 `is_concurrency_safe(input)`（简化） |
| 工具命名常量 | `tools/FileReadTool/prompt.ts:5` `FILE_READ_TOOL_NAME = "Read"` | `cc/tools/file_read/file_read_tool.py:26` 同名同值 |
| Level 1 description | `FileReadTool.ts:344-346` `description()` 异步 | `file_read_tool.py` `get_schema().description` 同步字段 |
| Level 2 prompt 渲染 | `tools/FileReadTool/prompt.ts:27-49` `renderPromptTemplate()` 含运行时参数 | cc-python 简化：prompt 嵌入 schema description |
| Level 3 字段 describe | `FileReadTool.ts:227-243` Zod `.describe()` 每字段 | `file_read_tool.py:42-64` dict `"description"` 字段 |
| **Read 工具案例** | `tools/FileReadTool/FileReadTool.ts:337-718` | `cc/tools/file_read/file_read_tool.py` 整文件 |
| **Edit 工具案例** | `tools/FileEditTool/FileEditTool.ts:86-595`（6 层 validateInput） | `cc/tools/file_edit/file_edit_tool.py` |
| **Bash 工具案例** | `tools/BashTool/BashTool.tsx:200-500`（命令语义化判定 readonly） | `cc/tools/bash/bash_tool.py:97-156` |
| 错误 Pattern A（validateInput） | `FileEditTool.ts:200-360` 返回 `{result:false, behavior, errorCode}` | cc-python 未单独分 validate 阶段 |
| 错误 Pattern B（运行时 throw） | `FileReadTool.ts:609-650` ENOENT → throw + similar file 启发式 | `cc/tools/orchestration.py:157-161` 统一捕获转 is_error |
| 错误 Pattern C（ToolResult.is_error） | `tools/*` 混用 | cc-python 主要风格（base.py:35-66 ToolResult） |
| 工具注册表 | `src/tools.ts:193-250` 全量 + 特性门控 | `cc/main.py:76-187` `_build_registry()` 三层注册 |
| Simple 模式（3 工具） | `tools.ts:272-298` `CLAUDE_CODE_SIMPLE` | 无（cc-python 默认即 26 工具） |
| Deferred / ToolSearch | `tools.ts` `shouldDefer` + `src/tools/ToolSearchTool/` | cc-python 未实现 defer |
| MCP 工具动态加载 | `src/services/mcpClient/*` | `cc/main.py:_connect_mcp_servers()` |
| UI 渲染分离 | `Tool.ts:605-667` 6 个 renderXxx 方法 + `mapToolResultToToolResultBlockParam` | cc-python 未实现（归终端主循环） |

### 阅读建议

- **先看 Python**：`cc/tools/base.py` (100 行) + `file_read/file_read_tool.py`（完整工具样例）——30 分钟理解契约骨架
- **再看 TS 三大工具**：FileRead → FileEdit → Bash，对应"并发安全 / 独占写 / 动态判断"三种画像
- **最后看 `Tool.ts`**：`buildTool()` + `TOOL_DEFAULTS`——搞清 fail-safe 默认值如何守护整个系统

### 与其它 skill 的连接

- **`agent-tool-budget`** — 工具数量与 token 预算的关系，本 skill 讲"单个工具怎么写"，那个讲"工具集怎么管"
- **`unified-tool-interface`** — 工具契约的类型层详细展开
- **`layered-permission`** — 本 skill 的"权限契约"（is_read_only / is_destructive）是权限系统的输入
- **`concurrent-dispatch`** — 本 skill 的 `is_concurrency_safe` 是调度器的输入
- **`mcp-runtime`** — MCP 工具的 defer 加载与命名空间前缀
