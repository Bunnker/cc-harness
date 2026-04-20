<!-- Merged from [A] EXECUTION_PLAN.md, [B] HARNESS_EVOLUTION_PLAN.md, [C] ANTHROPIC-ALIGNMENT-PLAN.md — merged by Codex @ 2026-04-20 -->

# UNIFIED ROADMAP

## 0. 状态图例

- `✅ merged to main`：已合入主线，或来源文档已给出 commit / PR / merge 证据。
- `⚠️ workspace uncommitted`：工作已做且 `TASKLIST.md` 记为完成，但当前工作区仍有相关未提交修改或未跟踪文件。
- `❌ not started`：来源文档仍列为未启动。
- `⏸️ deferred`：来源文档明确推迟、等待前置条件或界定为下游范围。

## 1. 统一目标 / 非目标 / 执行原则

### 1.1 统一目标

- 将 `cc-harness` 从“强治理、弱执行的数据不足型 skill pack”升级为“可执行、可验证、可分发的 Agent control plane”。
- 让 `portable` 以依赖图中心性衡量，而不是以 skill 数量衡量。
- 让 `harness` / `harness-lite` 成为默认入口，大多数 worker 默认不允许用户直连。
- 让 trace 成为真实执行证据，而不是 Worker 自述摘要。
- 让文档、catalog、依赖图、README skill 表由 manifest 生成并可校验。
- 让 skill pack 可版本锁定、升级、回滚，并在团队内复现。
- 让结构保真成为与调度能力并列的核心质量维度，不只验证“能跑”，还验证“不破坏现有代码结构”。
- 让 Anthropic 对齐项、失败模式索引、参考仓与 scorecard 共同组成可持续进化的 proof plane。

### 1.2 统一非目标

- 不与 `gstack` 在浏览器、QA、ship、team ops 执行面正面对齐。
- 不继续以新增 skill 数量作为当前阶段优先级。
- 不在没有 reference repo 和 held-out eval 的前提下启动自动搜索优化。
- 不一次性把全部 `cc-bound` skill 重写为 `portable`。
- 不让 proposer 自动修改 skill 主体内容、`portable/cc-bound` 分类、安全边界、`state-schema.md` 主结构。
- 不把外部 online eval 聚合管线强行纳入当前 skill pack 的仓内职责。

### 1.3 统一执行原则

- 先修根节点，再修边缘能力。
- 先补数据面，再谈自优化。
- 先收口默认路径，再保留专家绕过入口。
- 所有新增规则都必须能被脚本、schema、校验器或命令执行。
- 每个阶段都必须定义验收标准、风险、失败回滚点。
- 中间输出是否保留，按产出价值决定，不按任务“大不大”决定。
- Coordinator 永不委托理解，必须自己读 Worker 结果、做综合判断。
- 默认保守：未声明可并行即串行，未声明安全即不放开。
- deny 优先且不可覆盖，路径约束、工具约束和危险操作审批都优先于便利性。
- 控制面不动，数据面新增：`harness-state.json` 继续是调度单一来源，traces / evals / candidates 是证据层。
- 外循环优化严格按 `M0 → M1 → M2 → M3` 顺序推进，前一层不稳不得启动后一层。
- 必须区分 search repos 和 held-out repos，防止对单一项目过拟合。

### 1.4 当前进度总览

- HEP 给出的总体演进轨迹为：`37/100 → P0 后 55 → P1 后 ~70 → P2 后 ~85 → 结构保真补强后 ~90`。
- 当前 6 个高层维度中，结构保真已被正式提升为独立质量维度。
- 已完成的 Anthropic 对齐轮次为 `R1-R8`。
- Foundations 中 `P0` 与 `P2` 在 `TASKLIST.md` 内已打勾，但当前工作区仍显示相关未提交改动。
- `P1` 的 trace / verification 主链已有 merge 证据。
- `P3` 与 `M0-M3` 仍是后续主线。

## 2. 合并裁决

- `[CONFLICT RESOLVED: P3 启动顺序]` 采用“`P3 admission gates` 先行，`M0 → M1 → M2 → M3` 后续执行”的合并版本。
- 解释：`[A] EXECUTION_PLAN.md` 给出更严格的 proof-plane 启动门槛，`[B] HARNESS_EVOLUTION_PLAN.md` 给出更细的优化流水线；合并后先做 reference repos / eval config / baseline，再进入 M-track。
- `[CONFLICT RESOLVED: manifest 字段集]` 统一保留 `[A]` 的完整字段定义，包含 `target_path_policy`。
- 解释：`TASKLIST.md` 的已完成清单未逐项列出 `target_path_policy`，但没有提出替代字段集；按信息更完整的计划文本收敛。
- `[CONFLICT RESOLVED: 长运行工件命名]` 统一写作 `init.sh + claude-progress.txt + feature_list.json`。
- 解释：`[C]` 的状态矩阵使用 `progress.txt` 作为简写，但 `T2` 追踪和 R3/R7 文本给出了 harness 内部的更具体文件名。
- `[CONFLICT RESOLVED: P3 与 HEP 重叠]` 仅保留一条 proof-plane 主线。
- 解释：`P3` 负责“参考仓 / 基线 / search-vs-held-out admission”，`M0-M3` 负责 admission 通过后的可观测、可执行、可评估、可搜索外循环；不重复列两份 candidate / search / proposer 闭环。

