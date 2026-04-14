---
name: event-hook-system
description: "指导如何设计可扩展的事件 Hook 系统：声明式配置 + 5 种执行类型 + 决策合并 + 信任边界"
user-invocable: true
argument-hint: "<目标项目路径或模块名>"
---

# 事件 Hook 系统模式 (Event Hook System)

> 参考实现：Claude Code `src/utils/hooks.ts`（2900+ 行）
> — 27 种事件 × 5 种执行类型，声明式配置，并行执行 + 决策合并

## 核心思想

**Hook 不是回调函数，是声明式的"条件→动作"规则。** 用户用配置文件声明"当 X 事件发生时，执行 Y"，框架负责匹配、执行、合并结果。不需要写代码，改配置就能扩展行为。

---

## 一、CC 的 27 种 Hook 事件

按生命周期分组（你的项目不需要全部，从标 ★ 的开始）：

### 工具生命周期
| 事件 | 触发时机 | Matcher 字段 | 可拦截 |
|------|---------|-------------|--------|
| ★ **PreToolUse** | 工具执行前 | tool_name | 是（deny 阻止执行） |
| ★ **PostToolUse** | 工具执行后 | tool_name | 否（只通知） |
| **PostToolUseFailure** | 工具执行失败后 | tool_name | 否 |
| **PermissionRequest** | 弹出权限对话框时 | tool_name | 否 |
| **PermissionDenied** | 权限被拒绝时 | tool_name | 否 |

### 会话生命周期
| 事件 | 触发时机 | Matcher 字段 |
|------|---------|-------------|
| ★ **SessionStart** | 会话开始 | source (startup/resume/clear) |
| ★ **SessionEnd** | 会话结束 | reason (clear/logout/exit) |
| **Stop** | AI 响应即将结束 | — |
| **StopFailure** | API 错误导致中止 | error (rate_limit/auth_failed) |

### 上下文管理
| 事件 | 触发时机 | Matcher 字段 |
|------|---------|-------------|
| **PreCompact** | 上下文压缩前 | trigger (manual/auto) |
| **PostCompact** | 上下文压缩后 | trigger |
| **UserPromptSubmit** | 用户提交输入 | — |

### Agent 生命周期
| 事件 | 触发时机 | Matcher 字段 |
|------|---------|-------------|
| **SubagentStart** | 子 Agent 启动 | agent_type |
| **SubagentStop** | 子 Agent 结束 | agent_type |

### 系统事件
| 事件 | 触发时机 | Matcher 字段 |
|------|---------|-------------|
| **Setup** | 首次初始化/维护 | trigger (init/maintenance) |
| **ConfigChange** | 配置文件变更 | source |
| **CwdChanged** | 工作目录改变 | — |
| **FileChanged** | 监控文件变更 | filename |
| **InstructionsLoaded** | 指令文件加载 | load_reason |
| **WorktreeCreate/Remove** | 工作树创建/删除 | — |

---

## 二、Hook 规则格式（settings.json）

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "security-scan.sh",
            "timeout": 30,
            "if": "Write(*.env)"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "http",
            "url": "https://audit.internal/log",
            "timeout": 5,
            "headers": { "Authorization": "Bearer $API_TOKEN" },
            "allowedEnvVars": ["API_TOKEN"]
          }
        ]
      }
    ]
  }
}
```

### Hook 命令的 5 种执行类型

```typescript
type HookCommand =
  | { type: 'command'; command: string; shell?: 'bash' | 'powershell'; timeout?: number }
  | { type: 'prompt';  prompt: string; model?: string; timeout?: number }
  | { type: 'agent';   prompt: string; model?: string; timeout?: number }
  | { type: 'http';    url: string; headers?: Record<string, string>; timeout?: number }
  | { type: 'callback'; callback: Function; internal?: boolean }  // SDK only
