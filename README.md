# Harness Skills Pack

Claude Code 的 **Agent Harness 设计/审计编排体系**，包含 **45 个 skill**（1 个协调器 + 1 个验证 worker + 1 个课程文档生成器 + 42 个可调度 worker）。

Harness 的定位是 **设计/审计 harness，不是实现 harness**：它扫描项目 → 出执行计划 → 等用户确认 → 调度子 Agent 携带 skill 并行构建企业级 Agent 系统。每轮只做一件事：设计、编码、或审计。

---

## 按主题导航

遇到具体问题先查这里，再去看对应 skill：

- **按失败模式找 skill** → [FAILURE-MODES.md](FAILURE-MODES.md) — 15 种失败模式（含 Anthropic 显式命名的 context anxiety / self-eval blind spot / 结构保真 FM-15）× 47 个 skill 的正交视图
- **Anthropic 对齐路线图** → [ANTHROPIC-ALIGNMENT-PLAN.md](ANTHROPIC-ALIGNMENT-PLAN.md) — 原报告 17 项优先级清单状态矩阵 + 每轮改动的 commit / PR 追溯 + 维护规则
- **Harness 进化计划** → [skills/harness/HARNESS_EVOLUTION_PLAN.md](skills/harness/HARNESS_EVOLUTION_PLAN.md) — Meta-Optimization Track M0-M3（可观测 → 可执行 → 候选评估 → 自动搜索）

---

## 安装

Skill 必须放在 **全局** `~/.claude/skills/` 才能跨项目使用。项目级 `.claude/skills/` 只对当前项目可见。

```bash
# Linux / macOS / Git Bash
git clone https://github.com/<your-user>/<this-repo>.git
cd <this-repo>
bash install.sh

# PowerShell
.\install.ps1

# 手动
cp -r skills/* ~/.claude/skills/
```

`install.sh` / `install.ps1` 会覆盖 `~/.claude/skills/` 下的同名 skill，安全可重入。

---

## 使用

```
/harness <项目根目录路径>
```

例：`/harness "D:\ai code\Zero_magic"`

### 工作协议

Harness 是一个 **协调器（Coordinator）**，它的唯一职责是 **Plan → Approve → Execute → Report**：

1. **SCAN** — 读 `.claude/harness-state.json`（如有），跨会话恢复进展；否则探测代码现状
2. **PLAN** — 输出本轮目标、调度的 worker 列表、并行/串行分组、依赖前置
3. **APPROVE** — **硬边界**：用户没说"确认/OK/开始"之前绝不调度任何 worker
4. **EXECUTE** — 用 Agent 工具并发分派 worker，每个 worker 加载对应 skill
5. **REPORT** — 汇总结果、跑验证命令、更新 state、写 trace

**Coordinator 自身禁止做设计/编码/审计**——所有实质工作必须通过 worker 完成，即使只改 1 行代码。

---

## Skill 目录（45 个）

每个 skill 都附带 **Do Not Cargo-Cult**（标 `portable` 的）和 **Minimal Portable Version**。`cc-bound` 的 skill 仍以 Claude Code 源码解剖为主，跨项目使用时需人工判断哪些是 CC 特有实现。

### 协调层（non-worker，2 个）

| skill | 作用 |
|------|------|
| [`harness`](skills/harness/) | 总协调器，扫描/计划/分派/汇总；本身不做实质工作 |
| [`agent-architecture-curriculum`](skills/agent-architecture-curriculum/) | 把 Agent runtime 源码理解重构为 Diataxis 课程化文档 |

### Harness 基础设施 worker（1 个）

| skill | 作用 | 何时调度 |
|------|------|---------|
| [`harness-verify`](skills/harness-verify/) | 编码/审计轮的验证 worker：跑 commands、生成 diff、产出 `verification.md` + `scorecard.json` + `commands.log` | **编码/审计轮的最后一个串行组必须是它** |

### 基础契约层（6 个，`portability: mixed`）

| skill | purpose | best_for | depends_on |
|------|---------|----------|------------|
| [`unified-tool-interface`](skills/unified-tool-interface/) | 工具抽象接口 + buildTool 工厂 | 设计工具系统的第一步 | — |
| [`config-cascade`](skills/config-cascade/) | 5 源配置级联 + 热重载 | 构建配置系统 | — |
| [`api-client-layer`](skills/api-client-layer/) | 多 Provider API 客户端 | 构建 LLM 调用层 | — |
| [`auth-identity`](skills/auth-identity/) | 认证 + 安全存储 + 多租户 | 构建认证系统 | — |
| [`harness-entry-points`](skills/harness-entry-points/) | CLI / SDK / Bridge 统一入口 | 设计多形态入口 | unified-tool-interface, config-cascade |
| [`instruction-file-system`](skills/instruction-file-system/) | 4 层指令遍历 + 条件规则 + @include | 构建指令加载系统 | config-cascade |

### Agent 核心层（9 个）