## 3. 全局顺序

- 全局主线：`R1-R8` 已完成 → `P0` → `P1` → `P2` → `P3 admission gates` → `M0` → `M1` → `M2` → `M3`。
- `P0-A manifest` 可与 `P0-B portability 根节点重写` 并行。
- `P1-A command façade` 可与 `P1-D trace 工件规范` 并行。
- `P2-A 版本 / namespace 设计` 可与 `P2-D CI 校验链` 并行。
- `P0-C` 依赖 `P0-A`。
- `P0-D` 依赖 `P0-C`。
- `P1-C` 依赖 `P1-A` 与 `P1-B`。
- `P2-C` 依赖 `P2-A` 与 `P2-B`。
- `P3-B` 依赖 `P3-A`。
- `P3-C` 依赖 `P3-A` 与 `P3-B`。
- `M0` 依赖 `P1` 稳定。
- `M1` 依赖 `M0` 稳定。
- `M2` 依赖 `M1` 稳定。
- `M3` 依赖 `M2` 稳定且至少 1 个 held-out repo 已就位。

## 4. Anthropic 对齐轮次

- `R1` — `✅ merged to main` — 内容对齐：6 个 skill 精准补齐轨迹/端态、P/G/E 三角色、Context Anxiety、自评盲点、ASM、`harness` 核心循环。
- `R2` — `✅ merged to main` — 导航层：建立 `FAILURE-MODES.md`，将 47 个 skill 按失败模式组织。
- `R3` — `✅ merged to main` — 长运行交接：加入 5 步启动仪式、工件冲突仲裁、One-feature-at-a-time、Sprint 末客观自检边界。
- `R4` — `✅ merged to main` — 生成首版 Anthropic 对齐路线图，并将 17 项优先级清单系统化。
- `R5` — `✅ merged to main` — 闭合 Meta #15：加入 Step 9 Transcript Shape Analysis 与 fragile pass 判定。
- `R6` — `✅ merged to main` — FAILURE-MODES 反哺：新增 `FM-15` 结构保真，并补齐计划状态矩阵。
- `R7` — `✅ merged to main` — 对 `T2` 做 Codex 严审，识别 5 个前置缺口后明确推迟，不把未定义 schema / policy 硬塞进 `harness`。
- `R8` — `✅ merged to main` — README 导航整合：把 `FAILURE-MODES.md`、`ANTHROPIC-ALIGNMENT-PLAN.md`、`HARNESS_EVOLUTION_PLAN.md` 接入主导航。

## 5. Failure-Mode Index

> 以下锚点是基于来源文档的合并推断，用来保持 `FM-*` 与 `A/P/M` 的联动，不新增任何任务。

- `FM-1` — `✅ merged to main` — Context Anxiety（容量焦虑）；主要锚定 `A6`、`A7`、`A15`、`M0`。
- `FM-2` — `✅ merged to main` — Self-Evaluation Blind Spot（自评盲点）；主要锚定 `A9`、`A15`、`R5`。
- `FM-3` — `✅ merged to main` — 跨会话状态丢失；主要锚定 `A4`、`A7`、HEP 的跨会话衔接闭环。
- `FM-4` — `✅ merged to main` — Harness 组件假设过期；主要锚定 `A14`、`A17`、维护触发器。
- `FM-5` — `✅ merged to main` — 评估信号噪音；主要锚定 `A9`、`A15`、`P1`、`P3`、`M0`。
- `FM-6` — `✅ merged to main` — 工具选择成本爆炸；主要锚定 `A2`、保守默认值、`M1` 的可执行命令模板。
- `FM-7` — `✅ merged to main` — 递归 / 无限循环；主要锚定 `A1`、fork 递归防护、`FM-8` 的工具约束。
- `FM-8` — `✅ merged to main` — 权限绕过 / 危险操作未经审批；主要锚定 `A3`、`P0` 入口治理、Worker deny 约束。
- `FM-9` — `✅ merged to main` — Prompt Cache 命中率崩溃；主要锚定缓存经济学、固定前缀、`M1`、`P3` 的真正 CacheSafeParams 缺口。
- `FM-10` — `✅ merged to main` — 孤儿进程 / 资源泄漏；主要锚定 `A10`、Hook 与运行时脚本、未来后台自治。
- `FM-11` — `✅ merged to main` — 配置跨机器 / 跨团队漂移；主要锚定 `P0-A`、`P2`、`A11`。
- `FM-12` — `✅ merged to main` — 可观测性缺失；主要锚定 `A13`、`P1`、`M0`。
- `FM-13` — `✅ merged to main` — 模型换代行为回归；主要锚定 `A14`、`P3`、`M2`、`M3`。
- `FM-14` — `✅ merged to main` — 用户纠正未被内化；主要锚定 `A7`、learnings、迁移反馈闭环。
- `FM-15` — `✅ merged to main` — 结构保真失败；主要锚定 `P1-C` scorecard 维度、`M0.3`、`P3` 基线对比。

