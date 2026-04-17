---
name: multi-agent-design
description: "多 Agent 执行：5 条真实分支（async bg / sync fg / teammate / fork / remote）+ runAgent 查询循环生成器 + LocalAgentTask 后台生命周期"
user-invocable: false
argument-hint: "<目标项目路径或模块名>"
---

# 多 Agent 执行路径

> 参考实现：`src/tools/AgentTool/AgentTool.tsx`（5 条分支）、`src/tools/AgentTool/runAgent.ts`（查询循环生成器）、`src/tasks/LocalAgentTask/`（后台任务生命周期）、`src/utils/forkedAgent.ts`（fork 缓存共享）

## 源码事实

### 1. AgentTool.call() 有 5 条执行分支，不是 3 种"模式"

`AgentTool.tsx` 的 `call()` 方法中实际的 if/else 分支：

| 分支 | 触发条件 | 状态 | 返回值 |
|------|---------|------|--------|
| **A: Teammate 生成** | `teamName && name` | 真实子系统 | `teammate_spawned` |
| **B: Remote 隔离** | `isolation === 'remote'`（ant-only） | feature-gated | `remote_launched` |
| **C: Fork 隐式代理** | 不指定 subagent_type + `FORK_SUBAGENT` gate | 实验性 | 走异步后台路径 |
| **D: 异步后台** | `run_in_background=true` / coordinator / fork / proactive | **主路径** | `async_launched` + taskId |
| **E: 同步前台** | 以上都不满足 | 回退路径 | 直接返回结果 |

**主路径是 D（异步后台），不是 coordinator 或 teammate。** Coordinator 模式只是强制所有 Agent 走 D 路径（`isCoordinator → forceAsync`）。

### 2. runAgent.ts 是查询循环生成器——所有路径最终都走这里

`runAgent.ts` 不是"薄封装"——它是子 Agent 的完整运行时设置：

```
runAgent() 做的事（顺序）：
  1. initializeAgentMcpServers() → 连接 Agent 专属 MCP 服务器
  2. resolveAgentTools() → 按 agent.tools + disallowedTools 过滤工具池
  3. buildAgentSystemPrompt() → 构建子 Agent 的 system prompt
  4. 预加载 frontmatter 中声明的 skills
  5. 创建子 Agent 的 toolUseContext（权限模式、工作目录等）
  6. 进入 query() 循环 → yield 消息
  7. 清理 Agent 专属 MCP 连接
```

**所有分支最终都调用 `runAgent()`。** 分支 A-E 的差异在于：怎么准备参数、是否异步、怎么收集结果——但实际的 Agent 执行逻辑都在 `runAgent()` 里。

### 3. Fork 隔离与缓存共享：两层分离设计（源码验证）

**决策点 1：CacheSafeParams 的精确字段集（`forkedAgent.ts:57-68`）**

```
CacheSafeParams = {
  systemPrompt     // SystemPrompt 类型，必须与父 byte-identical
  userContext       // { [k: string]: string }，prepend 到 messages
  systemContext     // { [k: string]: string }，append 到 system prompt
  toolUseContext    // ToolUseContext，携带 tools + model + options
  forkContextMessages  // Message[]，父的完整对话历史
}
```

**判断条件**：API cache key = system prompt + tools + model + messages prefix + thinking config。CacheSafeParams 携带前 5 项；thinking config 从继承的 `toolUseContext.options.thinkingConfig` 推导。如果 fork 设了 `maxOutputTokens`，会 clamp `budget_tokens` → 破坏 cache。

**决策点 2：fork 时传了什么 vs 隔离了什么（`forkedAgent.ts:345-462` createSubagentContext）**

| 类别 | 字段 | 处理方式 | 设计理由 |
|------|------|---------|---------|
| **共享** | options（含 tools/model） | 直接传或 override | cache key 一致 |
| **共享** | getAppState | 包装后传入 | 加 shouldAvoidPermissionPrompts |
| **共享** | updateAttributionState | 直接共享 | 函数式 safe |
| **共享** | setAppStateForTasks | 始终共享到 root | 防 zombie 进程 |
| **隔离** | readFileState | `cloneFileStateCache()` | 防交叉污染 |
| **隔离** | abortController | `createChildAbortController()` | 父 abort 传播，子不影响父 |
| **隔离** | nestedMemoryAttachmentTriggers | `new Set()` | 每个子 Agent 独立发现 |
| **隔离** | contentReplacementState | `cloneContentReplacementState()` | 克隆（非新建）保持 cache hit |
| **隔离** | localDenialTracking | `createDenialTrackingState()` | 拒绝计数器独立累积 |
| **无操作** | setAppState（异步时） | `() => {}` | 异步 Agent 不写父状态 |
| **无操作** | setInProgressToolUseIDs | `() => {}` | 子不控制父 UI |
| **无操作** | addNotification/setToolJSX | `undefined` | 子无权操作父 UI |