| skill | purpose | best_for | depends_on |
|------|---------|----------|------------|
| [`agent-loop`](skills/agent-loop/) | 循环状态机 + 10 种终态 + 7 种恢复 | 构建主循环 | unified-tool-interface |
| [`layered-permission`](skills/layered-permission/) | 顺序评估 + 早期返回 + bypass-immune | 构建权限控制 | unified-tool-interface |
| [`agent-tool-budget`](skills/agent-tool-budget/) | 延迟加载 + 结果截断 + token 续跑 | 优化工具 token 消耗 | unified-tool-interface |
| [`concurrent-dispatch`](skills/concurrent-dispatch/) | 并发分区调度 + 错误级联取消 | 构建工具执行调度器 | unified-tool-interface |
| [`context-engineering`](skills/context-engineering/) | 多源 system prompt + 渐进压缩 + 二级缓存 | 构建上下文管理 | agent-loop |
| [`agent-resilience`](skills/agent-resilience/) | Withhold + 5 级恢复 + 5 级压缩 | 构建错误恢复和长会话 | agent-loop, context-engineering |
| [`agent-memory`](skills/agent-memory/) | 4 类型记忆 + 双路径保存 + 过期检测 | 构建跨会话记忆 | agent-loop |
| [`agent-reflection`](skills/agent-reflection/) | 纠正+确认学习 + auto-dream + denial tracking | 构建自我改进机制 | agent-memory |
| [`multi-agent-design`](skills/multi-agent-design/) | 5 条真实分支（async/sync/teammate/fork/remote） | 构建多 Agent 系统 | agent-loop, concurrent-dispatch |

### 能力扩展层（8 个）

| skill | purpose | best_for | depends_on |
|------|---------|----------|------------|
| [`command-sandbox`](skills/command-sandbox/) | 23 项 Bash 安全检查 + Tree-sitter AST | 构建命令执行安全层 | layered-permission |
| [`plugin-loading`](skills/plugin-loading/) | 4 层加载器 + 7 源合并 + 条件激活 | 构建插件/扩展系统 | unified-tool-interface |
| [`event-hook-system`](skills/event-hook-system/) | 声明式事件拦截 + 5 种执行类型 + 决策合并 | 构建事件扩展点 | — |
| [`model-routing`](skills/model-routing/) | 动态模型选择 + 订阅层级 | 构建模型路由 | api-client-layer |
| [`plan-mode`](skills/plan-mode/) | 思考/执行分离 + 审批工作流 | 构建计划审批机制 | layered-permission |
| [`session-recovery`](skills/session-recovery/) | UUID 链 + 三层清理 + 成本持久化 | 构建会话恢复 | context-engineering |
| [`speculative-execution`](skills/speculative-execution/) | CoW 预执行 + 边界停止 | 构建预测性优化 | agent-loop, layered-permission |
| [`mcp-runtime`](skills/mcp-runtime/) | MCP 发现 / 连接 / 映射 | 集成 MCP 协议 | unified-tool-interface |

### 生产化层（5 个）

| skill | purpose | best_for | depends_on |
|------|---------|----------|------------|
| [`startup-optimization`](skills/startup-optimization/) | 并行预取 + DCE + 分阶段启动 | 优化启动性能 | — |
| [`telemetry-pipeline`](skills/telemetry-pipeline/) | 多 Sink + 采样 + PII 过滤 | 构建可观测性 | — |
| [`process-lifecycle`](skills/process-lifecycle/) | 信号处理 + LIFO 清理 | 构建进程管理 | — |
| [`feature-flag-system`](skills/feature-flag-system/) | 构建期 DCE + 运行期缓存评估 | 构建特性门控 | — |
| [`prompt-cache-economics`](skills/prompt-cache-economics/) | cache key 稳定性 + 选择性延迟 | 优化 API 成本 | agent-tool-budget, context-engineering |

### 长会话扩展层（2 个）

| skill | purpose | best_for | depends_on |
|------|---------|----------|------------|
| [`compact-system`](skills/compact-system/) | 4 级压缩流水线 + 微压缩 + SM Compact | 构建上下文压缩系统 | context-engineering |
| [`session-memory`](skills/session-memory/) | 会话级后台记忆提取 + 10 段模板 | 构建会话内记忆 | agent-loop |

### 记忆扩展层（2 个）

| skill | purpose | best_for | depends_on |
|------|---------|----------|------------|
| [`team-memory-sync`](skills/team-memory-sync/) | 团队记忆双向同步 + 密钥扫描 | 构建团队知识共享 | agent-memory, auth-identity |
| [`magic-docs`](skills/magic-docs/) | 标记检测 + 后台子 Agent 文档更新 | 构建自动维护文档 | agent-loop, event-hook-system |

### IDE / 输入扩展层（3 个）