## 6. Foundation Track

### `P0` — `⚠️ workspace uncommitted` — 基础收口

- 目标：在不扩 skill 数量的前提下，解决根节点 portability、元数据统一、默认入口收口、轻量快速路径四个结构性问题。
- 当前判定：`TASKLIST.md` 将 `P0` 全部子项标为 `[x]`，但当前分支 `p0-b-root-portability` 仍有相关 root skills / README / `harness-lite` 等未提交变更，因此保持工作区未提交状态。

#### P0 范围

- 统一 manifest 元数据源。
- 可迁移化重写 4 个阶段 0 根节点。
- 收口公开入口，改成 orchestrated-first。
- 新增 `harness-lite` 作为叶子级小任务快速路径。

#### P0 具体工作

- 建立 `skill-manifest` 目录或等效元数据源。
- 定义 manifest schema。
- 为每个 skill 补齐基础元数据。
- manifest 统一纳入 `name`、`role`、`portability`、`depends_on`、`parallel_safe_with`、`stage`、`needs_user_context`。
- manifest 统一纳入 `value_assessment`、`target_path_policy`、`default_invocation_mode`。
- 编写 manifest 校验脚本、`skill-catalog.md` 生成脚本、`dependency-graph.md` 生成脚本、README skill 表生成脚本。
- 验证生成结果与当前文档结构兼容。
- 将生成链接入本地检查命令。
- 为 `unified-tool-interface`、`config-cascade`、`instruction-file-system`、`harness-entry-points` 制定 portable 重写模板并完成重写。
- 为 4 个根节点 skill 统一补齐 `Transferable Pattern`、`Minimal Portable Version`、`Do Not Cargo-Cult`。
- 将 CC 特有实现与 portable 内容分段隔离。
- 复核 4 个根节点 skill，消除“源码事实与抽象模式混写”。
- 列出全部 `user-invocable: true` skill 清单，标记保留公开入口者与应转为 internal-only / orchestrated 的 worker。
- 定义 `orchestrated mode` 与 `expert direct mode` 的边界，并批量收口大多数 worker 的 `user-invocable`。
- 确认 `harness-verify` 维持 internal-only。
- 更新 README 与入口说明。
- 增加入口暴露面检查脚本。
- 定义 `harness-lite` 目标用户。
- 定义 `harness-lite` 触发条件。
- 触发条件统一为：叶子模块、目标路径不超过 2 个文件、不涉及公共接口变更、不涉及阶段跳转、不涉及跨 Worker 依赖链。
- 明确 `harness-lite` 与严格 `harness` 的分界线。
- 设计 `harness-lite` prompt 结构。
- 设计 `harness-lite` 输出格式。
- 设计 `harness-lite` 限制条件。
- 新建 `harness-lite` skill。
- 在 README 中补充 `harness-lite` 使用说明。
- 用 2 个小任务样例验证 `harness-lite` 不越过 strict mode 边界。

#### P0 交付物

- `skill-manifest` 与生成脚本。
- 自动生成后的 `skill-catalog.md`。
- 自动生成后的 `dependency-graph.md`。
- README skill 概览表。
- 4 个根节点 skill 的 portable 重写版。
- `harness-lite` skill。
- user-invocable 策略收口清单。

#### P0 验收

- `skill-catalog.md` 可由 manifest 生成。
- `dependency-graph.md` 可由 manifest 生成。
- README skill 表可由 manifest 生成。
- 4 个阶段 0 根节点可被认定为 portable-first。
- 大多数 worker 默认不可直连。
- `harness-lite` 可处理叶子模块小任务。

#### P0 风险与回滚

