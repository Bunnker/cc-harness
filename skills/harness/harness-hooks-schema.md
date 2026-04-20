# Harness Hook 配置 Schema

> 来源：CC 的 27 种 Hook 事件（`src/schemas/hooks.ts`）+ 5 种执行类型（`src/utils/hooks/hookEvents.ts`）。
> harness 不需要完整的 Hook 基础设施——通过 JSON 配置 + Coordinator 在每个 Phase 检查来实现。

## 配置文件

路径：`{project}/.claude/harness-hooks.json`

此文件可选。不存在时所有 Hook 点跳过，不影响默认流程。

## Schema

```json
{
  "version": 1,
  "hooks": {
    "PreScan": {
      "enabled": true,
      "type": "command",
      "command": "python scripts/pre_scan.py",
      "description": "注入自定义探测规则"
    },
    "PostScan": {
      "enabled": true,
      "type": "command",
      "command": "python scripts/validate_scan.py",
      "description": "校验探测结果"
    },
    "PrePlan": {
      "enabled": true,
      "type": "inline",
      "constraints": [
        "本轮禁止使用 cc-bound skill",
        "Worker 数量上限 3"
      ],
      "description": "注入额外计划约束"
    },
    "PostPlan": {
      "enabled": false,
      "type": "command",
      "command": "python scripts/review_plan.py",
      "description": "自动审查计划"
    },
    "PreWorkerDispatch": {
      "enabled": true,
      "type": "inline",
      "prompt_suffix": "确保所有输出文件使用 UTF-8 编码",
      "cross_layer_contract": {
        "enforce_worker_output": true,
        "template": "worker_result_section",
        "pairs": [
          {
            "field": "soul",
            "producer": "backend/gateway/src/run/manager.ts:428",
            "consumer": "backend/runtime/src/context_assembly.py:_build_identity_block"
          }
        ]
      },
      "description": "给每个 Worker prompt 追加约束 + 可选注入跨层契约表（Contract-First 模式，cross_layer_contract 字段整体可选）"
    },
    "PostWorkerComplete": {
      "enabled": false,
      "type": "command",
      "command": "python scripts/notify.py --event worker_complete",
      "description": "Worker 完成时通知"
    },
    "WorkerFailed": {
      "enabled": true,
      "type": "inline",
      "action": "escalate",
      "description": "Worker 失败时直接上报用户"
    },
    "PreReport": {
      "enabled": false,
      "type": "command",
      "command": "npm run lint --quiet",
      "description": "Report 前检查代码风格（只读，不修复）"
    },
    "PostReport": {
      "enabled": false,
      "type": "command",
      "command": "git add -A && git commit -m 'harness: auto-commit'",
      "description": "Report 后自动提交"
    }
  }
}
```

## Hook 能力边界（每个 Hook 允许做什么、不允许做什么）

### Phase 1: SCAN

| Hook | 允许的输入 | 允许的输出 | 副作用策略 | 可否改 state |
|------|-----------|-----------|-----------|-------------|
| `PreScan` | 当前 harness-state.json（只读） | 额外探测项列表、额外 skip_if 条件 | **无副作用** — 只返回数据给 Coordinator，不修改文件/状态 | 否 |
| `PostScan` | 项目模型（语言/框架/模块列表） | 修正后的模型字段、额外 constraints | **无副作用** — 修正只影响 Coordinator 内存中的模型，不写 state | 否 |

### Phase 2: PLAN

| Hook | 允许的输入 | 允许的输出 | 副作用策略 | 可否改 state |
|------|-----------|-----------|-----------|-------------|
| `PrePlan` | 项目模型 + current_stage + learnings | 额外约束字符串、skill 黑名单/白名单、Worker 数量上限 | **无副作用** — 约束注入到 Coordinator 的计划生成逻辑，不修改文件 | 否 |
| `PostPlan` | 完整计划文本 | 修改后的 Worker 列表（可添加/移除/标记 skip）、修改 target_paths | **无副作用** — 修改只影响 Coordinator 将要展示给用户的计划。**不能绕过用户确认**：PostPlan 修改后的计划仍然需要用户确认才能执行。 | 否 |

> **硬边界**：SKILL.md 的 "用户确认前只能输出计划" 约束对 PostPlan 同样生效。PostPlan 不能自动触发执行，只能修改待确认的计划内容。

### Phase 3: EXECUTE

