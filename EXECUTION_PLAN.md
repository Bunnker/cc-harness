# cc-harness 改造执行计划

日期：2026-04-15

## 1. 目标

将 `cc-harness` 从“强治理、弱执行的数据不足型 skill pack”升级为“可执行、可验证、可分发的 Agent control plane”。

本计划的核心不是继续增加 skill 数量，而是先补齐 4 个短板：

1. 阶段 0 根节点 portability 不足
2. 元数据分散，文档靠手工维护
3. trace 与 verification 仍偏文本后处理，不是真实执行证据
4. 安装与分发仍是个人原型模式，不适合团队协作

## 2. 北极星定义

改造完成后，`cc-harness` 应满足以下 5 个条件：

1. `portable` 以依赖图中心性衡量，而不是按 skill 数量衡量
2. `harness` 是默认入口，大多数 worker 默认不允许用户直连
3. trace 是执行证据，不是 Worker 自述摘要
4. 文档由 manifest 生成并可校验，不再依赖多处手工同步
5. skill pack 可以被版本锁定、升级、回滚并在团队内复现

## 3. 非目标

本轮不追求以下事项：

1. 不与 `gstack` 在浏览器、QA、ship、team ops 执行面正面对齐
2. 不继续优先扩 skill 数量
3. 不在没有 reference repo 和 held-out eval 的情况下启动自动搜索优化
4. 不一次性把所有 `cc-bound` skill 全部重写为 `portable`

## 4. 执行原则

1. 先修根节点，再修边缘能力
2. 先补数据面，再谈自优化
3. 先把默认路径收口，再保留专家绕过入口
4. 所有新增规则必须能被脚本或校验器执行，尽量避免“只写文档不落地”
5. 每一阶段都必须留下明确的验收标准和失败回滚点

## 5. 阶段总览

| 阶段 | 时间窗口 | 核心目标 | 结果 |
|------|----------|----------|------|
| P0 | 2026-04-15 至 2026-04-26 | 收口根节点、入口和元数据 | control plane 收敛 |
| P1 | 2026-04-27 至 2026-05-10 | 硬化 trace / verification 数据面 | evidence plane 落地 |
| P2 | 2026-05-11 至 2026-05-24 | 完成团队分发和产品化基础设施 | distribution plane 落地 |
| P3 | 2026-05-25 起 | 建 benchmark、reference repo、eval 与优化闭环 | proof plane 落地 |

---

## 6. P0：基础收口

### 6.1 目标

在不继续扩 skill 数量的前提下，解决结构性问题：

1. 阶段 0 根节点真正 `portable`
2. skill 元数据统一收敛
3. 默认入口改为 orchestrated-first
4. 为小任务引入低摩擦快速路径

### 6.2 工作项

#### P0-A：建立统一 manifest

新建一个统一元数据源，至少覆盖以下字段：

- `name`
- `role`
- `portability`
- `depends_on`
- `parallel_safe_with`
- `stage`
- `needs_user_context`
- `value_assessment`
- `target_path_policy`
- `default_invocation_mode`

基于 manifest 自动生成：

1. `skills/harness/skill-catalog.md`
2. `skills/harness/dependency-graph.md`
3. README 中的 skill 概览表
4. 基础 schema 校验器

#### P0-B：重写阶段 0 portability 根节点

优先改造以下 4 个 skill，使其从“Claude Code 源码解剖导向”切换为“框架无关的可迁移模式导向”：

1. `unified-tool-interface`
2. `config-cascade`
3. `instruction-file-system`
4. `harness-entry-points`

要求：

1. 每个 skill 明确区分“源码事实”和“可迁移模式”
2. 必须包含 `Transferable Pattern`
3. 必须包含 `Minimal Portable Version`
4. 必须包含 `Do Not Cargo-Cult`
5. 如果仍保留 CC 特有部分，必须单独标记，不允许混写

#### P0-C：入口治理收口

将当前“几乎全部 user-invocable”的模式改成两级入口：

1. `orchestrated mode`
   默认路径，用户通过 `harness` 或 `harness-lite` 使用能力
2. `expert direct mode`
   仅保留少数高价值、低风险、纯方法论或纯探索型 skill 允许直连

默认策略：

1. 大多数 worker 设为 `user-invocable: false`
2. `harness-verify` 保持 internal-only
3. 仅保留 `harness`、`harness-lite`、课程或少数方法论型 skill 作为公开入口

#### P0-D：新增 `harness-lite`

定义轻量模式触发条件：

1. 叶子模块
2. 目标路径不超过 2 个文件
3. 不涉及公共接口变更
4. 不涉及阶段跳转
5. 不涉及跨 Worker 依赖链

`harness-lite` 允许：

1. 同轮完成设计 + 编码
2. 单 worker 快速路径
3. 降低审批与编排摩擦