- 风险：manifest 设计过重，维护成本从文档转移到 schema。
- 风险：过度关闭入口，损害专家用户灵活性。
- 风险：`harness-lite` 与 strict mode 边界不清，导致规则冲突。
- 回滚：若 manifest 生成链两轮内仍不稳定，先缩成“内部 catalog + schema 校验”，README 暂不自动生成。

### `P1` — `✅ merged to main` — 数据面硬化

- 目标：把以 Worker 文本回复为主的 trace / verification 升级为真实执行证据系统。
- 当前判定：`TASKLIST.md` 将 `P1` 子项全部标记为 `[x]`；仓内已有 `trace contract`、`harness-verify` audit 升级、Transcript Shape Analysis 等 merge 证据，因此按已合主线处理。

#### P1 入口条件

- `P0-A manifest` 已稳定。
- 入口治理策略已收口。
- trace artifact 命名规范已确认。

#### P1 具体工作

- 设计统一执行包装层接口。
- 定义命令记录格式。
- 记录 `stdout`、`stderr`、`exit_code`、`duration_ms`、`cwd`、`worker_id`、`target_paths`。
- 定义 timeout 与 failure 分类。
- 实现 command façade 最小版本。
- 让 façade 支持 worker 上下文标记。
- 让 façade 支持 `target_paths` 标记。
- 让 façade 输出标准 `commands.log`。
- 验证 `commands.log` 不再依赖 Worker 自述。
- 设计 touched files 采集方式。
- 设计 per-worker diff 存放结构。
- 设计 per-worker diff stat 存放结构。
- 设计路径越界检查逻辑。
- 评估并发 worker 的隔离方案。
- 优先实现 worktree 或隔离目录方案。
- 若暂不可行，则实现 baseline + `target_paths` 受限 diff。
- 验证同组并发场景下 diff 归因可靠。
- 当前已覆盖“不重叠 / 重叠 target_paths”两类并发归因验证，并接入 `peer_owned_changed_files`、`attribution_confidence`、`worker-{n}-worktree.json`、`capture_source=worker_worktree`。
- 梳理 `harness-verify` 当前输入输出。
- 将 `harness-verify` 输入源切换为真实执行 artifacts。
- 让 `harness-verify` 读取标准 `commands.log`。
- 让 `harness-verify` 读取 per-worker diff。
- 保留 5 个核心评分维度：`build_lint_typecheck`、`smoke_tests`、`runtime_invariants`、`structural_fidelity`、`verification_coverage`。
- 统一 `verification.md` 模板。
- 统一 `scorecard.json` 模板。
- 统一 `failure-reason.md` 模板。
- 验证同一输入下输出可重复。
- 固定 trace 目录结构。
- 固定 `worker-{n}-prompt.md`、`commands.log`、`worker-{n}-diff.patch`、`verification.md`、`scorecard.json` 命名。
- 区分设计轮与编码轮的必需工件。
- 为缺失工件提供失败提示。

#### P1 交付物

- command façade / execution wrapper。
- 真实 `commands.log`。
- 真实 per-worker diff artifacts。
- 升级版 `harness-verify`。
- 统一 scorecard 生成逻辑。

#### P1 验收

- `commands.log` 基于真实执行。
- `diff.patch` 能按 worker 归因。
- 任意失败轮次都能回溯命令、输出、耗时、路径越界。
- `harness-verify` 基于 artifacts 而不是文本摘要。
- `verification.md` 与 `scorecard.json` 可稳定复现。

#### P1 风险与回滚

- 风险：包装层侵入过强，影响 worker 执行体验。
- 风险：并发隔离实现不稳，导致 diff 归因失真。
- 风险：scorecard 权重设计过早固化。
- 回滚：若并发 diff 归因短期内不可靠，则先强制编码轮串行，优先保证证据正确。

### `P2` — `⚠️ workspace uncommitted` — 团队分发与产品化

- 目标：把“直接覆盖到 `~/.claude/skills`”的个人原型模式升级为可版本化、可团队复现、可升级回滚的分发体系。
- 当前判定：`TASKLIST.md` 将 `P2` 子项全部标为 `[x]`，但当前工作区仍存在 `install.sh`、`install.ps1` 修改与 `bootstrap/`、`pack.json`、`skills.lock.json` 等未提交文件，因此标记为工作区未提交。

#### P2 入口条件

- Manifest 与入口策略已稳定。
- `harness-verify` 与 trace 工件结构已稳定。
- 安装器改造边界已确认。

#### P2 具体工作

