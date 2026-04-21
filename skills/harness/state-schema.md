# Harness 状态文件 Schema

文件路径：`{project}/.claude/harness-state.json`

harness 每次 REPORT 结束后更新此文件。下次 `/harness` 启动时先读取，避免重复探测。

## Schema

```json
{
  "version": 1,
  "project": {
    "language": "python",
    "language_version": "3.12",
    "frameworks": ["fastapi", "sqlalchemy"],
    "package_manager": "uv",
    "source_root": "src/my_agent"
  },
  "constraints": [
    "token 不能明文存储",
    "必须支持飞书和钉钉双平台",
    "团队 3 人，Python 中级水平"
  ],
  "architecture_decisions": [
    {
      "module": "memory",
      "decision": "用 PostgreSQL 而非文件系统存储记忆",
      "reason": "项目已有 PG 实例，团队熟悉 SQLAlchemy",
      "date": "2026-04-02"
    }
  ],
  "modules": {
    "core/loop": { "status": "designed", "skill_used": "agent-loop", "files": ["src/my_agent/core/loop.py"] },
    "tools/base": { "status": "implemented", "skill_used": "unified-tool-interface", "files": ["src/my_agent/tools/base.py", "src/my_agent/tools/registry.py"] },
    "permissions": { "status": "not_started" },
    "memory": { "status": "not_started" }
  },
  "current_stage": "stage-0-contracts",
  "completed_stages": [],
  "last_execution": {
    "date": "2026-04-02T15:30:00Z",
    "plan_summary": "阶段 1：设计主循环 + 工具接口",
    "agents_dispatched": 3,
    "results": [
      { "agent": "worker-1", "task": "设计主循环", "status": "completed" },
      { "agent": "worker-2", "task": "设计工具接口", "status": "completed" },
      { "agent": "worker-3", "task": "设计 API 客户端", "status": "completed" }
    ]
  },
  "open_risks": [
    "飞书 API 的 webhook 回调格式未确认"
  ],

  "transition": {
    "reason": "next_stage",
    "from_phase": "EXECUTE",
    "attempt": 1
  },

  "recovery_flags": {
    "has_attempted_plan_revision": false,
    "has_attempted_scope_reduction": false,
    "worker_retry_count": 0,
    "max_worker_retries": 3
  },

  "denial_tracking": {
    "consecutive_failures": 0,
    "total_failures": 0,
    "last_failure_reason": null
  },

  "learnings": [
    {
      "date": "2026-04-02",
      "stage": "stage-1-minimal-loop",
      "type": "success",
      "insight": "该项目的 Flask 框架有内置中间件，不需要从零设计",
      "trace_ref": "harness-lab/traces/2026-04-02-stage-1/worker-2-result.md"
    }
  ],

  "cc_adaptations": [
    {
      "skill": "auth-identity",
      "cc_pattern": "macOS Keychain 集成",
      "adapted_to": "环境变量 + .env 文件",
      "reason": "目标项目是 Linux 服务器，无 Keychain"
    }
  ],

  "active_openspec_changes": [
    {
      "name": "add-fengshui-demo-workbench",
      "schema": "spec-driven",
      "status": "active",
      "artifact_dir": "openspec/changes/add-fengshui-demo-workbench",
      "phase_reports_dir": "docs/audit/",
      "last_report": "docs/audit/2026-04-21_archive_ready_final.md"
    }
  ]
}
```

## 字段说明

### modules 状态值

| status | 含义 |
|--------|------|
| `not_started` | 未开始 |
| `designed` | 有设计方案，未编码 |
| `implemented` | 已编码 |
| `audited` | 已审计通过 |

### current_stage 有效值（必须与 stage-roadmap.md 一致）

| 值 | 对应路线图阶段 |
|----|---------------|
| `stage-0-contracts` | 阶段 0：基础契约 |
| `stage-1-minimal-loop` | 阶段 1：最小循环 |
| `stage-2-security` | 阶段 2：安全与资源控制 |
| `stage-3-long-session` | 阶段 3：长会话支持 |
| `stage-4-memory` | 阶段 4：跨会话与记忆 |
| `stage-5-extensibility` | 阶段 5：可扩展性 |
| `stage-6-multi-agent` | 阶段 6：多 Agent 编排 |
| `stage-7-production` | 阶段 7：生产化 |
| `stage-8-enterprise` | 阶段 8：企业治理 |

### 更新规则

- **SCAN 阶段**：如果状态文件存在，读取它作为基础，只做增量代码探测验证
- **PLAN 阶段**：不修改状态文件（计划还未执行）
- **REPORT 阶段**：更新 `modules.{name}.status`、`completed_stages`（阶段内所有模块完成时追加）、`current_stage`、`last_execution`
- **用户提供新约束时**：追加到 constraints 数组
- **做出架构决策时**：追加到 architecture_decisions 数组

