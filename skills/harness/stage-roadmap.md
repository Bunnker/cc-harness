# 阶段路线图

双层模型：基础契约层先行定义边界，能力层按需构建。

## 层 1：基础契约（必须先做，定义后续所有模块的边界）

### 阶段 0：契约定义

这些模块定义了整个系统的核心接口和运行时基础。后续所有能力模块依赖它们的输出。

| 优先级 | 模块 | Skill | 并行组 | 定义什么边界 |
|--------|------|-------|--------|------------|
| P0 | 工具抽象接口 | `unified-tool-interface` | A | Tool Protocol — 所有工具/插件的统一契约 |
| P0 | 配置系统 | `config-cascade` | A | 配置来源和优先级 — 所有模块的配置读取方式 |
| P0 | API 客户端 | `api-client-layer` | A | Provider 接口 — LLM 调用的抽象边界 |
| P1 | 认证系统 | `auth-identity` | B | 身份模型 — 谁在调 API、凭证怎么管 |
| P1 | 指令文件系统 | `instruction-file-system` | B | 指令加载规则 — 行为配置的发现和优先级 |
| P2 | 入口层 | `harness-entry-points` | C（等 A+B） | 执行引擎接口 — CLI/SDK/Bridge 的统一抽象 |

**检测条件**：存在 Tool Protocol + 配置加载 + API 客户端工厂 + 身份管理

**skip_if**：不可跳过 — 所有后续阶段依赖此阶段产出。但可以裁剪：
- 单 Provider 项目 → 跳过 `api-client-layer` 的多 Provider 工厂
- 无用户登录需求 → 跳过 `auth-identity`（降为环境变量 API key）
- 单入口项目 → 跳过 `harness-entry-points`

**为什么先做**：如果工具接口在阶段 3 才定义，阶段 1 的循环和阶段 2 的权限层都在用临时接口 → 后面全部返工。

**value_assessment**：
- 设计方案 → **保留**（接口定义是后续所有模块的输入，必须写入项目文件）
- 编码实现 → **保留**（基础契约代码是直接依赖）
- 审计报告 → **看情况**（严重接口问题保留，通过则丢弃过程）

---

## 层 2：能力构建（按依赖关系推进，不是线性阶段）

### 阶段 1：最小循环

**前置**：阶段 0 的 P0（工具接口 + 配置 + API 客户端）

| 模块 | Skill | 并行组 | 产出 |
|------|-------|--------|------|
| Agent 主循环 | `agent-loop` | A | 循环状态机 + 退出条件 + 流式执行 |

**检测条件**：存在 while(true) 状态机 + tool dispatch + API 调用

**skip_if**：不可跳过 — Agent 主循环是所有能力的载体。

**value_assessment**：
- 设计方案 → **保留**（循环状态机设计是最核心架构决策）
- 编码实现 → **保留**（主循环代码是直接依赖）
- 审计报告 → **保留**（循环的退出条件和恢复路径错误代价极高）

---

### 阶段 2：安全与资源控制

**前置**：阶段 0 P0 + 阶段 1

| 模块 | Skill | 并行组 | 产出 |
|------|-------|--------|------|
| 权限层 | `layered-permission` | A | 顺序评估链 |
| 工具预算 | `agent-tool-budget` | A | 结果截断 + 延迟加载 |
| 命令沙箱 | `command-sandbox` | B（依赖权限层） | Shell 安全检查 |

**检测条件**：存在权限检查 + 结果大小限制 + 命令安全验证

**skip_if**：
- 目标项目是纯内部工具，无安全风险 → 可跳过 `command-sandbox`
- 目标项目不执行 shell 命令 → 可跳过 `command-sandbox`
- 目标项目是只读分析工具 → 可简化 `layered-permission` 为单一 allow 策略

**value_assessment**：
- 设计方案 → **保留**（安全边界定义不能丢）
- 编码实现 → **保留**（权限代码是安全关键路径）
- 审计报告 → **保留**（安全审计结论是合规证据）

---

### 阶段 3：长会话支持

**前置**：阶段 2