| Hook | 允许的输入 | 允许的输出 | 副作用策略 | 可否改 state |
|------|-----------|-----------|-----------|-------------|
| `PreWorkerDispatch` | Worker prompt + target_paths + skill 名称 + 可选 `cross_layer_contract.pairs`（字段两端位置对照表）| 修改后的 prompt（仅追加，不能删除安全约束；Contract-First 模式下追加一段强制输出"跨层一致性"表的指令）、修改后的 paths（仅缩小，不能扩大到受保护路径） | **有限副作用** — command 类型可执行只读命令（如 lint 检查），但不能修改项目文件 | 否 |
| `PostWorkerComplete` | Worker 结果 + 状态（completed/partial/failed） | 额外验证结果（pass/fail + 原因）、通知指令 | **允许副作用** — command 类型可执行通知命令（如发送消息）。但不能修改 Worker 产出文件。 | 否 |
| `WorkerFailed` | 失败原因 + Worker prompt + 已尝试的恢复路径列表 | `{ retry_prompt: "..." }` 提供修正 prompt 用于重试 / `{ abort_group: true }` 取消同组其他 Worker / `{ escalate: true }` 直接上报用户 / `null` 走默认恢复路径 | **无副作用** — 只返回决策，由 Coordinator 执行 | 否 |

### Phase 4: REPORT

| Hook | 允许的输入 | 允许的输出 | 副作用策略 | 可否改 state |
|------|-----------|-----------|-----------|-------------|
| `PreReport` | 所有 Worker 结果摘要（Coordinator 已综合后的） | 额外检查项列表（Coordinator 在 Report 中执行） | **无副作用** — 只追加检查项，不修改结果 | 否 |
| `PostReport` | Report 摘要 + harness-state.json 的 diff | 后续动作指令列表 | **允许副作用** — 这是唯一允许不可逆动作的 Hook。command 类型可执行 git commit、发送通知等。Coordinator 在执行前必须在 Report 末尾列出将要执行的 PostReport 动作。**禁止自动启动下一轮 /harness** — 下一轮必须由用户显式触发，不可被 hook 绕过。 | **间接可**：PostReport 本身不改 state，但它触发的 command 可能产生外部状态变更（如 git commit） |

### 能力边界总结

```
可改 state 的 Hook：无。state 只由 Coordinator 在 REPORT 阶段更新。
可有副作用的 Hook：PostWorkerComplete（通知）、PostReport（git commit/通知）。禁止自动启动下一轮。
不可有副作用的 Hook：PreScan、PostScan、PrePlan、PostPlan、PreWorkerDispatch、WorkerFailed、PreReport。
不可绕过用户确认：PostPlan。
不可绕过安全约束：所有 Hook（见下方"安全约束"章节）。
```

> **设计理由**：CC 的 Hook 系统中，只有 `notification` 类型允许副作用且不影响决策流。harness 的 PostWorkerComplete 和 PostReport 对应这个角色。其他 Hook 都是"数据进→数据出"的纯函数模式，不允许副作用——这保证了 Coordinator 对编排流程的完全控制权。

## Hook 类型

| type | 含义 | 执行方式 |
|------|------|---------|
| `command` | 外部命令 | Coordinator 用 Bash 工具执行，捕获 stdout 作为返回值 |
| `inline` | 内联配置 | Coordinator 直接读取 JSON 字段，不执行外部命令 |

> **为什么只有 2 种类型（CC 有 5 种）**：CC 的 5 种类型（command/intercept/pre-tool/post-tool/notification）是运行时代码层面的。harness 是 prompt 驱动的编排层，Coordinator 自己就是执行引擎——不需要 intercept（拦截在 prompt 指令中实现）、不需要 pre/post-tool（Worker 的工具约束在 prompt 中声明）。command + inline 覆盖所有 harness 需要的场景。

## 安全约束

### Hook 不可覆盖 deny

Hook 不能：
- 授权 Worker 使用被禁止的工具（Agent、AskUserQuestion）
- 扩大 Worker 的 target_paths 到受保护路径（.claude/、.git/）
- 跳过 denial_tracking 降级检查
- 跳过综合理解检查

> **源码对齐**：CC 的 `hooks.ts` 明确声明 Hook 的 allow 不能覆盖 settings 的 deny（信任层级：deny > allow）。harness 的 Hook 同理：配置级的安全约束不可被 Hook 绕过。

### Hook 执行超时

`command` 类型 Hook 的 Bash 执行超时为 30 秒。超时视为 Hook 失败，走默认流程。

### Hook 配置不存在时

`harness-hooks.json` 不存在 → 所有 Hook 点跳过，Coordinator 走默认流程。
单个 Hook 的 `enabled: false` → 该 Hook 跳过。
这保证了 Hook 系统是纯增量的——不配置不影响任何现有行为。