- 设计 skill pack 名称规范。
- 设计版本号规范、兼容矩阵格式、release note 模板。
- 设计 namespace 策略。
- 评估 namespace 对现有安装路径的影响。
- 设计 `skills.lock` 或等效锁文件结构、repo bootstrap 配置结构、团队声明文件结构。
- 让 bootstrap 能声明 pack 版本与入口策略。
- 编写 bootstrap 示例。
- 盘点现有 `install.sh` 与 `install.ps1` 行为。
- 设计新安装器 CLI。
- 支持 `dry-run`、`upgrade`、`rollback`、`version pin`、namespace install。
- 保留兼容模式或迁移提示。
- 用本地模拟环境演练安装、升级、回滚。
- 增加 manifest schema 校验、生成文件漂移校验、frontmatter 规则校验、skill 暴露面检查、install / upgrade / rollback 冒烟测试。
- 将失败输出整理为可读信息。

#### P2 交付物

- 版本化发布规范。
- 新安装器与升级脚本。
- lock 文件机制。
- CI 校验工作流。
- 团队 bootstrap 示例。

#### P2 验收

- 安装器不再默认覆盖同名 skill。
- 团队成员可通过锁文件复现同一版本。
- 升级与回滚路径可演练。
- 文档与 manifest 不一致时，CI 必须失败。

#### P2 风险与回滚

- 风险：namespace 策略过于复杂，降低个人使用门槛。
- 风险：安装器改造与现有用户路径冲突。
- 风险：CI 校验链过重，影响迭代速度。
- 回滚：若 namespace 安装短期内与现有生态冲突严重，则保留兼容安装模式，但默认输出冲突警告与版本信息。

### `P3` — `❌ not started` — 证明、基准与优化闭环

- 目标：证明 `cc-harness` 不是文档过拟合，而能在不同项目与技术栈中重复工作，并为 `M0-M3` 提供 admission gates。
- 当前判定：`TASKLIST.md` 的 `P3-A/P3-B/P3-C` 仍全部未打勾。

#### P3 入口条件

- 前三阶段主链已稳定。
- trace 与 scorecard 结构已稳定。
- 团队分发方式已稳定。

#### P3 具体工作

- 选定 CLI agent reference repo。
- 选定 IDE agent reference repo。
- 选定 multi-agent runtime reference repo。
- 为每个 reference repo 建立阶段映射、准备至少一轮完整 trace、准备固定 smoke tests、记录 baseline scorecard。
- 设计 eval 配置结构。
- 标记 search repos。
- 标记 held-out repos。
- 明确候选晋升规则与拒绝规则。
- 确认 held-out 至少覆盖 1 个不同技术栈。
- 明确 `M0-M3` 启动顺序：先 reference repos，再固定 scorecard baseline，再做候选评估，最后才做 proposer / 自动搜索优化。
- 明确“未满足基准条件时禁止启动自动优化”的规则。
- 补入 HEP 识别的代码级缺口：后台自治、投机执行与 CoW 隔离、真正的 CacheSafeParams、并发 Worker 自动分区。

#### P3 交付物

- 3 个 reference repos。
- baseline scorecard。
- search / held-out 评估配置。
- 候选晋升与拒绝规则。

#### P3 验收

- 至少 2 个不同技术栈项目可稳定跑完整流程。
- 每次改动都可与 baseline 对比。
- 自动优化只在基准稳定后启动。

#### P3 风险

- 过早启动 proposer，会过拟合单一仓库。
- reference repo 选型不合理，无法代表真实使用面。
- scorecard 指标设计若与真实质量脱钩，会把后续搜索引向错误目标。

## 7. Meta-Optimization Track

### `M0` — `❌ not started` — Observability（可观测）

- 目标：每轮 harness 执行都留下完整证据链，而不是只在 `learnings` 中保留一句摘要。
- 前置依赖：`P1` 已完成并稳定。
- 为每轮执行保存 5 类原始证据：Worker prompt 快照、关键命令输出、Worker 最终回复、git diff、失败原因与状态变更。
- 将 verification 结果持久化到 `verification.md`，而非只保留 pass/fail。
- 持久化 build / lint / typecheck 完整输出、smoke test 逐条结果、结构保真检查 diff、运行时不变式验证输出。
- 建立 `scorecard.json`，记录 `build_lint_typecheck`。
- 建立 `scorecard.json`，记录 `smoke_tests`、`runtime_invariants`、`structural_fidelity`、`verification_coverage`。
- 记录 `composite_score`。
- 记录 `trace_path`。
- 要求 `learnings` 中每条 insight 引用对应 trace 路径。
- 成功标准：每轮执行后 traces 下有完整 5 类证据文件，scorecard 的所有适用维度非空，`learnings` 与 traces 可互相追溯，连续 3 轮实战后仍保持一致。

### `M1` — `❌ not started` — Executable Shell（可执行）

