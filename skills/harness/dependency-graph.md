# Skill 依赖关系图

## 核心依赖链

```
unified-tool-interface（所有工具/调度/权限的基础）
  ↓
  ├→ agent-loop（循环中的 tool dispatch 依赖 Tool Protocol）
  ├→ layered-permission（checkPermissions 是 Tool 接口的一部分）
  ├→ agent-tool-budget（maxResultSize/shouldDefer 是 Tool 接口字段）
  ├→ concurrent-dispatch（isConcurrencySafe 是 Tool 接口方法）
  └→ plugin-loading（插件产出必须符合 Tool Protocol）

agent-loop（循环是所有高级能力的载体）
  ↓
  ├→ context-engineering（每轮上下文准备在循环 Phase 1）
  ├→ agent-resilience（Withhold/恢复在循环内部）
  ├→ agent-memory（记忆注入在循环的附件阶段）
  └→ multi-agent-design（子 Agent 复用循环）

context-engineering → agent-resilience（压缩是韧性的一部分）
                    → session-recovery（恢复依赖压缩边界）

agent-memory → agent-reflection（反思建立在记忆之上）
            → team-memory-sync（团队同步建立在记忆系统之上）

layered-permission → command-sandbox（Bash 安全是权限的特化）
                   → plan-mode（计划模式依赖权限模式切换）

api-client-layer → model-routing（路由建立在客户端之上）

context-engineering → compact-system（压缩是上下文工程的核心能力）
compact-system → session-memory（SM Compact 依赖 session memory 数据）

agent-loop + event-hook-system → magic-docs（post-sampling hook + 子 Agent 更新）

mcp-runtime + event-hook-system → ide-feedback-loop（LSP 通过 MCP 桥接 + 诊断注入通过 hook）

multi-agent-design → runtime-summaries（Agent Summary 依赖子 Agent 体系）

auth-identity → policy-limits（策略拉取需要 OAuth 认证）
             → remote-managed-settings（远程配置需要认证）
             → settings-sync（设置同步需要认证）
             → team-memory-sync（团队同步需要 org 身份）
```

## 无依赖（可独立构建）

```
config-cascade          — 只需文件路径
api-client-layer        — 只需 Provider 环境变量
auth-identity           — 只需安全存储路径
event-hook-system       — 只需事件定义
startup-optimization    — 只需启动入口
telemetry-pipeline      — 只需 Sink 配置
process-lifecycle       — 只需信号处理
feature-flag-system     — 只需 flag 服务地址
instruction-file-system — 只需文件系统路径
tip-system              — 只需 config-cascade
platform-integration    — 只需平台 API
voice-input             — 只需平台音频 API
```

## 并行安全矩阵

**规则：**
- 无条件安全并行组：同组内没有依赖箭头，设计和编码都可并行
- 条件并行组：只在设计阶段并行；编码阶段按依赖串行
- 明确依赖组：目标 skill 依赖上游输出，不能放进同一并行组

```
✓ 无条件安全并行组：
  [unified-tool-interface, config-cascade, api-client-layer]
    → 三者互无依赖，都是基础契约

  [auth-identity, instruction-file-system]
    → 互无依赖，都依赖 config-cascade 但彼此独立

  [layered-permission, agent-tool-budget]
    → 都依赖 unified-tool-interface 但彼此独立

  [plugin-loading, event-hook-system]
    → 互无依赖

  [model-routing, plan-mode]
    → 互无依赖

  [startup-optimization, telemetry-pipeline, feature-flag-system]
    → 三者互无依赖

  [team-memory-sync, magic-docs]
    → 互无依赖

  [ide-feedback-loop, tip-system, voice-input]
    → 互无依赖

  [policy-limits, remote-managed-settings, settings-sync]
    → 都依赖 auth-identity 但彼此独立

  [runtime-summaries, platform-integration, voice-input]
    → 互无依赖

⚠️ 条件并行组：
  [agent-memory, agent-reflection]
    → 依赖关系：agent-memory → agent-reflection
    → 设计阶段可并行（memory 方案与 reflection 方案可同步产出）
    → 编码阶段必须串行（reflection 需要 import memory 类型和存储接口）
    → Coordinator 判断规则：任务类型=设计 → 可并行；任务类型=编码/审计补齐 → 串行

  [compact-system, session-memory]
    → 依赖关系：compact-system → session-memory
    → 设计阶段可并行（压缩策略与 session-memory 结构可同步设计）
    → 编码阶段必须串行（session-memory 依赖 compact-system 的接口与压缩边界）
    → Coordinator 判断规则：任务类型=设计 → 可并行；任务类型=编码/审计补齐 → 串行

  [agent-loop, concurrent-dispatch]
    → 前置条件：unified-tool-interface 已完成
    → 满足前置后可并行设计/实现；前置未完成时不能排入同一轮

✗ 明确依赖，必须串行：
  layered-permission → command-sandbox
    → command-sandbox 依赖权限层的安全判定输出
    → 不能与 layered-permission 同轮
    → 可与 agent-tool-budget 并行（无依赖关系）

  context-engineering 与 agent-resilience
    → resilience 的压缩策略建立在 context-engineering 之上
    → 必须串行

  agent-loop 与 multi-agent-design
    → multi-agent 复用循环，需要循环的 API 设计作为输入
    → 必须串行

  harness-entry-points 与任何核心模块
    → 入口层是最后的胶水层，依赖所有核心模块的接口
    → 最后做
```

## 依赖决策速查

当 Coordinator 需要判断"A 和 B 能否并行"时：

1. 先查条件并行组 → A 和 B 是否命中“设计可并行 / 编码串行”的特殊对？
   - 是，且任务类型=设计 → **可并行**
   - 是，且任务类型=编码/审计补齐 → **串行**
2. 查明确依赖链 → A 是否指向 B 或 B 指向 A？
   - 有箭头 → **串行**
3. 查无条件安全并行组 → A 和 B 是否在同一个安全并行组？
   - 在 → **可并行**
4. 都没找到 → 检查两者是否操作同一个文件/目录
   - 是 → **串行**
   - 否 → **可并行**
5. 仍然不确定 → **保守串行**