**关键设计模式**：contentReplacementState 默认克隆而非新建——因为 cache-sharing fork 处理父消息中的 `tool_use_id`，新建 state 会做出不同的替换决策 → wire prefix 不同 → cache miss。

**决策点 3：runAgent.ts 中 fork vs 普通子 Agent 的分叉（`runAgent.ts:500-695`）**

```
if useExactTools:
  tools = availableTools（直接用，不过滤）
  thinkingConfig = 继承父的（cache key 一致）
  isNonInteractiveSession = 继承父的
  querySource 写入 options（防 autocompact 破坏递归防护）
else:
  tools = resolveAgentTools()（按 disallowedTools + isAsync 过滤）
  thinkingConfig = { type: 'disabled' }（控制 output token 成本）
  isNonInteractiveSession = isAsync ? true : 继承
```

**可迁移模式**：fork 路径用 `useExactTools=true` 保证与父 byte-identical；普通子 Agent 用 `resolveAgentTools()` 做最小权限过滤。两条路径共用同一个 `createSubagentContext()`。

### 3a. ALL_AGENT_DISALLOWED_TOOLS 的完整列表与设计理由（源码验证 `constants/tools.ts:36-112`）

**4 个常量集合，各有不同的约束目标：**

| 常量 | 工具列表 | 设计理由 |
|------|---------|---------|
| `ALL_AGENT_DISALLOWED_TOOLS` | TaskOutput, ExitPlanMode, EnterPlanMode, Agent（非 ant 用户）, AskUserQuestion, TaskStop, Workflow（若 feature on） | **递归防护 + 主线程抽象保护** |
| `ASYNC_AGENT_ALLOWED_TOOLS` | Read, WebSearch, TodoWrite, Grep, WebFetch, Glob, Shell, Edit, Write, NotebookEdit, Skill, SyntheticOutput, ToolSearch, EnterWorktree, ExitWorktree | **异步 Agent 白名单**：只给文件操作 + 搜索 + shell |
| `IN_PROCESS_TEAMMATE_ALLOWED_TOOLS` | TaskCreate/Get/List/Update, SendMessage, Cron*（若 feature on） | **进程内 Teammate 额外权限**：任务管理 + 通信 |
| `COORDINATOR_MODE_ALLOWED_TOOLS` | Agent, TaskStop, SendMessage, SyntheticOutput | **Coordinator 极简工具集**：只能调度 + 通信 |

**决策点**：Agent 工具（AgentTool）对 `ant` 用户条件放开（`process.env.USER_TYPE === 'ant'`），允许嵌套 Agent。外部用户一律禁止 → 硬性递归防护。

**被明确注释为"以后再开"的工具**（`tools.ts:99-101`）：MCPTool, ListMcpResourcesTool, ReadMcpResourceTool — 因为 MCP 连接管理与子 Agent 的生命周期未对齐。

### 3b. canUseTool 回调如何实现最小权限（源码验证）

**决策点**：`canUseTool` 是运行时的 per-call 权限门控，独立于 `disallowedTools` 的编译期过滤。两者叠加形成双重约束。

**autoDream 的 canUseTool（`extractMemories.ts:171-222`）——最严格的只读 + 定向写入**：

```
判断链（顺序评估，首个匹配返回）：
  1. REPL → allow（REPL 内部递归调用 canUseTool 检查真实操作）
  2. Read/Grep/Glob → allow（天然只读）
  3. Bash → 仅当 tool.isReadOnly(input) 为 true 时 allow
     拒绝消息："Only read-only shell commands are permitted"
  4. Edit/Write → 仅当 file_path 在 memoryDir 下时 allow
     判断函数：isAutoMemPath(filePath)
  5. 其他一切 → deny
```

**关键设计**：工具列表不变（保持与父 byte-identical → cache key 一致），权限通过 `canUseTool` 回调在运行时软约束。改工具列表会破坏 cache。

