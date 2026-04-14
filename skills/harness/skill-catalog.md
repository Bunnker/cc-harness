# Skill 调度目录

## 角色分类

| 角色 | 含义 | harness 默认调度 |
|------|------|-----------------|
| `worker` | 可被 harness 分派给子 Agent 执行设计/编码/审计 | 是 |
| `non-worker` | 不被 harness 调度（协调器自身、课程体系） | 否 |

| 可移植性 | 含义 | 跨项目建议 |
|----------|------|-----------|
| `portable` | 已按 design-oriented spec 重写，有 Do Not Cargo-Cult + Minimal Portable Version | 可安全用于其他项目 |
| `cc-bound` | 仍以 CC 源码解剖为主，缺少迁移指引 | 跨项目使用时需人工判断哪些是 CC 特有实现 |

**non-worker skill 注册表：**

| name | role | portability | reason |
|------|------|-------------|--------|
| `harness` | `non-worker` | `portable` | Coordinator 自身，只生成计划和汇总，不作为 worker 调度 |
| `agent-architecture-curriculum` | `non-worker` | `portable` | 课程化文档生成器，不作为设计/编码/审计 worker 使用 |

**特殊 worker skill（harness 基础设施）：**

| name | role | portability | purpose |
|------|------|-------------|---------|
| `harness-verify` | `worker` | `portable` | 编码/审计轮完成后的验证 Worker：执行 commands、生成 diff、产出 verification.md + scorecard.json + commands.log。**编码/审计轮必须调度此 Worker 作为最后一个串行组。** |

**当前 skill 总数：45 个** = **43 个可调度 worker skill**（21 个 `cc-bound` + 21 个 `portable` + 1 个 `harness-verify`）+ **2 个 non-worker**。

**cc-bound → portable 重写记录：**
- 初始：24 cc-bound + 18 portable
- 2026-04-04：agent-loop / layered-permission / context-engineering 重写为 portable（8 段模板）→ 21 + 21
- 剩余 cc-bound skill 中，已有可迁移结构的（unified-tool-interface、plugin-loading、session-recovery）不急着重写。

Worker 通过 SkillTool 调用，不由 Coordinator 手工复制内容。

## 调度元数据

### 基础契约层 `role: worker` · `portability: cc-bound`（`auth-identity`、`api-client-layer` 已升级为 `portable`）

| name | purpose | best_for | depends_on | parallel_safe_with | needs_user_context |
|------|---------|----------|------------|-------------------|-------------------|
| `unified-tool-interface` | 工具抽象接口 + buildTool 工厂 | 设计工具系统的第一步 | 无 | api-client-layer, config-cascade | 技术栈 |
| `config-cascade` | 5 源配置级联 + 热重载 | 构建配置系统 | 无 | api-client-layer, unified-tool-interface | 无 |
| `api-client-layer` | 多 Provider API 客户端 | 构建 LLM 调用层 | 无 | unified-tool-interface, config-cascade | Provider 选型 |
| `auth-identity` | 认证 + 安全存储 + 多租户 | 构建认证系统 | 无 | config-cascade | 安全要求 |
| `harness-entry-points` | CLI/SDK/Bridge 统一入口 | 设计多形态入口 | unified-tool-interface, config-cascade | 无（最后做） | 运行形态需求 |
| `instruction-file-system` | 4 层指令遍历 + 条件规则 | 构建指令加载系统 | config-cascade | auth-identity | 无 |

### Agent 核心层 `role: worker` · `portability: mixed`（`agent-loop`、`layered-permission`、`context-engineering`、`model-routing` 已升级为 `portable`）

| name | purpose | best_for | depends_on | parallel_safe_with | needs_user_context |
|------|---------|----------|------------|-------------------|-------------------|
| `agent-loop` | 循环状态机 + 退出条件 + 流式执行 | 构建主循环 | unified-tool-interface | agent-memory | 技术栈 |
| `layered-permission` | 权限评估链 + bypass-immune | 构建权限控制 | unified-tool-interface | agent-tool-budget | 安全要求 |
| `agent-tool-budget` | 延迟加载 + 结果截断 + token 续跑 | 优化工具 token 消耗 | unified-tool-interface | layered-permission | 无 |
| `concurrent-dispatch` | 并发分区调度 + 错误级联 | 构建工具执行调度器 | unified-tool-interface | 无（依赖工具接口设计结果） | 无 |
| `context-engineering` | 多源 system prompt + 渐进压缩 | 构建上下文管理 | agent-loop | agent-resilience | 模型选择 |
| `agent-resilience` | Withhold + 5 级恢复 + 5 级压缩 | 构建错误恢复和长会话 | agent-loop, context-engineering | 无（强依赖） | 无 |
| `agent-memory` | 4 类型记忆 + 双路径保存 + 过期检测 | 构建跨会话记忆 | agent-loop | agent-reflection（仅设计阶段） | 存储选型 |
| `agent-reflection` | 纠正+确认学习 + auto-dream | 构建自我改进机制 | agent-memory | agent-memory（仅设计阶段） | 无 |
| `multi-agent-design` | Fork/Coordinator/Team 编排 | 构建多 Agent 系统 | agent-loop, concurrent-dispatch | model-routing | 协作需求 |

### 能力扩展层 `role: worker` · `portability: cc-bound`（`mcp-runtime` 已升级为 `portable`）