```

| 类型 | 执行方式 | 延迟 | 适用场景 |
|------|---------|------|---------|
| **command** | Shell 子进程 | 毫秒级 | Lint、安全扫描、格式化 |
| **prompt** | LLM 推理（Haiku） | 秒级 | 内容审核、策略评估 |
| **agent** | 完整 Agent 执行 | 秒~分钟 | 复杂验证、多步检查 |
| **http** | HTTP POST | 毫秒级 | 审计日志、外部通知 |
| **callback** | 直接函数调用 | 微秒级 | 内部统计、状态追踪 |

---

## 三、匹配算法

```typescript
function matchesPattern(query: string, matcher: string): boolean {
  if (!matcher || matcher === '*') return true                    // 通配符
  if (/^[a-zA-Z0-9_|]+$/.test(matcher)) {                       // 简单模式
    if (matcher.includes('|'))
      return matcher.split('|').includes(query)                  // 管道分隔 OR
    return query === matcher                                      // 精确匹配
  }
  return new RegExp(matcher).test(query)                         // 正则匹配
}
```

**三种匹配语法**：
- `"Write"` — 精确匹配
- `"Write|Edit|Bash"` — OR 匹配
- `"^(Read|Grep)$"` — 正则匹配

**条件过滤**（`if` 字段）：
```json
{ "if": "Bash(git *)" }
// 只在 Bash 执行 git 命令时触发，其他 Bash 命令不触发
// 使用权限规则语法（与 allow/deny 规则相同）
```

---

## 四、Shell Hook 通信协议

### 输入：JSON 通过 stdin

```json
{
  "session_id": "sess_abc123",
  "transcript_path": "/home/user/.claude/transcripts/session.md",
  "cwd": "/home/user/project",
  "hook_event_name": "PreToolUse",
  "tool_name": "Write",
  "tool_input": {"path": "/src/main.ts", "content": "..."}
}
```

### 输出：Exit Code + 可选 JSON stdout

| Exit Code | 含义 | 行为 |
|-----------|------|------|
| **0** | 成功 | PreToolUse: 静默放行；PostToolUse: stdout 可选显示 |
| **2** | 阻断错误 | PreToolUse: **阻止工具执行**，stderr 发送给模型 |
| **其他** | 非阻断错误 | stderr 显示给用户，但操作继续 |

### 结构化 JSON 输出（可选，比 exit code 更强大）

```json
{
  "decision": "approve",
  "reason": "Security scan passed",
  "systemMessage": "提醒：此文件上次修改于 3 天前",
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse"
  }
}
```

```typescript
type HookJSONOutput = {
  continue?: boolean           // 默认 true
  suppressOutput?: boolean     // 静默输出
  decision?: 'approve' | 'block'
  reason?: string
  systemMessage?: string       // 注入到模型上下文
  stopReason?: string          // 中止 session 的原因
}
```

### 环境变量

```bash
CLAUDE_SESSION_ID          # 会话 ID
CLAUDE_TRANSCRIPT_PATH     # 会话记录路径
CLAUDE_CWD                 # 当前工作目录
CLAUDE_PROJECT_DIR         # 项目根目录（稳定，不随 worktree 变）
```

---

## 五、执行管道：匹配 → 执行 → 合并

```
事件触发
│
├─ 1. 信任检查
│  └─ shouldSkipHookDueToTrust() → 未信任？→ 跳过所有 Hook
│
├─ 2. 匹配
│  ├─ 从多个来源收集 Hook（settings/plugin/内置/session）
│  ├─ 按 matcher 过滤
│  ├─ 按 if 条件过滤
│  └─ 去重（相同 command + shell + if → 只保留一个）
│
├─ 3. 并行执行（所有匹配的 Hook 同时跑）
│  ├─ 每个 Hook 有独立超时（默认 10 分钟，SessionEnd 1.5 秒）
│  ├─ 每个 Hook 有独立 AbortController
│  └─ 进度消息实时 yield
│
└─ 4. 合并结果
   ├─ 权限决策：deny > ask > allow > passthrough
   │  └─ 任何一个 Hook deny → 最终 deny
   ├─ 输入修改：Last-Write-Wins（后执行的覆盖先执行的）
   ├─ 附加上下文：所有 Hook 的 systemMessage 拼接
   ├─ 监听路径：所有 Hook 的 watchPaths 合并
   └─ 阻断错误：任何 Hook 返回阻断 → 立即中止
