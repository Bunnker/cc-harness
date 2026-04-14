---
name: context-engineering
description: "指导如何设计 Agent 上下文工程：多源 System Prompt 组装 + 二级缓存 + 渐进压缩 + 预算分配"
user-invocable: true
argument-hint: "<目标项目路径或模块名>"
---

# Agent 上下文工程 (Context Engineering)

## 1. Problem — 有限窗口里传达最多有效信息

LLM 的上下文窗口是稀缺资源。Agent 的 system prompt 来自多个来源（角色定义、工具规则、环境信息、用户指令、记忆），每轮还有工具结果和附件不断累积。

通用问题是：**如何从多个来源组装 system prompt，按优先级分配 token 预算，并在逼近窗口极限时触发压缩，使 Agent 在整个会话周期内保持可用。**

---

## 2. In Claude Code — 源码事实

> 以下内容回钉到具体文件。

### 多源 System Prompt 组装管道

CC 的 system prompt 由 3 层组装（`src/constants/prompts.ts`）：

| 层级 | 内容 | 缓存策略 |
|------|------|---------|
| 静态段 | 角色定义、工具规则、安全指南 | `cacheScope: global`，跨会话复用 |
| 动态段 | 环境信息(cwd/git/model)、记忆索引、MCP 指令 | `cacheScope: org` 或 null |
| 附件段 | 相关记忆(<=5)、Skill 列表、任务状态、LSP 诊断 | 每轮重新评估 |

**关键决策**：用 `DYNAMIC_BOUNDARY` 标记分隔静态/动态段。静态段内容不变 = cache hit = 不重新计费。MCP 指令标记为 `DANGEROUS_uncachedSystemPromptSection`，因服务器连接状态随时变化。

### 用户指令层级（`src/utils/claudeMd.ts`）

CLAUDE.md 按优先级叠加：企业策略级 > 用户级(~/.claude) > 项目级(.claude/)。支持 `@path` 递归包含（最大深度 5 层，循环引用检测）。

### 分项预算控制

| 组件 | 预算 | 超出策略 |
|------|------|---------|
| Skill 列表 | 上下文的 1%(~8000 字符) | 三级降级：完整/均分/只显示名字 |
| 单个 Skill 描述 | <=250 字符 | 截断 |
| MEMORY.md 索引 | <=200 行/<=25KB | 截断+警告 |
| 工具结果 | 每工具 maxResultSizeChars | 持久化到磁盘，返回摘要+路径 |

**工具结果预算**：不同工具有不同上限（FileRead=Infinity 防循环读取，Bash/MCP=100K）。超阈值则保存磁盘，返回前 1000 字符预览。

### 压缩触发决策（context-engineering 拥有触发，compact-system 拥有实现）

CC 在每轮 API 调用前检查 token 用量（`autoCompact.ts`）：

```
effectiveWindow = contextWindow - min(maxOutputTokens, 20_000)
autoCompactThreshold = effectiveWindow - 13_000
tokens >= autoCompactThreshold -> 触发压缩（委托 compact-system）
```

### 附件异步预取

每轮 API 调用前两条并发路径：(1) Sonnet 模型选最相关 <=5 个记忆文件；(2) 根据用户输入发现相关 Skill。用 AbortSignal 控制——API 调用先完成则取消预取。

### 消息标准化管道

原始消息经 7 步处理后才发 API：附件上浮 / 过滤 virtual+progress 消息 / 合并连续 user 消息 / 过滤 tool_reference / 移除出错媒体块 / 应用剥离目标 / 标准化消息。

---

## 3. Transferable Pattern — 多源组装 + 分层预算 + 压缩触发

> 框架无关的可迁移设计模式。

### 模式 1：多源 System Prompt 分层组装

```
system_prompt = assemble([
    StaticLayer(role, tool_rules, safety),      # 不变，可缓存
    DynamicLayer(env, memory_index, plugins),   # 每会话变
    EphemeralLayer(attachments, diagnostics),    # 每轮变
])
```

**核心原则**：按变化频率分层。不变的放前面利用 prompt cache；会变的放后面避免破坏缓存。

### 模式 2：分项 Token 预算

每个注入源独立设预算上限，超出时有明确的降级策略（截断/摘要/只保留标题）。防止单个超大注入源挤掉其他关键内容。

```
budget = {
    system_prompt: 30%,    # 固定，role + rules
    instructions: 10%,     # 用户指令文件
    tools: 5%,             # 工具 schema
    history: 45%,          # 对话历史
    attachments: 10%,      # 动态附件
}
```