**onMessage 回调的两种进度监控模式（源码对比）**：

| 场景 | 实现 | 追踪粒度 |
|------|------|---------|
| DreamTask（`autoDream.ts:281-313`） | `makeDreamProgressWatcher` | 每个 assistant turn：提取 text + 统计 tool_use 数 + 收集 Edit/Write 的 file_path |
| AgentTool 异步（`LocalAgentTask`） | `updateAsyncAgentProgress` | 每条消息：toolUseCount + latestInputTokens + cumulativeOutputTokens + recentActivities[5] |

**可迁移模式**：`onMessage` 是 fork/子 Agent 唯一的进度通信渠道。不同场景构造不同的 watcher 函数，但都是 `(msg: Message) => void` 签名。

### 4. Coordinator 是提示注入层，不是执行子系统

`src/coordinator/coordinatorMode.ts` 只有 **1 个文件**，做 3 件事：

```
isCoordinatorMode()           → feature gate + 环境变量检查
getCoordinatorUserContext()   → 注入 worker 能力列表到用户上下文
getCoordinatorSystemPrompt()  → 421 行静态提示文本
```

**没有 coordinator 特定的执行逻辑。** 当 coordinator 模式开启：
- 所有 Agent 强制异步（`isCoordinator → forceAsync`）
- system prompt 被替换为编排指令
- 仅此而已——实际的异步执行走的是 `Branch D → LocalAgentTask` 的通用路径

### 5. LocalAgentTask 是后台 Agent 的真实生命周期管理器

```
registerAsyncAgent()
  ↓ 创建 LocalAgentTaskState
runAsyncAgentLifecycle()
  ↓ 运行 agent iterator
  ↓ updateAsyncAgentProgress() 逐条更新进度
  ↓ 捕获 AbortError → killAsyncAgent()
enqueueAgentNotification()
  ↓ 生成 XML task-notification 
  ↓ 通过 messageQueue 发送到 Coordinator
```

**Task 状态机**：`running → completed | failed | killed`

**Progress 追踪**：
```typescript
type ProgressTracker = {
  toolUseCount: number
  latestInputTokens: number
  cumulativeOutputTokens: number
  recentActivities: ToolActivity[]  // 最近 5 个工具调用
}
```

### 6. Task Notification 是结构化 XML，不是自由文本

```xml
<!-- src/tasks/LocalAgentTask/ — 模板化生成 -->
<task-notification>
  <task-id>{agentId}</task-id>
  <tool_use_id>{toolUseId}</tool_use_id>
  <output_file>{outputPath}</output_file>
  <status>completed|failed|killed</status>
  <summary>{一句话摘要}</summary>
  <result>{Agent 最终文本输出}</result>
  <usage>
    <total_tokens>{N}</total_tokens>
    <tool_uses>{N}</tool_uses>
    <duration_ms>{N}</duration_ms>
  </usage>
  <worktree>{path} on branch {branch}</worktree>
</task-notification>
```

**通过 messageQueue 投递**，Coordinator 从消息流中解析 XML 标签。

### 7. Teammate 是真实子系统但是次要路径

Teammate 有两种后端：
- **tmux**（主要）：`spawnTeammate() → detectAndGetBackend() → tmux pane`
- **进程内**（实验性）：`isInProcessEnabled() → AsyncLocalStorage 隔离`

进程内 teammate 用 `AsyncLocalStorage` 给每个 teammate 独立上下文：

```typescript
type TeammateContext = {
  agentId: string
  agentName: string      // "researcher"
  teamName: string       // "team1"
  planModeRequired: boolean
  abortController: AbortController
}

teammateContextStorage.run(context, () => {
  // 这里的代码看到的是自己的 context
})
```

**通信**：teammate 之间通过 `writeToMailbox()` 写文件 + `SendMessage` 工具发消息。

---

## 可迁移设计

### 异步后台 Agent 是默认路径

你的项目应该**默认异步**，同步是特例：

```python
async def dispatch_agent(task, context, background=True):
    if background:
        task_handle = create_background_task(task, context)
        return {"status": "launched", "task_id": task_handle.id}
    else:
        return await run_agent_sync(task, context)
```

### fork 的 cache 共享模式（源码验证版）

不只是"复用前缀"——需要保证 5 个维度全部 byte-identical：