- 目标：把 harness 文档里的检查步骤变成可直接运行的命令与脚本，减少 Coordinator 解释偏差。
- 前置依赖：`M0` 稳定。
- 在 `harness-state.json` 中引入项目级 `commands` 配置。
- `commands` 覆盖 `build`、`lint`、`typecheck`、`smoke`、`structural_diff`。
- Coordinator 在 Phase 3 verification 时直接执行 `commands.build`、`commands.lint`、`commands.typecheck`、`commands.smoke`、`commands.structural_diff`。
- 不再仅靠 prompt 指令让 Worker “去运行构建检查”。
- 将 Hook 配置落地为可执行脚本目录 `.claude/harness-lab/hooks/`。
- 提供 `pre-worker-dispatch.sh`、`post-worker-complete.sh`、`worker-failed.sh`、`post-report.sh`。
- 为 harness 编排逻辑本身写回归测试。
- 回归测试覆盖 `state-schema` 一致性、trace 完整性、scorecard 维度覆盖、learnings 可溯源、候选不侵入主流程。
- 成功标准：`commands` 配置覆盖 5 类检查，至少 2 个 Hook 有可执行脚本，回归测试全部通过，并能在已有项目上跑通 M1 全流程。

### `M2` — `❌ not started` — Candidate Evaluation（候选评估）

- 目标：对 harness 编排策略变体做受控 A/B 评估，用数据决定是否采纳。
- 前置依赖：`M1` 稳定。
- 为每个候选建立 `manifest.json`。
- `manifest.json` 记录 `candidate_id`、创建时间、baseline、hypothesis、`modified_files`、`search_space`、`status`。
- 第一阶段允许 A/B 的范围：prompt / template 变体。
- 第一阶段允许 A/B 的范围：设计方案变体、小范围局部 patch、高不确定但可快速验证的模块。
- 第一阶段禁止 A/B 的范围：大规模编码任务。
- 第一阶段禁止 A/B 的范围：跨多文件架构重构、安全边界相关变更。
- 每个候选在独立 git worktree 中评估。
- 流程包含：从 main 创建 `eval/{candidate-id}` worktree、应用 `patches/`、对 search repo 执行完整 harness 调度、将 scorecard 写入 `candidates/{candidate-id}/eval-results/`、清理 worktree。
- 建立 `leaderboard.json`。
- `leaderboard.json` 记录 baseline 的 `composite_score`、`cost_tokens`、候选逐项目分数、`delta_vs_baseline` 与 `status`。
- 成功标准：至少 1 个候选完成 A/B 评估，leaderboard 有 baseline 与候选对比数据，worktree 自动清理，`eval-results` 包含完整 scorecard。

#### M2 实证启发式（empirical priors，来自下游）

> 来源：一个下游项目（Zero Magic `feature/fengshui-mvp`）的 4 个完整 M2 候选实验。证据详见 `EVOLUTION-FROM-ZEROMAGIC.md` §建议 4 + §2.1 / §2.2 / §2.3 / §1.8。**n = 1 项目 × 4 候选**，作为第一批 empirical priors 指导候选选择，不替代未来多项目 held-out 的正式晋升判定（M3 职责）。

**高 ROI 候选特征**（基于 `slim-report-v1`（leaderboard verdict: `promoted`）+ `independent-audit-v1`（manifest status: `proposed`））：

| 特征 | 为什么高 ROI |
|------|------------|
| 改动**协议/流程**（REPORT 模板、verify 步骤、hook schema）| 一次改动影响所有后续轮次；不依赖单个 Worker 的执行质量 |
| 改动**评估维度本身**（scorecard 组成、composite_score 口径）| 直接触及 self-eval bias（参见 FM-5）；换掉坏的量尺比让量尺读数变好容易 |
| 改动**独立性边界**（独立审查者、角色拆分）| 打破 agent 自评的循环；独立审计的价值由 `2026-04-14-full-audit` trace 单独证实——`full-audit/scorecard.json` composite 为 0.72，远低于常规编码轮自评的 ~0.99（这是 full-audit 一次性证据，不是 `independent-audit-v1` 的 A/B 对比结果） |

**低 ROI 候选特征**（基于 `prompt-self-save-v1`（leaderboard verdict: `rejected_search`）+ `lean-prefix-v1`（manifest verdict: `withdrawn`））：

