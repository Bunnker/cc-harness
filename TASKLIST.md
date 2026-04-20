# cc-harness 改造任务清单

关联文档：[EXECUTION_PLAN.md](./EXECUTION_PLAN.md)

日期：2026-04-15

## 使用方式

- `[ ]` 未开始
- `[-]` 进行中
- `[x]` 已完成
- 每个阶段只有在“阶段入口条件”满足后再启动
- 如果某任务阻塞后续主线，优先解决阻塞项，不并行扩 scope

## P0：基础收口

### 阶段入口条件

- [x] 冻结新增 skill 数量
- [x] 确认本阶段只做 manifest、根节点 portability、入口治理、lite 模式
- [x] 确认 `P0` 期间不启动 auto-optimization 相关工作

### P0-A：Manifest 与生成链

- [x] 建立 `skill-manifest` 目录或等效元数据源
- [x] 定义 manifest schema
- [x] 为每个 skill 补齐基础元数据
- [x] 将 `role` 纳入 manifest
- [x] 将 `portability` 纳入 manifest
- [x] 将 `depends_on` 纳入 manifest
- [x] 将 `parallel_safe_with` 纳入 manifest
- [x] 将 `stage` 纳入 manifest
- [x] 将 `needs_user_context` 纳入 manifest
- [x] 将 `value_assessment` 纳入 manifest
- [x] 将 `default_invocation_mode` 纳入 manifest
- [x] 编写 manifest 校验脚本
- [x] 编写 `skill-catalog.md` 生成脚本
- [x] 编写 `dependency-graph.md` 生成脚本
- [x] 编写 README skill 表生成脚本
- [x] 验证生成结果与当前文档结构兼容
- [x] 将生成链接入本地检查命令

### P0-B：阶段 0 portability 根节点

- [x] 为 `unified-tool-interface` 制定 portable 重写模板
- [x] 为 `config-cascade` 制定 portable 重写模板
- [x] 为 `instruction-file-system` 制定 portable 重写模板
- [x] 为 `harness-entry-points` 制定 portable 重写模板
- [x] 重写 `unified-tool-interface`
- [x] 重写 `config-cascade`
- [x] 重写 `instruction-file-system`
- [x] 重写 `harness-entry-points`
- [x] 为每个根节点 skill 补齐 `Transferable Pattern`
- [x] 为每个根节点 skill 补齐 `Minimal Portable Version`
- [x] 为每个根节点 skill 补齐 `Do Not Cargo-Cult`
- [x] 将 CC 特有实现与 portable 内容分段隔离
- [x] 复核 4 个根节点 skill 是否仍残留“源码事实与抽象模式混写”

### P0-C：入口治理

- [x] 列出全部 `user-invocable: true` skill 清单
- [x] 标记必须保留公开入口的 skill
- [x] 标记应转为 internal-only / orchestrated 的 worker
- [x] 定义 `orchestrated mode` 与 `expert direct mode` 的边界
- [x] 批量收口大多数 worker 的 `user-invocable`
- [x] 确认 `harness-verify` 保持 internal-only
- [x] 更新相关 README 和入口说明
- [x] 增加入口暴露面检查脚本

### P0-D：`harness-lite`

- [x] 定义 `harness-lite` 的目标用户
- [x] 定义 `harness-lite` 的触发条件
- [x] 明确与严格 `harness` 的分界线
- [x] 设计 `harness-lite` prompt 结构
- [x] 设计 `harness-lite` 的输出格式
- [x] 设计 `harness-lite` 的限制条件
- [x] 新建 `harness-lite` skill
- [x] 在 README 中补充 `harness-lite` 使用说明
- [x] 用 2 个小任务样例验证 `harness-lite` 不会越过 strict mode 边界

### P0 验收

- [x] `skill-catalog.md` 可由 manifest 生成
- [x] `dependency-graph.md` 可由 manifest 生成
- [x] README skill 表可由 manifest 生成
- [x] 4 个阶段 0 根节点可被认定为 portable-first
- [x] 大多数 worker 默认不可直连
- [x] `harness-lite` 可处理叶子模块小任务

### P0 依赖关系

- `P0-C` 依赖 `P0-A`
- `P0-D` 依赖 `P0-C`
- `P1` 启动前必须完成 `P0-A`、`P0-C`

---

## P1：数据面硬化