| 模块 | Skill | 并行组 | 产出 |
|------|-------|--------|------|
| 上下文工程 | `context-engineering` | A | 多源 prompt + 渐进压缩 |
| Agent 韧性 | `agent-resilience` | B（依赖上下文） | Withhold + 恢复链 |
| 并发调度 | `concurrent-dispatch` | A | 分区调度器 |
| 压缩系统 | `compact-system` | B（依赖上下文工程） | 4 级压缩流水线 + 微压缩 |
| 会话记忆 | `session-memory` | C（依赖压缩系统） | 后台周期提取 + 10 段模板 |

**检测条件**：存在上下文压缩 + 错误恢复 + 并发分区 + 分级压缩 + 会话记忆提取

**skip_if**：
- 目标项目的对话通常不超过模型上下文窗口的 50% → 跳过 `compact-system` 和 `session-memory`
- 目标项目不需要错误恢复（一次性任务） → 跳过 `agent-resilience`
- 目标项目不需要并发工具执行 → 跳过 `concurrent-dispatch`

**value_assessment**：
- 设计方案 → **保留**（压缩策略和恢复路径设计影响系统稳定性）
- 编码实现 → **保留**
- 审计报告 → **看情况**（压缩边界问题保留，性能数据丢弃过程只保留结论）

---

### 阶段 4：跨会话与记忆

**前置**：阶段 3

| 模块 | Skill | 并行组 | 产出 |
|------|-------|--------|------|
| 记忆系统 | `agent-memory` | A | 4 类型 + 双路径保存 |
| 反思进化 | `agent-reflection` | A（设计并行；编码依赖 memory） | 纠正/确认学习 + 过期验证 |
| 会话恢复 | `session-recovery` | B（依赖上下文工程） | UUID 链 + 三层清理 + 持久化 |
| 团队记忆同步 | `team-memory-sync` | C（依赖 agent-memory + auth） | 双向 delta 同步 + 密钥扫描 |
| 自动维护文档 | `magic-docs` | C | 标记检测 + 后台子 Agent 更新 |

**检测条件**：存在记忆存储 + 反思机制 + 会话恢复 + 团队同步 + 活文档

**skip_if**：
- 目标项目是一次性脚本或短生命周期任务 → 跳过整个阶段
- 目标项目不需要跨会话记忆 → 跳过 `agent-memory` + `agent-reflection`
- 单人项目 → 跳过 `team-memory-sync`
- 目标项目没有需要持续维护的文档 → 跳过 `magic-docs`

**value_assessment**：
- 设计方案 → **保留**（记忆分类和反思机制是架构决策）
- 编码实现 → **保留**
- 探索性分析（如现有记忆方案调研）→ **不保留**（结论写入 state.learnings，过程丢弃）
- 审计报告 → **看情况**

---

### 阶段 5：可扩展性

**前置**：阶段 2（权限层）

| 模块 | Skill | 并行组 | 产出 |
|------|-------|--------|------|
| 插件加载 | `plugin-loading` | A | 多层加载 + 条件激活 |
| 事件 Hook | `event-hook-system` | A | 声明式拦截 + 决策合并 |
| 模型路由 | `model-routing` | B | 动态模型选择 |
| 计划模式 | `plan-mode` | B | 思考/执行分离 |
| IDE 反馈闭环 | `ide-feedback-loop` | C（依赖 mcp-runtime + hook） | LSP + 诊断基线 + 被动反馈 |
| 上下文提示 | `tip-system` | B | 条件过滤 + LRU 调度 |

**检测条件**：存在插件注册 + Hook 引擎 + 模型路由 + IDE 诊断集成 + 提示调度

**skip_if**：
- 目标项目不需要插件体系 → 跳过 `plugin-loading` + `event-hook-system`
- 目标项目只用一个模型 → 跳过 `model-routing`
- 目标项目不集成 IDE → 跳过 `ide-feedback-loop`
- 目标项目不需要 plan 审批流 → 跳过 `plan-mode`
- 目标项目不需要用户提示 → 跳过 `tip-system`