| 特征 | 为什么低 ROI |
|------|------------|
| 依赖 **Worker 服从性**的新约束（"让 Worker 做 X"）| Worker 在 context 压力下会忽略非核心指令；`prompt-self-save-v1` manifest 中 `prompt_md_rate: 0.0`，Worker 完全不执行自保存 |
| **token prefix / 缓存结构** 的微优化 | 在 Opus 4.6 / 4.7 的 1M context 下，prefix 不是瓶颈；`lean-prefix-v1` manifest 估算 "token < 1%"，ROI 评估后**自行 withdrawn** |
| **治表不治里**——改一个症状但不触碰自评盲点 / 信号噪音的根因 | 改完 scorecard 数字好看一点，但相同的盲区会在下一轮换另一种方式出现 |

**反模式（明确不做）**：

- ❌ 把 Worker 服从性问题当执行面问题：如果 Worker 不做某件事，大概率不是 prompt 措辞问题，而是"这件事不该让 Worker 做"（应该改走 hook 或 harness-verify 补齐）
- ❌ 把 prefix 大小当主瓶颈：当 context 窗口足够大时，优化它属于**成本微优化而非质量提升**；除非有真实测量的 cache-creation token 占成本比例 / 具体成本对比数据支持，否则不做
- ❌ 优化前没先问"这是自评盲点引起的吗"：如果根因是盲点，先做独立性改动（如 E5），再谈候选 A/B

**下次提新候选前先问 4 个问题**：

1. 改动落点是**协议 / 流程 / 评估维度**，还是 **Worker 内部约束**？（前者高 ROI）
2. 是否触及 **scorecard 维度或独立性**？（若是加分）
3. 是否**依赖 Worker 服从性**？（若是降级到 low-ROI 类）
4. 当前真正的瓶颈是 **token 成本**还是**信号质量**？（前者多半低 ROI，除非有具体的成本测量数据支持）

### `M3` — `❌ not started` — Harness Search（自动搜索优化）

- 目标：用受控 proposer 自动生成候选，在 search / held-out 双集上评估，通过后再晋升。
- 前置依赖：`M2` 稳定且至少 1 个 held-out repo 已配置。
- Proposer 输入包含最近 N 轮 traces、当前 scorecard 低分维度、leaderboard 中已尝试过的候选、版本化搜索空间边界。
- Proposer 输出 `candidates/{candidate-id}/manifest.json`。
- Proposer 输出对应的 `patches/` 目录。
- Proposer 约束：每次只改一个文件或一个策略点，必须写出 hypothesis，不能修改搜索空间边界之外的文件。
- 切分 `search_repos`，允许 proposer 查看其 traces 与 scorecard。
- 切分 `held_out_repos`，用于验证泛化。
- held-out 最低要求：至少 1 个与 search repo 不同技术栈 / 框架的项目。
- 若没有 held-out repo，则 `M3` 不启动。
- 晋升条件 1：所有 search repos 的 `composite_score` 必须 ≥ baseline。
- 晋升条件 2：所有 held-out repos 的 `composite_score` 必须 ≥ baseline - 0.02。
- 晋升条件 3：`structural_fidelity` 与 `runtime_invariants` 维度不得低于 baseline。
- 晋升条件 4：token 成本必须 ≤ baseline × 1.3。
- 晋升流程：proposer 生成候选 → search repos 评估 → 不提升则 `rejected_search` → 提升后再做 held-out 评估 → held-out / fidelity / cost 任一不满足则拒绝并写明原因 → 全部满足后 promote 到主文件、更新 baseline、记录 learnings、归档候选。
- Reject 后的处理：被拒候选保留在 `candidates/` 中，供 proposer 避免重复。
- Reject 后的处理：连续 3 次 reject 后，暂停 proposer，等待人工 review。
- 第一批允许 proposer 自动修改：`harness/SKILL.md` 中 Worker prompt 模板措辞与 Phase 检查顺序。
- 第一批允许 proposer 自动修改：`execution-policy.md` 中决策阈值、降级策略、并行分组规则。
- 第一批允许 proposer 自动修改：`verification-protocol.md` 中检查项权重与通过阈值、Hook 启用矩阵、context packing / prompt 模板顺序与格式。
- 暂不允许 proposer 自动修改：各 skill 主体内容。
- 暂不允许 proposer 自动修改：`portable/cc-bound` 分类、`state-schema.md` 主结构、路径约束 / 工具约束 / 递归防护等安全边界。

## 8. Anthropic Alignment Items（A1-A17）