```python
@dataclass
class CacheSafeParams:
    system_prompt: str           # 不能改
    user_context: dict           # 不能改
    system_context: dict         # 不能改
    tool_use_context: object     # tools + model 不能改
    fork_context_messages: list  # 父对话历史原样传入

def fork_agent(parent_params: CacheSafeParams, directive: str):
    """fork 时：CacheSafeParams 共享，其他全部隔离"""
    isolated_context = create_subagent_context(
        parent_params.tool_use_context,
        # 隔离：readFileState 克隆、abortController 新建、denial 计数器独立
        # 共享：options（含 tools）、attribution state
    )
    messages = [*parent_params.fork_context_messages, user_msg(directive)]
    return run_forked_agent(messages, parent_params, isolated_context)
```

**关键约束**：`maxOutputTokens` 会 clamp `budget_tokens` → 破坏 thinking config → 破坏 cache。只在不关心 cache 的场景设（如 compact summary）。

### canUseTool 运行时权限门控模式（源码验证版）

```python
def create_scoped_can_use_tool(allowed_write_dir: str):
    """不改工具列表（保 cache），用运行时回调做软约束"""
    def can_use_tool(tool, input):
        if tool.name in ['Read', 'Grep', 'Glob']:
            return allow()  # 天然只读，放行
        if tool.name == 'Bash':
            return allow() if tool.is_read_only(input) else deny("只允许只读命令")
        if tool.name in ['Edit', 'Write']:
            return allow() if input['file_path'].startswith(allowed_write_dir) else deny()
        return deny("不在白名单中")
    return can_use_tool
```

### fork 清理链（源码验证版 `runAgent.ts:816-858`）

```
finally 块必须清理 8 项资源（顺序无关但全部必须执行）：
  1. MCP 服务器连接 → mcpCleanup()（只清理 Agent 新建的，不清理共享的）
  2. 会话级 hooks → clearSessionHooks(agentId)
  3. Prompt cache 追踪 → cleanupAgentTracking(agentId)
  4. 文件状态缓存 → readFileState.clear()
  5. Fork 上下文消息 → initialMessages.length = 0（释放内存）
  6. Perfetto 注册 → unregisterPerfettoAgent(agentId)
  7. Todo 条目 → 从 AppState.todos 删除 agentId 键（防 whale session 泄露）
  8. 后台 Bash 任务 → killShellTasksForAgent()（防 PPID=1 zombie）
```

**可迁移模式**：子 Agent 的 finally 清理必须覆盖所有 fork 时分配的资源。CC 里每个清理步骤都有对应的 bug 注释说明为什么必须做。

### Coordinator 可以只是 prompt + 强制异步

不需要为 coordinator 写专门的执行引擎——只需要：
1. 替换 system prompt 为编排指令
2. 强制所有 Agent 异步
3. 让 Agent 通过通知消息报告结果

### task-notification 用结构化格式

```python
@dataclass
class TaskNotification:
    task_id: str
    status: str  # 'completed' | 'failed' | 'killed'
    summary: str
    result: str | None
    usage: dict  # {tokens, tool_uses, duration_ms}

    def to_xml(self) -> str:
        return f"""<task-notification>
<task-id>{self.task_id}</task-id>
<status>{self.status}</status>
<summary>{self.summary}</summary>
<result>{self.result or ''}</result>
</task-notification>"""
```

---

## 角色分层：Planner / Generator / Evaluator

> 来源：Anthropic "Effective harnesses for long-running agents"。**短任务用单 Agent 够用；任务跨多个 sprint、需要跨会话衔接时，三角色分工显著优于"让一个 Agent 自己规划自己执行自己自评"**。

### 三个角色的职责边界

| 角色 | 只做 | 绝不做 | 失效模式 |
|------|------|--------|---------|
| **Planner** | 把 1-4 句需求扩展为完整规格（feature_list.json + 验收标准 + 依赖顺序） | 不执行、不写实现代码 | 过度设计 / 提前定死实现 |
| **Generator** | one-feature-at-a-time 实现，sprint 末做客观自检（跑测试、看 diff） | 不自评质量、不决定是否通过 | self-eval blind spot（见下） |
| **Evaluator** | 独立 context 读 Generator 产出 + 用 Playwright/curl 端到端验证，打分并给出可执行反馈 | 不修改代码、不替 Generator 决定下一步 | 过于宽容 → 需要校准为"怀疑主义者" |