### transition 字段

记录上一次阶段跳转的原因，防止恢复路径无限循环。

| reason | 含义 |
|--------|------|
| `next_stage` | 正常进入下一阶段 |
| `worker_retry` | Worker 失败，补充上下文重试 |
| `scope_reduction` | Worker 失败，缩小任务范围重试 |
| `plan_revision` | 多次失败，修订计划 |
| `partial_completion` | 部分 Worker 成功，重新调度失败的 |

> 来源：CC `query.ts` 的 transition.reason 防螺旋机制。参见 `transition-patterns.md` 模式 1。

### recovery_flags 字段

跨轮恢复状态追踪。防止同一恢复路径重复执行。

| 字段 | 含义 | 重置时机 |
|------|------|---------|
| `has_attempted_plan_revision` | 是否已尝试修订计划 | 进入新阶段时重置为 false |
| `has_attempted_scope_reduction` | 是否已尝试缩小范围 | 进入新阶段时重置为 false |
| `worker_retry_count` | Worker 重试次数 | 进入新阶段时重置为 0 |
| `max_worker_retries` | 最大重试次数 | 不重置（用户可调） |

**关键约束**：`plan_revision` 的 continue 中，`worker_retry_count` 不重置为 0。原因同 CC 的 `stop_hook_blocking` 设计——修订计划不会解决 Worker 内部的重复错误。

### denial_tracking 字段（对齐 CC `denialTracking.ts` 门控模式）

Worker 连续失败计数。3 次后触发自动降级。

| consecutive_failures | 行为 |
|---------------------|------|
| 0-2 | 正常执行 |
| >= 3 | 自动降级（设计→仅骨架，编码→仅接口，审计→仅 top 3） |

失败时 `consecutive_failures++`，成功时重置为 0。

> **源码对齐**：CC 的 `denialTracking.ts` 用 `maxConsecutive: 3` + `maxTotal: 20` 双阈值。harness 只用 consecutive（总量阈值对 harness 不适用——每轮只调度几个 Worker，不会累积到 20）。
> CC 的 `autoCompact.ts:70` 也用了同样的断路器模式（`MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES = 3`）。这是 CC 的通用模式：连续 N 次失败 → 停止重试。

### learnings 字段（对齐 CC 的 extractMemories 后台提取模式）

记录每轮执行中的非显而易见的经验。下次 SCAN 时读取，避免重复犯错。

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| date | string | 是 | YYYY-MM-DD |
| stage | string | 是 | 所属阶段 |
| type | "success" \| "failure" | 是 | 经验类型 |
| insight | string | 是 | 非显而易见的经验描述 |
| trace_ref | string | 是（M0） | 指向证据来源的相对路径，如 `harness-lab/traces/2026-04-02-stage-1/worker-2-result.md`。learnings 是 trace 的摘要索引，没有 trace_ref 的 learning 是不完整的。对于 M0 之前创建的旧 learnings，trace_ref 可为 null。 |

> **源码对齐**：CC 的 `extractMemories` 从对话中后台提取记忆写入文件；harness 的 learnings 从 Worker 执行结果中提取经验写入 state。
> 提取条件对齐 CC 的 `shouldExtractMemory()` 模式：不是每轮都提取——只在 Worker 结果包含"非显而易见的信息"时才记录。

### cc_adaptations 字段（对齐 CC 的记忆类型系统 — "reference" 型记忆）

记录 CC-bound skill 在目标项目中的迁移决策。下次使用同一 skill 时注入 Worker prompt 作为上下文。

> **源码对齐**：CC 的记忆系统有 4 种类型（user/feedback/project/reference）。cc_adaptations 最接近 "reference" 型——记录"去哪里找到什么"的指针，但面向的是 CC → 目标项目的迁移差异而非外部系统链接。

### smoke_tests 字段（可选，用于运行时不变式验证）

编码阶段完成后，verification-protocol.md 的"必跑 smoke test"会从此字段读取项目自定义的验证命令。