### 模式 3：压缩触发（触发归 context，实现归 compact）

context-engineering 只负责两件事：(1) 每轮估算 token 用量；(2) 超过阈值时发出压缩信号。压缩算法的实现（裁剪/摘要/恢复）委托给 compact-system。

```
if estimate_tokens(assembled) >= token_budget.total * 0.8:
    compact_system.compress(messages, budget_remaining)
```

### 模式 4：指令文件优先级叠加

多个来源的指令按优先级合并，后者覆盖前者：

```
global_defaults < user_config < project_config < session_override
```

支持 `@path` 递归包含，需要深度限制和循环检测。

---

## 4. Minimal Portable Version

> 遵守共享契约接口：`context.assemble(history, tools, config) -> assembled_messages`

```python
from dataclasses import dataclass, field
from typing import Callable

@dataclass
class TokenBudget:
    total: int
    system: int      # system prompt 预算
    history: int     # 对话历史预算
    tools: int       # 工具 schema 预算
    attachments: int # 动态附件预算

@dataclass
class ContextConfig:
    window_size: int = 200_000
    max_output: int = 16_000
    compact_threshold: float = 0.8  # 触发压缩的比例

def get_token_budget(config: ContextConfig) -> TokenBudget:
    effective = config.window_size - min(config.max_output, 20_000)
    return TokenBudget(
        total=effective,
        system=int(effective * 0.30),
        history=int(effective * 0.45),
        tools=int(effective * 0.05),
        attachments=int(effective * 0.10),
    )

@dataclass
class ContextAssembler:
    static_sections: list[tuple[str, str]] = field(default_factory=list)
    dynamic_sections: list[tuple[str, Callable]] = field(default_factory=list)
    instructions: list[tuple[int, str]] = field(default_factory=list)

    def add_static(self, name: str, content: str):
        self.static_sections.append((name, content))

    def add_dynamic(self, name: str, factory: Callable[[], str | None]):
        self.dynamic_sections.append((name, factory))

    def add_instruction(self, priority: int, content: str):
        self.instructions.append((priority, content))

    def assemble(self, history: list[dict], tools: list[dict],
                 config: ContextConfig) -> list[dict]:
        budget = get_token_budget(config)
        # 1. Build system prompt: static + instructions + dynamic
        static = "

".join(c for _, c in self.static_sections)
        instr = "

".join(c for _, c in sorted(self.instructions))
        dynamic = "

".join(
            r for _, f in self.dynamic_sections if (r := f()) is not None
        )
        system = truncate(f"{static}

{instr}

{dynamic}", budget.system)
        # 2. Build messages, check compression trigger
        messages = [{"role": "system", "content": system}] + history
        used = estimate_tokens(messages)
        needs_compact = used >= budget.total * config.compact_threshold
        if needs_compact:
            for m in messages:
                m.setdefault("_meta", {})["needs_compact"] = True
        return messages

def truncate(text: str, max_tokens: int) -> str:
    limit = max_tokens * 4  # rough chars-to-tokens
    return text[:limit] if len(text) > limit else text

def estimate_tokens(messages: list[dict]) -> int:
    return sum(len(str(m.get("content", ""))) // 4 for m in messages)
```

---

## 5. Do Not Cargo-Cult

> CC 特有的实现选择，不应照搬到其他项目。

1. **不要照搬 DYNAMIC_BOUNDARY 标记**。这是 Anthropic API 的 prompt cache 分段机制。其他 provider（OpenAI/Azure）有不同的缓存 API，或者根本没有——用你的 provider 的原生缓存方式。

2. **不要照搬 CC 的 attachment 体系（记忆预取 + Skill 发现 + LSP 诊断注入）**。CC 的附件系统是为 IDE-agent 场景设计的。如果你的 Agent 不需要代码诊断或 Skill 发现，不要为了“完整”而引入这些。按实际信息源设计附件。

3. **不要照搬 MCP 服务器指令注入（DANGEROUS_uncachedSystemPromptSection）**。这是 CC 处理第三方 MCP 工具服务器安全风险的特定方案。如果你的工具集是固定的，不需要动态指令注入和“危险段”标记。

4. **不要照搬消息标准化管道的全部 7 步**。CC 的标准化是为了兼容多 provider（Bedrock 不允许连续 user 消息）和处理 UI-only 消息。如果你只对接一个 API 且没有 UI 层，大部分步骤不需要。

---

## 6. Adaptation Matrix