### 阶段入口条件

- [x] `P0-A manifest` 已稳定
- [x] 入口治理策略已收口
- [x] trace artifact 命名规范已确认

### P1-A：Command Façade

- [x] 设计统一执行包装层接口
- [x] 定义命令记录格式
- [x] 定义 `stdout/stderr/exit_code/duration_ms` 字段
- [x] 定义 timeout 与 failure 分类
- [x] 实现 command façade 最小版本
- [x] 让 façade 支持 worker 上下文标记
- [x] 让 façade 支持 `target_paths` 标记
- [x] 让 façade 输出标准 `commands.log`
- [x] 用最小样例验证 `commands.log` 不再依赖 Worker 自述

### P1-B：真实 per-worker diff

- [x] 设计 touched files 采集方式
- [x] 设计 per-worker diff 存放结构
- [x] 设计 per-worker diff stat 存放结构
- [x] 设计路径越界检查逻辑
- [x] 评估并发 worker 的隔离方案
- [x] 若可行，优先实现 worktree 或隔离目录方案
- [x] 若暂不可行，先实现 baseline + `target_paths` 受限 diff
- [x] 验证同组并发场景下 diff 归因是否可靠

当前结论：
- 已通过 `scripts/validate_parallel_diff_attribution.py` 覆盖“不重叠 target_paths”与“重叠 target_paths”两类并发场景
- 已通过 `scripts/validate_worktree_isolation.py` 覆盖 `prepare-worker-isolation.py -> run-harness-verify.py --cleanup-worktrees` 的隔离链路
- `peer_owned_changed_files` + `attribution_confidence` 已接入 `worker-{n}-diff.json`
- `worker-{n}-worktree.json` + `capture_source=worker_worktree` 已接通，重叠 target_paths 可通过 worktree 走强隔离归因

### P1-C：升级 `harness-verify`

- [x] 梳理 `harness-verify` 当前输入输出
- [x] 将输入源切换为真实执行 artifacts
- [x] 让 `harness-verify` 读取标准 `commands.log`
- [x] 让 `harness-verify` 读取 per-worker diff
- [x] 保留 5 个核心评分维度
- [x] 统一 `verification.md` 模板
- [x] 统一 `scorecard.json` 模板
- [x] 统一 `failure-reason.md` 模板
- [x] 验证同一输入下输出可重复

### P1-D：统一 trace 工件

- [x] 固定 trace 目录结构
- [x] 固定 `worker-{n}-prompt.md` 命名
- [x] 固定 `commands.log` 命名
- [x] 固定 `worker-{n}-diff.patch` 命名
- [x] 固定 `verification.md` 命名
- [x] 固定 `scorecard.json` 命名
- [x] 区分设计轮与编码轮的必需工件
- [x] 为缺失工件提供失败提示

### P1 验收

- [x] `commands.log` 基于真实执行
- [x] `diff.patch` 能按 worker 归因
- [x] 任意失败轮次可回溯命令、输出、耗时、路径越界
- [x] `harness-verify` 基于 artifacts 而非文本摘要工作
- [x] `verification.md` 与 `scorecard.json` 能稳定复现

### P1 依赖关系

- `P1-C` 依赖 `P1-A`、`P1-B`
- `P1-D` 可与 `P1-A` 并行
- `P2` 启动前建议先完成 `P1-C`

---

## P2：团队分发与产品化

### 阶段入口条件

- [x] Manifest 与入口策略已稳定
- [x] `harness-verify` 和 trace 工件结构已稳定
- [x] 安装器改造边界已确认

### P2-A：命名空间与版本

- [x] 设计 skill pack 名称规范
- [x] 设计版本号规范
- [x] 设计兼容矩阵格式
- [x] 设计 release note 模板
- [x] 设计 namespace 策略
- [x] 评估 namespace 对现有安装路径的影响

### P2-B：Lock 与 Bootstrap

- [x] 设计 `skills.lock` 或等效锁文件结构
- [x] 设计 repo bootstrap 配置结构
- [x] 设计团队声明文件结构
- [x] 让 bootstrap 能声明 pack 版本与入口策略
- [x] 编写 bootstrap 示例

### P2-C：安装器升级