- `A1` — `✅ merged to main` — Loop：`gather/act/verify + 中断`；落位 `agent-loop`、`harness` 核心循环。
- `A2` — `✅ merged to main` — Tool：`<20 + defer + ACI`；落位 `tool-authoring`、`agent-tool-budget`。
- `A3` — `✅ merged to main` — 权限：`3+ tier + 外部副作用必问`；落位 `layered-permission`、`command-sandbox`。
- `A4` — `✅ merged to main` — Session：`JSONL + 快照 + resume/fork`；落位 `session-recovery`。
- `A5` — `✅ merged to main` — Compact：`compact / context-reset`；落位 `compact-system`。
- `A6` — `✅ merged to main` — Subagent：独立 context + 摘要回传；落位 `multi-agent-design`。
- `A7` — `✅ merged to main` — Memory：分层 + 索引常驻；落位 `agent-memory`。
- `A8` — `✅ merged to main` — Artifacts：`init.sh + claude-progress.txt + feature_list.json` 启动仪式已落位于 `multi-agent-design`。
- `A9` — `✅ merged to main` — Evaluator：轨迹 + 端态双评估；落位 `eval-driven-design`、`multi-agent-design`。
- `A10` — `✅ merged to main` — MCP：`stdio / HTTP / SSE`；落位 `mcp-runtime`。
- `A11` — `✅ merged to main` — 权限设置分层：`org → personal`；落位 `policy-limits`、`remote-managed-settings`。
- `A12` — `✅ merged to main` — Plan mode：独立子模式；落位 `plan-mode`。
- `A13` — `⏸️ deferred (仓外 online eval aggregation 不属于当前 pack；仓内采集、展示、shape 分析已落地)` — 观测：transcript 分析；落位 `telemetry-pipeline`、`runtime-summaries`、Step 9。
- `A14` — `✅ merged to main` — 压测假设：定期 prune；落位 `architecture-invariants` 的 ASM。
- `A15` — `✅ merged to main` — Transcript 脆弱点：读中间过程失败；落位 `eval-driven-design` Step 9（R5）。
- `A16` — `✅ merged to main` — 失败模式视图：按“要防什么”组织；落位 `FAILURE-MODES.md`。
- `A17` — `✅ merged to main` — 升级 → 简化：不堆砌脚手架；落位 `architecture-invariants`。

## 9. Alignment Follow-ups（来自 [C] 的剩余工作）

- `⏸️ deferred (R7 已否决当轮直接推进)` — T2：为 `harness` 补“长运行工件硬约束”，把 `init.sh`、`claude-progress.txt`、`feature_list.json` 变成真正的必需输出。
- `⏸️ deferred (前置未满足)` — T2 前置 1：澄清命名语义，避免把 Phase 2 守卫误叫成“硬边界 3”。
- `⏸️ deferred (前置未满足)` — T2 前置 2：在 `stage-roadmap.md` 正式加入 `long_running: bool`。
- `⏸️ deferred (前置未满足)` — T2 前置 3：在 `state-schema.md` 正式加入 `last_execution.estimated_sprints`。
- `⏸️ deferred (前置未满足)` — T2 前置 4：与 `harness-verify` 的 `expected-outputs` 机制去重并并轨。
- `⏸️ deferred (前置未满足)` — T2 前置 5：在 `execution-policy.md` 定义 `ESCALATE → 降级为单 sprint` 的具体路径。
- `❌ not started` — T3：广度扫描剩余 40+ skill 的 Anthropic 对齐，形成 gap 矩阵后分批修复。
- `⏸️ deferred (等待真实跨 2-3 sprint 任务)` — T4：用新增 skill 在真实多 sprint 任务上做实证验证并回写反馈。
- `✅ merged to main` — T5：README 导航整合已在 R8 落地。

## 10. 关键决策门

- manifest 字段模型必须单独评审。
- 哪些 skill 保留直连入口必须单独评审。
- `harness-lite` 触发条件必须单独评审。
- command façade 的日志格式必须单独评审。
- namespace / version / lock 方案必须单独评审。
- scorecard 初始权重必须单独评审。

## 11. 完成定义

### 11.1 Foundation DoD

- 阶段 0 根节点已完成 portable-first 改造。
- `skill-catalog.md` / `dependency-graph.md` / README skill 表由 manifest 生成。
- 大多数 worker 默认不允许用户直连。
- 编码轮 trace 来自真实执行记录。
- `harness-verify` 基于真实 artifacts 工作。
- 安装器支持版本化与非破坏式升级。
- 至少 2 个 reference repo 上有稳定 baseline。

### 11.2 Anthropic 对齐出口条件

- 原报告 17 项全部 `✅` 或显式承认 `not applicable`。
- 至少一次真实的 T4 实证反馈，或书面承认当前尚无条件实证。
- `FAILURE-MODES.md` 与对齐路线图持续同步。

## 12. 维护触发器

- 每次 Anthropic 发布新的 harness 相关文章，都要在路线图追加 review 记录并触发 ASM 复审。
- 每次 Claude 大版本升级，都要强制重审 ASM 并更新“上次压测”记录。
- 本计划 6 个月无更新时，标记为 `possibly stale` 并重新对照当前官方写作。