```

### 关键：权限决策合并

```typescript
// 不是投票，是优先级覆盖
if (hook.permissionBehavior === 'deny') {
  permissionBehavior = 'deny'              // 一票否决，不可覆盖
} else if (hook.permissionBehavior === 'ask') {
  if (permissionBehavior !== 'deny')
    permissionBehavior = 'ask'             // 除非已有 deny
} else if (hook.permissionBehavior === 'allow') {
  if (!permissionBehavior)
    permissionBehavior = 'allow'           // 只在没人说话时生效
}
```

---

## 六、安全机制

### 1. 工作区信任

```typescript
// 所有 Hook 都需要工作区信任对话框确认
if (shouldSkipHookDueToTrust()) return  // 跳过所有 Hook，无错误
// SDK 模式下信任隐含（非交互式）
```

### 2. HTTP Hook 安全

- **URL 白名单**：只允许 `allowedHttpHookUrls` 中的 URL
- **SSRF 防护**：拒绝私有 IP 地址
- **环境变量白名单**：Header 中只能引用 `allowedEnvVars` 列出的变量
- **代理路由**：沙箱模式下通过代理转发

### 3. 托管 Hook 策略

```typescript
// 企业策略：只允许策略控制的 Hook
if (policySettings.allowManagedHooksOnly) {
  // 过滤掉所有用户/插件 Hook，只保留 managed 来源
}
```

---

## 七、你的项目应该怎么做

### 最小实现（3-5 个事件）

先从这些开始：

```typescript
type HookEvent = 'pre-action' | 'post-action' | 'session-start' | 'session-end' | 'error'

type HookRule = {
  event: HookEvent
  matcher?: string            // 通配符 / 精确 / 正则
  type: 'command' | 'http'
  command?: string
  url?: string
  timeout?: number            // 秒
  continueOnError?: boolean   // 失败是否继续（默认 false = fail-safe）
}
```

### 核心执行引擎

```typescript
class HookEngine {
  private rules: HookRule[] = []

  async execute(event: HookEvent, payload: Record<string, unknown>): Promise<HookResult> {
    const matched = this.rules.filter(r =>
      r.event === event && matchesPattern(payload.actionName, r.matcher)
    )
    if (matched.length === 0) return { decision: 'allow' }

    // 并行执行所有匹配的 Hook
    const results = await Promise.allSettled(
      matched.map(rule => this.runWithTimeout(rule, payload))
    )

    return this.mergeResults(results)
  }

  private async runWithTimeout(rule: HookRule, payload: unknown): Promise<HookResult> {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), (rule.timeout ?? 10) * 1000)
    try {
      if (rule.type === 'command')
        return await this.execShell(rule.command!, payload, controller.signal)
      if (rule.type === 'http')
        return await this.execHttp(rule.url!, payload, controller.signal)
    } catch (e) {
      if (rule.continueOnError) return { decision: 'allow' }
      return { decision: 'deny', reason: `Hook failed: ${e.message}` }  // fail-safe
    } finally {
      clearTimeout(timer)
    }
  }

  private execShell(cmd: string, payload: unknown, signal: AbortSignal): Promise<HookResult> {
    // stdin: JSON(payload), exit 0=allow, exit 2=deny
    const result = await exec(cmd, { input: JSON.stringify(payload), signal })
    if (result.exitCode === 0) return { decision: 'allow' }
    if (result.exitCode === 2) return { decision: 'deny', reason: result.stderr }
    return { decision: 'allow' }  // 非阻断错误
  }

  private mergeResults(results: PromiseSettledResult<HookResult>[]): HookResult {
    // deny > ask > allow（与权限系统一致）
    const resolved = results
      .filter(r => r.status === 'fulfilled')
      .map(r => r.value)

    if (resolved.some(r => r.decision === 'deny'))
      return resolved.find(r => r.decision === 'deny')!
    if (resolved.some(r => r.decision === 'ask'))
      return resolved.find(r => r.decision === 'ask')!
    return { decision: 'allow' }
  }
}
```

---

## 八、实施步骤

请分析用户的 $ARGUMENTS 中指定的项目，然后：

1. **识别扩展点**：用户最可能想在哪些地方插入自定义逻辑（操作前审核？操作后通知？）
2. **定义 3-5 个事件**：从 pre-action / post-action / error 开始
3. **选择通信协议**：Shell hook 用 stdin(JSON) + exit code，HTTP hook 用 POST + JSON response
4. **实现匹配 + 执行 + 合并**三步管道
5. **加超时**：每个 Hook 必须有超时，避免卡死
6. **选择失败策略**：审计类 Hook 用 `continueOnError: true`，安全类用 `false`（fail-safe）
7. **配置文件格式**：用 JSON/YAML，不要求用户写代码

**反模式警告**：
- 不要一开始就定义 27 种事件 — 从 3-5 个开始，按需增加
- 不要串行执行多个 Hook — 并行执行 + 合并结果
- 不要忘了超时 — 没有超时的 Hook 会卡死整个系统
- 不要让所有 Hook 失败都阻断操作 — 区分"必须通过"和"尽力通知"
- 不要忘了信任边界 — 远程/不可信来源的 Hook 需要额外限制