| 项目类型 | 建议保留 | 建议简化 | 注意事项 |
|----------|---------|---------|--------|
| **单进程 CLI Agent** | 静态/动态分层 + 分项预算 | 附件系统、消息标准化 | system prompt 通常不大，重点控制工具结果预算 |
| **对话式 Agent（类 CC）** | 完整 3 层组装 + 分项预算 + 压缩触发 | 可简化指令优先级（2 层够用） | 最接近 CC 原始设计 |
| **API 服务（无状态）** | 分项预算 | 压缩触发、缓存分层 | 每次请求独立，重点是控制输入大小 |
| **多 Agent 编排** | 每个 Agent 独立预算 | 跨 Agent 共享 system prompt | 子 Agent 窗口小，预算更紧 |

### Zero Magic 适配案例

```yaml
cc_feature: "5级渐进压缩触发"
cc_adaptations: "4级压缩->3级(trim_messages截断/LLM摘要/mem0联动)"
reason: >
  LangGraph 有内建 trim_messages，不需要 CC 的 microcompact。
  mem0 提供外部记忆持久化，替代 CC 的 session memory compact。
  最终：L1=trim_messages 截断旧消息，L2=LLM 摘要替换，L3=mem0 外部存储+检索。

cc_feature: "多源 system prompt 组装(3层+DYNAMIC_BOUNDARY)"
cc_adaptations: "2层(静态角色+动态环境)，无缓存分段"
reason: >
  Zero Magic 不使用 Anthropic prompt cache API，
  无需 DYNAMIC_BOUNDARY。静态段写死在代码中，动态段每轮拼接即可。

cc_feature: "分项预算控制(Skill列表/MEMORY索引/工具结果各有上限)"
cc_adaptations: "工具结果预算保留，其余简化为全局预算"
reason: >
  Zero Magic 没有 Skill 系统和 MEMORY 索引，
  只需控制工具结果大小（LangGraph tool node 中截断）。
```

---

## 7. Implementation Steps

请分析用户的 $ARGUMENTS 中指定的项目，然后：

1. **盘点上下文来源** — system prompt 由哪些部分组成（角色、规则、环境、用户指令等）
2. **划分静态/动态** — 不变的内容（角色定义）vs 会变的（环境、连接状态）
3. **计算 token 预算** — `effective = window - output_reserve`，按比例分配给 system/history/tools/attachments
4. **实现多源组装** — 用 ContextAssembler 模式：add_static / add_dynamic / add_instruction / assemble
5. **设置分项预算** — 每个注入源有 token 上限，超出有降级策略
6. **实现压缩触发** — 每轮检查 `tokens >= threshold`，超过则委托 compact-system 压缩
7. **实现指令文件加载** — 如需多级指令文件（全局/用户/项目），实现优先级叠加和 @include 解析
8. **验证** — 检查组装后的 prompt 是否超预算、压缩触发是否及时、降级策略是否生效

**反模式警告**：
- 不要把所有内容放在 system prompt 里——用附件按需注入
- 不要忘了工具结果预算——单个超大结果可以挤掉整个对话历史
- 不要缓存会变的内容——环境变了但缓存没更新 = 模型用错信息
- 不要让 context-engineering 做压缩——它只触发，compact-system 实现

---

## 8. Source Anchors

> CC 源码锚点，供深入阅读。

| 关注点 | 文件 | 关键符号 |
|--------|------|---------|
| System Prompt 组装 | `prompts.ts` | `getSystemPrompt()`, `SYSTEM_PROMPT_DYNAMIC_BOUNDARY` |
| 缓存分层 | `prompts.ts` | `cacheScope`, `DANGEROUS_uncachedSystemPromptSection()` |
| CLAUDE.md 加载 | `claudeMd.ts` | `getUserContext()`, `resolveIncludes()` |
| 分项预算-Skill | `skillDiscover.ts` | `SKILL_BUDGET_PERCENT`, 三级降级逻辑 |
| 分项预算-工具结果 | 各 Tool 定义 | `maxResultSizeChars`, `saveToDisk()` |
| 附件注入 | `attachments.ts` | `reorderAttachmentsForAPI()`, 附件类型定义 |
| 消息标准化 | `messageNormalization.ts` | 7 步 pipeline, `mergeConsecutiveUserMessages()` |
| 压缩触发阈值 | `autoCompact.ts` | `getEffectiveContextWindowSize()`, `getAutoCompactThreshold()` |
| 记忆预取 | `memoryPrefetch.ts` | `startRelevantMemoryPrefetch()`, AbortSignal |
| @include 解析 | `claudeMd.ts` | `resolveIncludes()`, 深度限制=5, 循环检测 |