| name | purpose | best_for | depends_on | parallel_safe_with | needs_user_context |
|------|---------|----------|------------|-------------------|-------------------|
| `command-sandbox` | 23 项 Bash 安全检查 | 构建命令执行安全层 | layered-permission | agent-tool-budget | 无 |
| `plugin-loading` | 4 层插件加载 + 条件激活 | 构建插件/扩展系统 | unified-tool-interface | event-hook-system | 无 |
| `event-hook-system` | 声明式事件拦截 + 决策合并 | 构建事件扩展点 | 无 | plugin-loading | 无 |
| `model-routing` | 动态模型选择 + 订阅层级 | 构建模型路由 | api-client-layer | plan-mode | 用户层级 |
| `plan-mode` | 思考/执行分离 + 审批 | 构建计划审批机制 | layered-permission | model-routing | 无 |
| `session-recovery` | UUID 链 + 三层清理 + 成本持久化 | 构建会话恢复 | context-engineering | 无（强依赖上下文） | 无 |
| `speculative-execution` | CoW 预执行 + 边界停止 | 构建预测性优化 | agent-loop, layered-permission | 无 | 无 |
| `mcp-runtime` | MCP 发现/连接/映射 | 集成 MCP 协议 | unified-tool-interface | 无 | MCP 需求 |

### 生产化层 `role: worker` · `portability: cc-bound`（`telemetry-pipeline`、`process-lifecycle` 已升级为 `portable`）

| name | purpose | best_for | depends_on | parallel_safe_with | needs_user_context |
|------|---------|----------|------------|-------------------|-------------------|
| `startup-optimization` | 并行预取 + DCE + 分阶段启动 | 优化启动性能 | 无 | telemetry-pipeline, feature-flag-system | 无 |
| `telemetry-pipeline` | 多 Sink + 采样 + PII 过滤 | 构建可观测性 | 无 | startup-optimization, feature-flag-system | 无 |
| `process-lifecycle` | 信号处理 + LIFO 清理 | 构建进程管理 | 无 | telemetry-pipeline | 无 |
| `feature-flag-system` | 构建期 DCE + 运行期缓存 | 构建特性门控 | 无 | startup-optimization, telemetry-pipeline | 无 |
| `prompt-cache-economics` | cache key 稳定性 + 成本优化 | 优化 API 成本 | agent-tool-budget, context-engineering | 无 | 无 |

### 长会话扩展层 `role: worker` · `portability: portable`

| name | purpose | best_for | depends_on | parallel_safe_with | needs_user_context |
|------|---------|----------|------------|-------------------|-------------------|
| `compact-system` | 4 级压缩流水线 + 微压缩 + SM Compact | 构建上下文压缩系统 | context-engineering | session-memory（仅设计阶段） | 无 |
| `session-memory` | 会话级后台记忆提取 + 10 段模板 | 构建会话内记忆 | agent-loop | compact-system（仅设计阶段） | 无 |

### 记忆扩展层 `role: worker` · `portability: portable`

| name | purpose | best_for | depends_on | parallel_safe_with | needs_user_context |
|------|---------|----------|------------|-------------------|-------------------|
| `team-memory-sync` | 团队记忆双向同步 + 密钥扫描 | 构建团队知识共享 | agent-memory, auth-identity | magic-docs | 团队协作需求 |
| `magic-docs` | 标记检测 + 后台子 Agent 文档更新 | 构建自动维护文档 | agent-loop, event-hook-system | team-memory-sync | 无 |

### IDE / 输入扩展层 `role: worker` · `portability: portable`

| name | purpose | best_for | depends_on | parallel_safe_with | needs_user_context |
|------|---------|----------|------------|-------------------|-------------------|
| `ide-feedback-loop` | LSP 多服务器 + 诊断基线 + 被动反馈 | 构建 IDE 代码质量闭环 | mcp-runtime, event-hook-system | tip-system, voice-input | IDE 集成需求 |
| `tip-system` | 条件过滤 + LRU 调度 + spinner 集成 | 构建上下文感知提示 | config-cascade | ide-feedback-loop, voice-input | 无 |
| `voice-input` | 多平台音频捕获 + 流式 STT | 构建语音输入能力 | 无 | ide-feedback-loop, tip-system | 平台需求 |

### 企业 / 生产化扩展层 `role: worker` · `portability: portable`

| name | purpose | best_for | depends_on | parallel_safe_with | needs_user_context |
|------|---------|----------|------------|-------------------|-------------------|
| `runtime-summaries` | Away/Agent/ToolUse 三粒度摘要 | 构建运行时可观测性 | multi-agent-design | platform-integration | 无 |
| `platform-integration` | 防休眠 + 跨平台通知 | 构建平台适配层 | 无 | runtime-summaries, voice-input | 平台需求 |
| `policy-limits` | fail-open 远程策略门控 | 构建企业功能管控 | auth-identity | remote-managed-settings, settings-sync | 企业合规需求 |
| `remote-managed-settings` | Checksum 增量拉取 + 安全审查 | 构建企业远程配置 | auth-identity, config-cascade | policy-limits, settings-sync | 企业合规需求 |
| `settings-sync` | 增量上传 + 按环境下载 | 构建跨设备配置同步 | auth-identity | policy-limits, remote-managed-settings | 无 |

### 方法论 `role: worker` · `portability: cc-bound`（不产出代码，产出决策/文档）

| name | purpose | best_for | depends_on | parallel_safe_with | needs_user_context |
|------|---------|----------|------------|-------------------|-------------------|
| `eval-driven-design` | 假设命名 + A/B 评分 | 迭代 prompt 设计 | 无 | architecture-invariants | 无 |
| `architecture-invariants` | 6 条不变式 + 进化轨迹 | 架构评审/决策记录 | 无 | eval-driven-design | 无 |