**关键不对称**：
> Calibrating an independent evaluator to be skeptical proved easier than getting generators to critique their own work.
> — Anthropic, 同一引用

直白说：**让评估 agent 挑刺**比**让生成 agent 自己承认错**容易——这是设计三角色而非两角色的根本理由。

### Sprint Contract：三角色之间的接口

Generator 和 Evaluator 开始工作前，先用结构化文件签订一次性契约：

```json
// sprint-contract.json（Planner 产出，双方读）
{
  "sprint_id": "S-07",
  "goal": "用户可在 /settings 切换主题，刷新后保持",
  "scope_in": ["theme toggle UI", "localStorage 持久化", "初始加载读取"],
  "scope_out": ["账号级同步", "系统偏好检测"],
  "exit_criteria": [
    "Playwright: 切换主题后刷新仍保持",
    "新测试全绿 + 旧测试无回归",
    "bundle 大小增量 < 5KB"
  ],
  "deadline_sprints": 1,
  "escalate_if": ["scope 超出", "exit_criteria 某项无法达成"]
}
```

**硬规则**：
- 未写入 `exit_criteria` 的验证维度，Evaluator 不要主动扣分（防范围蠕变）
- `scope_out` 里的东西，Generator 碰了就是违约（Evaluator 应直接打回，不要"顺便改了也挺好"）
- `escalate_if` 命中时，Generator 和 Evaluator 都停手，回到 Planner 重新签订

### 工件交接的目录结构

```
project/
├── sprint-contract.json     # Planner 写，双方读
├── claude-progress.txt      # Generator 叙述性追加（append-only）
├── feature_list.json        # Planner 初始化，Generator 更新状态
├── evaluator-report.md      # Evaluator 每 sprint 末产出
└── .sprint-lock             # Evaluator 通过才清除，未通过 Generator 不进下一 sprint
```

**为什么是 JSON 不是 Markdown**：模型编辑 Markdown 会顺手改格式；改 JSON 必须保持结构合法 → 跨 sprint 追踪稳定。

### 跨 Sprint 启动仪式：新 Generator 如何醒来

> 来源：Anthropic "Effective harnesses for long-running agents" 明确列出的 5 步启动序列。
>
> 长任务跨多个 sprint 时，**每个 sprint 开始的 Generator 是一个新的 Agent 实例**，没有前一 sprint 的 context。工件文件是它唯一的记忆源。不固定启动仪式，Generator 会跳过关键状态直接开工 → 重复已完成工作、破坏 scope 边界、漏掉 escalate 点。

**Sprint 开始时 Generator 必须执行的 5 步（顺序不可换）**：

```
1. pwd                              # 确认自己在哪——防止启动路径漂移
2. git log -20 --oneline            # 近 20 次提交——上个 sprint 实际改了什么
3. cat claude-progress.txt | tail   # 上个 sprint 最后的叙述状态
4. jq '.' feature_list.json         # 结构化任务清单——done / in_progress / pending
5. bash init.sh                     # 恢复运行环境（deps / 启动服务 / 环境变量）
```

**每步揭示什么**：
| 步骤 | 揭示 | 若跳过的后果 |
|------|------|------------|
| pwd | 工作目录锚点 | 在错误路径里 grep，得到空结果后瞎猜 |
| git log | 代码侧真实状态（不会说谎） | 信任 progress 叙述，但 git 已回滚了——重复做已撤销的改动 |
| progress | 人类可读的"为什么"链 | 只看代码不知道上个 sprint 为什么中断 |
| feature_list | 结构化的待办 | 做已完成的 feature / 漏掉阻塞依赖 |
| init.sh | 环境恢复 | 端口占用 / 依赖缺失 / 环境变量丢失，跑测试全错 |

**工件冲突时的决策规则**（git 是唯一仲裁者）：
```
progress 说"实现了 X" + git log 里没有 X 相关 commit
  → 信 git：上个 Generator 叙述了但没提交，或 commit 被回滚
  → 更新 feature_list 把 X 标回 in_progress
  → 在 progress 追加 "[reconciled: X not in git, reopened]"

feature_list 说"X done" + 测试证明 X 坏了
  → 信测试：feature_list 的 done 标记不等于质量验收
  → 这是 Evaluator 的工作域，Generator 不自己翻案，升级 escalate
```

### One-Feature-at-a-Time：Generator 的 scope 防蠕变规则