```json
"smoke_tests": [
  {
    "name": "state_serialization",
    "command": "python -m pytest tests/test_state_serialization.py -x -q",
    "timeout": 30,
    "invariant": "LangGraph state 字段必须可被 msgpack 序列化"
  },
  {
    "name": "graph_build",
    "command": "python -c \"from src.graph.builder import build_graph; build_graph()\"",
    "timeout": 30,
    "invariant": "图节点接口兼容"
  },
  {
    "name": "process_health",
    "command": "curl -sf http://localhost:8001/health",
    "timeout": 60,
    "invariant": "Runtime 进程启动正常"
  }
]
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | string | 测试名称（Report 中引用） |
| `command` | string | Bash 命令（Coordinator 用 Bash 工具执行） |
| `timeout` | number | 超时秒数（超时视为失败） |
| `invariant` | string | 对应的 constraints 中的不变式描述 |

此字段可选。不存在时，Coordinator 按 verification-protocol.md 的默认 smoke test 表执行；都没有时，在 Report 中标注"⚠️ 缺少运行时验证"。

---

### active_openspec_changes 字段（可选 · [speculation] 实验性只读可见性元数据）

> 来源：`WORKFLOW-TRACKS.md` 决策指南 + `OPENSPEC-HARNESS-COEXISTENCE-ANALYSIS.md` Action 1（Codex 审计 agentId `a5dab88543cce4ae9`，标为 `[speculation]` 实验性建议）。
>
> **[speculation] 待验证状态**：此字段的设计基于 1 个项目（Zero Magic `feature/fengshui-mvp`）的单次观察，属 Codex 审计 §4 Action 1 的 `[speculation]` 建议之直接落地。**接口尚未稳定**；至少需要第二个外部 spec 系统验证后才会固定字段定义与写入路径。

**设计意图**：让 harness SCAN 阶段知道项目里是否有 OpenSpec change 正在推进，**避免 harness Stage 推进撞上 OpenSpec change 的交付节奏**。纯只读**可见性元数据**——不是第二个阶段机，不替代 `current_stage`，也不由 harness 写入/更新 `openspec/changes/*/tasks.md` / `proposal.md` / `spec.md`。

**字段结构**：
```json
"active_openspec_changes": [
  {
    "name": "<change-name>",
    "schema": "spec-driven",
    "status": "active | archived",
    "artifact_dir": "openspec/changes/<change-name>",
    "phase_reports_dir": "docs/audit/",
    "last_report": "docs/audit/<最近一份 phase/archive 报告>"
  }
]
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | string | OpenSpec change 名称（与 `openspec list` 输出对齐）|
| `schema` | string | OpenSpec 内部的 schema 类型，目前观察到的唯一值是 `spec-driven`（其他 schema 未验证）|
| `status` | enum | `active`（change 未归档）/ `archived`（已 `/opsx:archive`，entries 暂留到下次 scan 清理）|
| `artifact_dir` | string | change 的 proposal/tasks/design 目录（相对项目根路径）|
| `phase_reports_dir` | string | Phase 报告存放目录（通常是 `docs/audit/`）|
| `last_report` | string | 最近一份 Phase/Archive 报告路径（给 SCAN 展示上下文）|

**使用规则**：

1. **读取**：harness SCAN 阶段读取此字段，若存在 `status=active` 条目，在 "上次进展摘要" 之后输出一行陈述："检测到 {N} 个活跃 OpenSpec change：{name} 在 {last_report}；该 change 的交付范围可能与本轮规划存在重叠"——**只读事实陈述，不含祈使语气、不给行动指令**
2. **写入归属**（[speculation] 未在 Codex §4 原议中定义，暂记为开放问题）：Codex §4 Action 1 只授权此字段作为可见性元数据存在，**未明确谁负责写入**。当前未授权 Coordinator 在 SCAN 阶段自动探测并写入此字段；用户可手动维护，或由未来的 OpenSpec↔harness 桥接机制写入。harness **禁止**写 `openspec/changes/*/tasks.md` / `proposal.md` / `spec.md`——那些属于 `openspec-apply-change` / `openspec-archive-change` skill 的写权限
3. **非硬约束**：此字段缺失或为空不影响 harness 正常运行。只有当字段存在且含 `active` 条目时才触发 SCAN 提示

**此字段不负责的事**：
- ❌ 不是 M2 candidate 对比池的数据源（OpenSpec change 不进 M2 leaderboard）
- ❌ 不是 `current_stage` 的替代（两个字段尺度不同：`current_stage` 是 Stage 节奏，change 是交付节奏）
- ❌ 不是独立 evaluator 的输入（Archive-Ready 独立审的范围超出 harness 职责）
- ❌ Coordinator 不自己跑 `openspec list --json` 生成此字段——由用户或 OpenSpec 工作流写入，harness 只读

**限制**（基于 1 项目观察）：
- Zero Magic 是目前唯一观察到的 OpenSpec 用户，`schema: "spec-driven"` 是唯一确认存在的 schema 值
- 其他 spec 系统（Notion / Linear / JIRA / 自制 YAML）需要独立字段（不要塞进 `active_openspec_changes` 里），避免 schema 污染

---

### 状态文件不存在时

首次 `/harness` 调用时文件不存在 → harness 执行完整代码探测 → REPORT 阶段创建初始状态文件。