`harness` 严格模式保留不变，适用于多模块、跨阶段、审计型或高风险改动。

### 6.3 交付物

1. `skill-manifest` 及生成脚本
2. 自动生成后的 `skill-catalog.md` / `dependency-graph.md` / README skill 表
3. 4 个根节点 skill 的 portable 重写版
4. `harness-lite` skill
5. user-invocable 策略收口清单

### 6.4 验收标准

1. 文档主表不再手工维护
2. 阶段 0 根节点都能脱离 CC 语境独立阅读和复用
3. 大多数 worker 默认不可直连
4. 小补丁任务可通过 `harness-lite` 在一轮内完成

### 6.5 风险

1. manifest 设计过重，导致维护成本转移而不是下降
2. 过度关闭入口，损害专家用户的灵活性
3. `harness-lite` 与严格模式边界不清，导致规则冲突

### 6.6 回滚条件

如果 manifest 生成链在两轮迭代后仍无法稳定产出 README 和 catalog，则先缩小为“只生成内部 catalog + schema 校验”，README 暂不自动生成。

---

## 7. P1：数据面硬化

### 7.1 目标

把当前以 Worker 文本回复为主的 trace / verification，升级为真实执行证据系统。

### 7.2 工作项

#### P1-A：实现 command façade

引入统一执行包装层，负责记录：

1. 原始命令
2. `stdout`
3. `stderr`
4. `exit_code`
5. `duration_ms`
6. `cwd`
7. `worker_id`
8. `target_paths`

要求：

1. `commands.log` 来自真实执行，不来自 Worker 自述
2. 失败和超时必须可区分
3. 同一类命令格式一致，便于后续评估和回归分析

#### P1-B：实现真实 per-worker diff

按 worker 真实落盘：

1. touched files
2. per-worker diff
3. per-worker diff stat
4. 路径越界检查结果

优先方案：

1. 同组并发 worker 默认走隔离目录或 worktree
2. 无法隔离时，至少记录 dispatch 时基线并按 `target_paths` 做受限 diff

#### P1-C：升级 `harness-verify`

将验证 worker 的输入从“Coordinator 汇总文本”升级为“真实执行产物 + 标准 command 结果 + diff artifacts”。

验证维度至少保留：

1. `build_lint_typecheck`
2. `smoke_tests`
3. `runtime_invariants`
4. `structural_fidelity`
5. `verification_coverage`

#### P1-D：把 trace 变成第一类工件

固定 trace 目录结构，并要求每轮都有：

1. `worker-{n}-prompt.md`
2. `commands.log`
3. `worker-{n}-diff.patch`
4. `verification.md`
5. `scorecard.json`

设计轮可以简化，但编码轮和审计轮必须完整。

### 7.3 交付物

1. command façade / execution wrapper
2. 真正的 `commands.log`
3. 真正的 per-worker diff artifacts
4. 升级版 `harness-verify`
5. 统一 scorecard 生成逻辑

### 7.4 验收标准

1. `commands.log` 不依赖 Worker 自述
2. `diff.patch` 能按 worker 归因
3. 任意一轮执行都能复盘失败点、耗时和越界修改
4. verification 输出对同一输入可重复

### 7.5 风险

1. 包装层侵入过强，影响现有 worker 执行体验
2. 并发隔离实现不稳，导致 diff 归因失真
3. scorecard 权重设计过早固化

### 7.6 回滚条件

如果并发 diff 归因短期内无法可靠实现，则先强制编码轮串行化，优先保证证据正确性。

---

## 8. P2：团队分发与产品化

### 8.1 目标

将当前“直接覆盖到 `~/.claude/skills`”的个人原型模式，升级为可版本化、可团队复现、可升级回滚的分发体系。

### 8.2 工作项

#### P2-A：引入命名空间与版本

每个发布版本必须具备：

1. skill pack 名称
2. 版本号
3. 兼容矩阵
4. release note

避免与用户本地已有 skill 直接发生同名覆盖。

#### P2-B：设计 lock 与 bootstrap 机制

新增：

1. `skills.lock` 或等效版本锁文件
2. 团队 bootstrap 配置
3. repo 内声明文件，记录当前使用的 pack 版本与入口策略

#### P2-C：安装器升级

替换现有覆盖式安装器，要求支持：

1. dry-run
2. upgrade
3. rollback
4. version pin
5. namespace install

#### P2-D：CI 和校验链

至少补齐以下检查：

1. manifest schema 校验
2. 生成文件漂移校验
3. frontmatter 规则校验
4. install / upgrade / rollback 冒烟测试
5. skill 入口暴露面检查

### 8.3 交付物

1. 版本化发布规范
2. 新安装器与升级脚本
3. lock 文件机制
4. CI 校验工作流
5. 团队 bootstrap 示例

### 8.4 验收标准