- [x] 盘点现有 `install.sh` 与 `install.ps1` 行为
- [x] 设计新安装器 CLI
- [x] 支持 `dry-run`
- [x] 支持 `upgrade`
- [x] 支持 `rollback`
- [x] 支持 `version pin`
- [x] 支持 namespace install
- [x] 保留兼容模式或迁移提示
- [x] 用本地模拟环境演练安装、升级、回滚

### P2-D：CI 与校验链

- [x] 增加 manifest schema 校验
- [x] 增加生成文件漂移校验
- [x] 增加 frontmatter 规则校验
- [x] 增加 skill 暴露面检查
- [x] 增加 install 冒烟测试
- [x] 增加 upgrade 冒烟测试
- [x] 增加 rollback 冒烟测试
- [x] 将失败输出整理为可读信息

### P2 验收

- [x] 安装器不再默认覆盖同名 skill
- [x] 团队成员可通过锁文件复现同一版本
- [x] 升级与回滚路径可演练
- [x] 文档与 manifest 不一致时 CI 会失败

### P2 依赖关系

- `P2-C` 依赖 `P2-A`、`P2-B`
- `P2-D` 可与 `P2-A` 并行
- `P3` 启动前建议先完成 `P2-D`

---

## P3：证明、基准与优化闭环

### 阶段入口条件

- [ ] 前三阶段主链已稳定
- [ ] trace 与 scorecard 结构已稳定
- [ ] 团队分发方式已稳定

### P3-A：Reference Repos

- [ ] 选定 CLI agent reference repo
- [ ] 选定 IDE agent reference repo
- [ ] 选定 multi-agent runtime reference repo
- [ ] 为每个 repo 建立阶段映射
- [ ] 为每个 repo 准备至少一轮完整 trace
- [ ] 为每个 repo 准备固定 smoke tests
- [ ] 记录每个 repo 的 baseline scorecard

### P3-B：Search / Held-out Eval

- [ ] 设计 eval 配置结构
- [ ] 标记 search repos
- [ ] 标记 held-out repos
- [ ] 明确候选晋升规则
- [ ] 明确候选拒绝规则
- [ ] 确认 held-out 至少覆盖 1 个不同技术栈

### P3-C：M0-M3 启动顺序

- [ ] 先完成 `M0 Observability`
- [ ] 再固定 scorecard baseline
- [ ] 再做候选评估
- [ ] 最后才做 proposer / 自动搜索优化
- [ ] 明确“未满足基准条件时禁止启动自动优化”的规则

### P3 验收

- [ ] 至少 2 个不同技术栈项目可稳定跑完整流程
- [ ] 每次改动可与 baseline 对比
- [ ] 自动优化不会在无 held-out 验证时启动

### P3 依赖关系

- `P3-B` 依赖 `P3-A`
- `P3-C` 依赖 `P3-A`、`P3-B`

---

## 关键决策门

以下事项不建议边做边定，必须单独评审：

- [ ] manifest 字段模型
- [ ] 哪些 skill 保留直连入口
- [ ] `harness-lite` 触发条件
- [ ] command façade 日志格式
- [ ] namespace / version / lock 方案
- [ ] scorecard 初始权重

## 当前建议开工顺序

### 本周首批任务

- [ ] 定义 manifest 结构
- [ ] 建立 manifest 生成器骨架
- [ ] 列出全部 `user-invocable` skill 收口名单
- [ ] 为 4 个阶段 0 根节点制定 portable 重写模板
- [ ] 设计 `harness-lite` 输入/输出约束
- [ ] 起草 command façade artifact 格式

### 次批任务

- [ ] 完成 `skill-catalog.md` 生成
- [ ] 完成 `dependency-graph.md` 生成
- [ ] 完成 README skill 表生成
- [ ] 完成 4 个根节点 portable 改造
- [ ] 完成入口治理第一轮收口

## Definition of Done Checklist

- [ ] 阶段 0 根节点已完成 portable-first 改造
- [ ] `skill-catalog.md` 由 manifest 生成
- [ ] `dependency-graph.md` 由 manifest 生成
- [ ] README skill 表由 manifest 生成
- [ ] 大多数 worker 默认不允许用户直连
- [ ] 编码轮 trace 来自真实执行记录
- [ ] `harness-verify` 基于真实 artifacts 工作
- [ ] 安装器支持版本化和非破坏式升级
- [ ] 至少 2 个 reference repo 上有稳定 baseline