> 同样来自 Anthropic。Generator 在 sprint 中**只实现 feature_list 里 in_progress 状态的那一个**，不管同时看到其他 pending 项多诱人。

```json
// feature_list.json 状态流转
"status": "pending" → "in_progress" → "ready_for_review"
                                        ↓
                              Evaluator 判定 → "done" | "rework"
```

**规则**：
- 同一时刻最多 1 个 `in_progress`（Planner 初始化时保证）
- Generator 完成后改为 `ready_for_review`，**不自己改成 `done`**（这是 Evaluator 的职责）
- 如果实现过程中发现必须动到其他 pending feature → ESCALATE 回 Planner，不顺手做

**为什么**：一次一个 feature 让 diff 小、Evaluator 易读、回滚成本低。Generator 倾向"顺便也改了相关的"——这是 scope creep 的第一步，sprint contract 的 `scope_in` 就是为了约束它。

### Sprint 末的自评边界（降级不可替代）

Generator 在提交给 Evaluator 前必须做**客观**自检（跑测试、跑 linter、看 diff 规模），但**不做主观判断**（"这个实现优雅不优雅"）：

```
Generator 的 sprint 末输出：
  ✓ 测试：通过 12/12（客观）
  ✓ Lint：0 warnings（客观）
  ✓ Diff 大小：+147 -23（客观）
  ✓ 覆盖 exit_criteria：1/1 已测（客观）
  ✗ 不写："我觉得实现得很好"
  ✗ 不写："这个方案应该没问题"
```

**原因**：主观判断命中 self-eval blind spot（见 `agent-reflection` §7）。客观指标是 Evaluator 决策的输入，主观夸奖只会污染判断。

### 何时**不**用三角色

- **单 sprint、目标清晰的改动**：一个 Agent 直接做完，加三角色只是开销
- **探索性调研**：Planner 无法预先写 exit_criteria（不知道答案长什么样），这时候用 gather→act→verify 单 Agent 循环
- **硬实时交互**：三角色协作有延迟（sprint contract + eval 回合），用户等不起
- **团队工作流已有人类 reviewer**：Evaluator 角色由人担任，Generator 是 Agent 就够

### 反模式

- 不要让 Generator 同时扮演 Evaluator（self-eval blind spot 的成因，见 `agent-reflection`）
- 不要让 Evaluator 直接改代码（失去独立判断视角，降级为"另一个 Generator"）
- 不要把 sprint_contract 写成自由文本——结构化字段才能被程序化校验 scope 是否溢出
- 不要跳过 `exit_criteria` 直接开工（Generator 会把"看起来 OK"当通过）

---

## 不要照抄的实现细节

- CC 的 `Branch E` 有复杂的 mid-turn backgrounding（同步执行中途转异步）——你的项目大概率不需要
- `Remote isolation`（Branch B）是 ANT-only 的 CCR 环境，外部构建中已被 DCE
- tmux teammate 后端依赖 tmux 可用性，不跨平台
- `CacheSafeParams` 的 5 个精确字段（systemPrompt/userContext/systemContext/toolUseContext/forkContextMessages）是 Anthropic API cache key 结构耦合的。你的 LLM provider 的 cache key 结构可能不同——抽象"保持前缀一致"的意图，不要照抄字段名
- `contentReplacementState` 的克隆 vs 新建决策与 CC 的 tool_use_id 替换机制耦合——只抽象"子 Agent 的替换决策必须与父一致"的原则
- `createAutoMemCanUseTool` 通过 `tool.isReadOnly(input)` 判断 Bash 是否只读——这是 CC 的 BashTool 特有方法，其他框架需要自己实现只读检测

---

## 反模式

- 不要把 coordinator 写成重型执行引擎——CC 里它只是 1 个文件 + 421 行提示文本
- 不要默认同步——异步后台才是主路径，同步是回退
- 不要跳过 task-notification 的结构化——自由文本的完成通知无法被程序化解析
- 不要在 fork 子 Agent 里改 thinking config / model / maxOutputTokens——会破坏 cache 共享（源码证据：`runAgent.ts:680-684`，fork 路径强制 `thinkingConfig: useExactTools ? 继承父的 : disabled`）
- 不要让 canUseTool 和 disallowedTools 做同一件事——CC 的设计是两层叠加：disallowedTools 在编译期移除工具定义（影响 cache key），canUseTool 在运行时软拒绝（不影响 cache key）。二者目的不同，不可合并