**value_assessment**：
- 设计方案 → **保留**（插件协议和 Hook 契约是扩展点定义）
- 编码实现 → **保留**
- 探索性分析（如现有插件生态调研）→ **不保留**（结论写入 learnings）

---

### 阶段 6：多 Agent 编排

**前置**：阶段 1（循环）+ 阶段 3（调度）

| 模块 | Skill | 并行组 | 产出 |
|------|-------|--------|------|
| 多 Agent | `multi-agent-design` | A | Coordinator/Worker/Team |

**检测条件**：存在 Agent 生成 + 通知机制

**skip_if**：
- 目标项目只需要单 Agent → 跳过整个阶段
- 目标项目不需要后台任务 → 跳过（单 Agent 足够）

**value_assessment**：
- 设计方案 → **保留**（多 Agent 通信协议和隔离边界是核心架构）
- 编码实现 → **保留**
- 审计报告 → **保留**（多 Agent 的竞态和死锁审计结论有长期价值）

---

### 阶段 7：生产化

**前置**：基础能力基本完成

| 模块 | Skill | 并行组 | 产出 |
|------|-------|--------|------|
| 启动优化 | `startup-optimization` | A | 并行预取 + 分阶段启动 |
| 遥测管道 | `telemetry-pipeline` | A | 多 Sink + 采样 + PII |
| 特性门控 | `feature-flag-system` | A | 构建期/运行期双轨 |
| 进程管理 | `process-lifecycle` | B | 信号处理 + LIFO 清理 |
| 成本优化 | `prompt-cache-economics` | B | cache key 稳定性 |
| 运行时摘要 | `runtime-summaries` | B | Away/Agent/ToolUse 三粒度 |
| 平台集成 | `platform-integration` | A | 防休眠 + 跨平台通知 |
| 语音输入 | `voice-input` | A | 多平台音频捕获 + STT |

**检测条件**：存在启动 checkpoint + 遥测 + 特性门控 + 优雅关闭 + 运行时摘要 + 平台适配

**skip_if**：
- 目标项目是早期原型 → 跳过整个阶段（先让功能跑起来）
- 目标项目不需要遥测 → 跳过 `telemetry-pipeline`
- 目标项目启动已够快（< 1 秒） → 跳过 `startup-optimization`
- 目标项目不是长时间运行服务 → 跳过 `process-lifecycle` + `platform-integration`
- 目标项目不需要语音 → 跳过 `voice-input`

**value_assessment**：
- 设计方案 → **看情况**（启动优化和遥测的设计探索过程不值得保留，结论写入 learnings）
- 编码实现 → **保留**
- 性能基准测试 → **不保留**（数据会过期，只保留结论）

---

### 阶段 8：企业治理

**前置**：阶段 0 P1（认证系统）+ 阶段 0 P0（配置系统）

| 模块 | Skill | 并行组 | 产出 |
|------|-------|--------|------|
| 策略限制 | `policy-limits` | A | fail-open 远程功能门控 |
| 远程配置 | `remote-managed-settings` | A | Checksum 增量拉取 + 安全审查 |
| 设置同步 | `settings-sync` | A | 增量上传 + 按环境下载 |

**检测条件**：存在远程策略拉取 + 配置同步 + 安全审查

**skip_if**：
- 目标项目是个人项目或开源项目 → 跳过整个阶段
- 目标项目不需要远程配置管理 → 跳过 `remote-managed-settings`
- 目标项目不需要跨设备同步 → 跳过 `settings-sync`
- 目标项目不需要功能管控 → 跳过 `policy-limits`

**value_assessment**：
- 设计方案 → **保留**（企业治理的策略定义和信任模型是合规依据）
- 编码实现 → **保留**
- 审计报告 → **保留**（企业治理审计结论是合规证据）

---

## 按需模块（不在主线路径上）

| 模块 | Skill | 何时引入 |
|------|-------|---------|
| 投机执行 | `speculative-execution` | 需要预测性优化时 |
| MCP 运行时 | `mcp-runtime` | 需要集成 MCP 协议时 |
| Eval 方法论 | `eval-driven-design` | 迭代 prompt 设计时 |
| 架构不变式 | `architecture-invariants` | 架构评审时 |