1. 安装器不再默认覆盖同名 skill
2. 团队成员能使用同一 lock 版本得到一致 skill pack
3. 升级与回滚路径可演练
4. 文档与 manifest 不一致时 CI 失败

### 8.5 风险

1. 命名空间策略过于复杂，降低个人使用门槛
2. 安装器改造与现有用户路径冲突
3. CI 校验链过重，影响迭代速度

### 8.6 回滚条件

如果 namespace 安装在短期内与现有生态冲突严重，则先保留兼容安装模式，但默认输出冲突警告和版本信息。

---

## 9. P3：证明、基准与优化闭环

### 9.1 目标

证明 `cc-harness` 不是“文档过拟合”，而是在不同项目与技术栈中可重复工作。

### 9.2 工作项

#### P3-A：构建 3 个 reference repo

至少覆盖：

1. CLI agent
2. IDE agent
3. multi-agent runtime

每个 reference repo 都需要：

1. 明确阶段映射
2. 至少一轮完整 harness trace
3. 一组固定 smoke tests

#### P3-B：建立 search / held-out eval

评估规则：

1. search repo 用于调优
2. held-out repo 用于验证泛化
3. 只有两侧都不回退，候选改动才允许晋升

#### P3-C：在基准稳定后再启用 M0-M3

`HARNESS_EVOLUTION_PLAN.md` 中的 observability、candidate、leaderboard、proposer 可以保留，但启动顺序必须是：

1. 先 reference repo
2. 再固定 scorecard
3. 再候选评估
4. 最后才是自动搜索优化

**启动 M2 候选评估前先读**：`UNIFIED-ROADMAP.md` §M2 实证启发式 —— 来自 Zero Magic 的 4 个完整候选实验（`slim-report-v1` PROMOTED / `independent-audit-v1` PROPOSED / `prompt-self-save-v1` REJECTED / `lean-prefix-v1` WITHDRAWN）归纳出的"高 ROI / 低 ROI 候选特征"表。这批 empirical priors 避免 M2 启动就把第一批预算花在 Worker 服从性约束或 prefix 微优化这类已知低 ROI 方向上。

### 9.3 交付物

1. 3 个 reference repo
2. 基线 scorecard
3. search / held-out 评估配置
4. 候选晋升与拒绝规则

### 9.4 验收标准

1. 至少 2 个不同技术栈项目上能稳定跑完整流程
2. 有明确 baseline 可比较每次改造收益
3. 自动优化只在基准稳定后启动

### 9.5 风险

1. 过早做 proposer，优化会过拟合单一仓库
2. reference repo 选型不合理，无法代表真实使用面
3. scorecard 指标设计与真实质量脱钩

---

## 10. 并行策略

可并行推进：

1. `P0-A manifest` 与 `P0-B portability 根节点重写`
2. `P1-A command façade` 与 `P1-D trace 目录规范`
3. `P2-A 版本/namespace 设计` 与 `P2-D CI 校验链`

必须串行推进：

1. `P0-C 入口治理` 依赖 manifest 完成
2. `P0-D harness-lite` 依赖入口治理边界明确
3. `P1-C harness-verify 升级` 依赖 command façade 和真实 diff
4. `P3-C 自动优化` 依赖 reference repo 与 eval 先完成

## 11. 资源建议

推荐最小配置：

1. 1 人负责 control plane 与文档生成链
2. 1 人负责 execution wrapper、trace、verification 数据面
3. 如有人力，额外 1 人负责安装器、CI 与团队分发

如果只有 1 人推进，建议顺序为：

1. manifest
2. 根节点 portable 化
3. 入口治理
4. command façade
5. verify 升级
6. 安装器与 CI

## 12. 关键决策门

以下节点必须单独评审，不建议边做边拍板：

1. manifest 字段模型
2. 哪些 skill 保留直连入口
3. `harness-lite` 触发条件
4. command façade 的记录格式
5. namespace / version / lock 方案
6. scorecard 的初始权重

## 13. Definition of Done

满足以下条件时，本轮改造可认为完成：

1. 阶段 0 根节点已完成 portable-first 改造
2. `skill-catalog` / `dependency-graph` / README skill 表由 manifest 生成
3. 大多数 worker 默认不允许用户直连
4. 编码轮 trace 来自真实执行记录
5. `harness-verify` 基于真实 artifacts 工作
6. 安装器支持版本化和非破坏式升级
7. 至少 2 个 reference repo 上有稳定 baseline

## 14. 下一步建议

建议按以下顺序立刻开工：

1. 定义 manifest 结构并建立生成器骨架
2. 列出所有 skill 的 `user-invocable` 收口名单
3. 为 4 个阶段 0 根节点制定 portable 重写模板
4. 设计 `harness-lite` 的输入/输出约束
5. 起草 command façade 的日志格式和 artifact 命名规范

这 5 项完成后，后续所有工作都会明显更顺。