| skill | purpose | best_for | depends_on |
|------|---------|----------|------------|
| [`ide-feedback-loop`](skills/ide-feedback-loop/) | LSP 多服务器 + 诊断基线 + 被动反馈 | 构建 IDE 代码质量闭环 | mcp-runtime, event-hook-system |
| [`tip-system`](skills/tip-system/) | 条件过滤 + LRU 调度 + spinner 集成 | 构建上下文感知提示 | config-cascade |
| [`voice-input`](skills/voice-input/) | 多平台音频捕获 + 流式 STT | 构建语音输入能力 | — |

### 企业 / 生产化扩展层（5 个）

| skill | purpose | best_for | depends_on |
|------|---------|----------|------------|
| [`runtime-summaries`](skills/runtime-summaries/) | Away / Agent / ToolUse 三粒度摘要 | 构建运行时可观测性 | multi-agent-design |
| [`platform-integration`](skills/platform-integration/) | 防休眠 + 跨平台通知 | 构建平台适配层 | — |
| [`policy-limits`](skills/policy-limits/) | fail-open 远程策略门控 | 构建企业功能管控 | auth-identity |
| [`remote-managed-settings`](skills/remote-managed-settings/) | Checksum 增量拉取 + 安全审查 | 构建企业远程配置 | auth-identity, config-cascade |
| [`settings-sync`](skills/settings-sync/) | 增量上传 + 按环境下载 | 构建跨设备配置同步 | auth-identity |

### 方法论（2 个，不产出代码）

| skill | purpose | best_for |
|------|---------|----------|
| [`eval-driven-design`](skills/eval-driven-design/) | 假设命名 + 前后对比评分 + A/B 测试 | 迭代 prompt 设计 |
| [`architecture-invariants`](skills/architecture-invariants/) | 6 条不变式 + 进化轨迹 + 被否决方案 | 架构评审 / 决策记录 |

---

## 调度规则（依赖与并行）

完整规则在 [`skills/harness/dependency-graph.md`](skills/harness/dependency-graph.md)，速查如下。

### 核心依赖链

```
unified-tool-interface
  ├→ agent-loop ─┬→ context-engineering → agent-resilience
  │              │                       → session-recovery
  │              ├→ agent-memory → agent-reflection
  │              │              → team-memory-sync
  │              └→ multi-agent-design → runtime-summaries
  ├→ layered-permission → command-sandbox
  │                     → plan-mode
  ├→ agent-tool-budget
  ├→ concurrent-dispatch
  └→ plugin-loading

api-client-layer → model-routing
auth-identity → policy-limits / remote-managed-settings / settings-sync / team-memory-sync
context-engineering → compact-system → session-memory
agent-loop + event-hook-system → magic-docs
mcp-runtime + event-hook-system → ide-feedback-loop
harness-entry-points  ← 最后做（依赖所有核心接口）
```

### 无条件安全并行组（同组可同轮分派）

- `[unified-tool-interface, config-cascade, api-client-layer]`
- `[auth-identity, instruction-file-system]`
- `[layered-permission, agent-tool-budget]`
- `[plugin-loading, event-hook-system]`
- `[model-routing, plan-mode]`
- `[startup-optimization, telemetry-pipeline, feature-flag-system]`
- `[team-memory-sync, magic-docs]`
- `[ide-feedback-loop, tip-system, voice-input]`
- `[policy-limits, remote-managed-settings, settings-sync]`
- `[runtime-summaries, platform-integration, voice-input]`

### 条件并行组（设计可并行，编码必须串行）

- `[agent-memory, agent-reflection]`
- `[compact-system, session-memory]`
- `[agent-loop, concurrent-dispatch]`（前置：`unified-tool-interface` 完成）

### 并行决策速查

判断 A 和 B 能否同轮分派：

1. 命中条件并行组？ → 设计可并行 / 编码串行
2. 命中明确依赖链（A → B 或 B → A）？ → **串行**
3. 命中无条件安全并行组？ → **可并行**
4. 操作同一文件/目录？ → **串行**
5. 仍不确定？ → **保守串行**

---

## 状态与 Trace

Harness 在目标项目下维护：

```
<project>/.claude/
├── harness-state.json          # 跨会话进展（current_stage / modules / learnings / denial_tracking）
├── harness-hooks.json          # 可选：自定义 PreScan/PrePlan/PostExecute hook
├── harness-lab/
│   ├── trace-index.json        # 全历史 trace 索引（不删旧轮）
│   └── traces/
│       └── <date>-<stage>-<type>/
│           ├── verification.md
│           ├── scorecard.json
│           ├── commands.log
│           └── failure-reason.md  # 仅失败时
```

下次 `/harness` 启动时会读 state，输出"上次进展摘要"，从未完成的模块继续。`learnings` 注入 PLAN 阶段的约束，`cc_adaptations` 注入 worker prompt，避免重复犯错。

---

## 更新流程

源机器更新 skill → 重新打包 → push：

```bash
# 在源机器上重新拷贝最新 skill 进 pack
cp -r ~/.claude/skills/<skill-name> skills/
git add . && git commit -m "Update <skill-name>"
git push
```

目标机器：

```bash
git pull && bash install.sh
```
