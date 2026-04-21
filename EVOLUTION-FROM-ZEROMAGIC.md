2026-04-20 Codex 审阅 feature/fengshui-mvp branch HEAD 2537e06 的结果

## 0. 取证范围与方法

- Repo A：`D:/ai/claude-code/harness-skills-pack/`，分支 `main`。
- Repo B：`D:/ai code/Zero_magic/`，分支 `feature/fengshui-mvp`，HEAD `2537e06`。
- 当前工作树可直接读取的主证据包括：`.claude/harness-state.json`、`.claude/harness-lab/traces/2026-04-05...2026-04-20/*`、`.claude/harness-lab/trace-index.json`、`.claude/agents/fengshui-phase-coordinator.md`、`.claude/skills/openspec-*/SKILL.md`。
- `leaderboard.json`、`candidates/*/manifest.json`、`2026-04-14-full-audit/*`、`2026-04-17-round3-audit/*` 不在 `2537e06` 当前工作树内，但可从历史提交 `f9dd02e7ce9b77dd1c443c78ce8bc5bbc456a272` 读取。
- 与 architecture decision 直接相关的提交额外读取了 `12ac80d`、`bdb9566`、`e691df7`、`2537e06`。
- 本报告只依据已读文件与提交摘要下结论；任何从多份证据归纳出的扩展判断都显式标记为 `[speculation]`。

## 1. 已验证模式

### 1.1 `PreWorkerDispatch` 契约注入能显著降低跨层漂移

- `harness-state.json` 已把该模式写成 learnings：`PreWorkerDispatch hook` 自动追加跨层事件名/header 校验提示，直接带来 `agentConfig packaging` 命名对齐满分（证据：`.claude/harness-state.json:199-200`）。
- Stage-7 第一批里，worker-2 明确把 `soul / safety_config / privacy_config` 与 Runtime 消费端做成对照表，而不是只写“注意一致性”（证据：`2026-04-19-stage-7-personality-safety/worker-2-result.md:47-54`）。
- 同一轮 verification 再次从 Gateway 打包键和 Runtime 读键的双侧 grep 验证 snake_case 一致性（证据：`2026-04-19-stage-7-personality-safety/verification.md:88-129`）。
- Stage-7 第二批把这个模式升级成“五字段三层 byte-identical 一致”，验证文件明确给出 manager.ts / internal.py / state.py 三层字段映射表（证据：`2026-04-20-stage-7-personality-safety-batch2/verification.md:61-72`）。
- 批次 scorecard 也把 `cross_layer_consistency` 打到 1.0，并把原因归因到显式契约校验（证据：`2026-04-20-stage-7-personality-safety-batch2/scorecard.json:7-15`）。
- 结论：Repo B 的实证不是“有 hook 就够”，而是“hook 必须把跨层字段/事件/header 变成显式映射表和 file:line 约束”。

### 1.2 真实独立审计能暴露自评盲点

- `2026-04-08-stage-6-deepresearch-r4/scorecard.json` 给出的 composite 是 `0.99`（证据：`2026-04-08-stage-6-deepresearch-r4/scorecard.json:5-13`）。
- 但 `2026-04-14-full-audit/scorecard.json` 在 full audit 下跌到 `0.72`，去重后问题数 `70`（证据：历史提交 `f9dd02e` 中 `.claude/harness-lab/traces/2026-04-14-full-audit/scorecard.json:15-29`）。
- `full-audit` 发现的是结构性问题，不是表面 lint：跨层事件名不匹配、内部 header 不匹配、模块级 dict 泄漏、流式前端性能问题、HMAC timing attack 遗漏（证据：历史提交 `f9dd02e` 中 `worker-4-result.md:38-50`、`worker-1-result.md:17-24`、`worker-3-result.md:21-33`、`worker-2-result.md:17-24`）。
- `harness-state.json` 随后把这些失败直接写进 learnings 与 open_risks，而不是继续沿用高分叙事（证据：`.claude/harness-state.json:135-145`、`.claude/harness-state.json:185-190`）。
- `independent-audit-v1` 的 manifest 也明确把目标写成“把虚高 0.97 拉回真实 0.80-0.90，并把 issue discovery 从约 0 提升到 >0”（证据：历史提交 `f9dd02e` 中 `.claude/harness-lab/candidates/independent-audit-v1/manifest.json:5-21`）。
- 结论：Repo B 已给出强证据，独立审计不是锦上添花，而是修正 score inflation 的必要层。

### 1.3 `smoke_tests + JsonPlusSerializer round-trip` 是高 ROI 元层守门模式

- `2026-04-16` 的元层配置补齐直接把 `smoke_tests` 写入 `harness-state.json`，其中第三条用 LangGraph 官方 `JsonPlusSerializer.dumps_typed/loads_typed` 做真实 round-trip（证据：`.claude/harness-state.json:21-39`）。
- worker-1 说明原始 state 在 baseline `83d7f8e` 就是无效 JSON，并把 `"[trace_missing: ...]"` 修成 `trace_missing_note`，同时新增 `state_serialization` smoke（证据：`2026-04-16-harness-config-fill/worker-1-result.md:30-42`）。
- verify Worker 认为这条 smoke 是“高价值新增”，因为它精确守护了“LangGraph state 必须可序列化”这个约束（证据：`2026-04-16-harness-config-fill/worker-2-result.md:48-52`）。
- verification 报告进一步把它定义为“未来 failure 会精准定位 ZeroMagicState 字段破坏序列化”的回归 gate（证据：`2026-04-16-harness-config-fill/verification.md:35-46`）。
- 同一轮 scorecard 也把这条经验写进 notes，而不是只记成测试通过（证据：`2026-04-16-harness-config-fill/scorecard.json:39-43`）。
- 结论：这不是普通 smoke test，而是“元 schema + 运行时 contract”联动校验的可复用模板。

### 1.4 当 worker 边界冲突时，优先选最小耦合扩展点

- Stage-7 batch2 的 worker-3 明确处在“双重边界”里：不能动 `state.py`，也不能动 `agent_reasoning`，因此选了 `context_assembly()` 返回 dict 新增 `cache_ttl` key 的最小耦合解法（证据：`2026-04-20-stage-7-personality-safety-batch2/worker-3-result.md:10-29`）。
- `harness-state.json` 把这次决策总结成“在 worker 边界冲突时优先选择最小耦合扩展点而不是侵入式改动”，并把它上升为 sprint 拆分正确性的验证（证据：`.claude/harness-state.json:201-202`）。
- 这说明 Repo B 的成功经验不是“把任务尽量切小”这么抽象，而是“切小之后要为每个 slice 设计低耦合接缝”。

### 1.5 确定性路由覆盖 LLM verdict，是多 agent workflow 的稳定器

- Stage-6 deepresearch r2 中 reviewer 明确实现三路路由，并注明“overrides LLM verdict”（证据：`2026-04-08-stage-6-deepresearch-r2/worker-2-result.md:6-12`）。
- `harness-state.json` 把这条经验写成 architecture decision：LLM 负责评分与识别 issues，路由决策必须硬编码在代码里（证据：`.claude/harness-state.json:64-65`）。
- 同一 learnings 条目把它表述为“避免 LLM 随机输出导致路由不稳定”的系统性教训（证据：`.claude/harness-state.json:183-184`）。
- 结论：Repo B 验证了 `multi-agent-design` 里的 Evaluator 思路，但实际落地时增加了“路由层 deterministic override”这一步。

### 1.6 “单一事实源 + codegen + drift CI”比双栈手工同步可靠

- Stage-7 worker-3 把 Python `pii_detector.py` 明确设为 single source of truth，再生成 `pii_patterns.generated.ts`（证据：`2026-04-19-stage-7-personality-safety/worker-3-result.md:16-35`）。
- 同一 worker 要求 TS header 带 `SOURCE_HASH`，并把 `--check` 做成 CI 阻断（证据：`2026-04-19-stage-7-personality-safety/worker-3-result.md:27-35,48-53`）。
- verification 复跑 `python scripts/codegen/pii_patterns_to_ts.py --check` 并拿到 0 漂移（证据：`2026-04-19-stage-7-personality-safety/verification.md:110-119`）。
- `harness-state.json` 把它正式记为 architecture decision，而不是一次性实现细节（证据：`.claude/harness-state.json:71-72`）。
- 结论：这是 Repo B 对“跨语言结构保真”的真实可复制模式。

### 1.7 “先 spike/grep 现状，再写 spec”是 Stage-7 的核心复盘

- Stage-7 worker-1 spike 发现 Langfuse v4 的 mask 不是 `@observe(mask=...)`，而是 `Langfuse(mask=fn)`（证据：`2026-04-19-stage-7-personality-safety/worker-1-result.md:11-18,37-39`）。
- `harness-state.json` 把这个经验抽象成“第三方 SDK API 假设必须先 spike 验证而不是从文档推测”（证据：`.claude/harness-state.json:198-199`）。
- 同一 state 还记录了更一般的结论：Round 1 的 18 个 finding 里有 6 个 blocking 是 spec 假设了不存在的代码/接口，因此“现状与缺口分析”必须逐行挂 `file:line` 引用（证据：`.claude/harness-state.json:194-195`）。
- 结论：Repo B 已经从 spec 失真里提炼出可迁移的“code-first evidence”写法。

### 1.8 Report 模板“瘦身”是真正被验证过的 M2 候选

- `leaderboard.json` 把 baseline 直接定义为 `slim-report-v1 (promoted 2026-04-08)`（证据：历史提交 `f9dd02e` 中 `.claude/harness-lab/leaderboard.json:3-23`）。
- 它给出的 promoted 理由很具体：`state` 更新遵从率从约 `60%` 提升到 `100%`，composite 从 baseline `0.97` 提升到 `0.99`（证据：历史提交 `f9dd02e` 中 `.claude/harness-lab/leaderboard.json:33-45`）。
- Repo A 当前 `skills/harness/SKILL.md` 已经把 Phase 4 REPORT 标成“精简版 — M2 候选 slim-report-v1”（证据：`skills/harness/SKILL.md:599-636`）。
- 结论：这是少数已经从真实 candidate 试验反向进入主 skill 的经验。

## 2. 被拒、撤回或待证的假设

### 2.1 `prompt-self-save-v1`：靠 Worker 自觉自保存 prompt，不成立

- 假设是“在 Worker prompt 固定前缀末尾追加一条自保存指令，可以把 `prompt.md` 产出率从 30% 提到 >80%”（证据：历史提交 `f9dd02e` 中 `.claude/harness-lab/candidates/prompt-self-save-v1/manifest.json:5-18`）。
- 实际结果是 `rounds_tested=2`，`prompt_md_rate=0.0`，Worker 完全忽略这条指令（证据：同文件 `:19-28`）。
- `leaderboard.json` 也把它标成 `rejected_search`，拒绝理由与 manifest 一致（证据：历史提交 `f9dd02e` 中 `.claude/harness-lab/leaderboard.json:24-31`）。
- 这是否定了“把 trace 生成责任继续压给 Worker 文本服从性”的路线。

### 2.2 `lean-prefix-v1`：继续压 prompt 前缀 token，不是当前瓶颈

- 假设是把固定前缀从 42 行压到约 25 行，减少 token 约 40%，且不降 scorecard（证据：历史提交 `f9dd02e` 中 `.claude/harness-lab/candidates/lean-prefix-v1/manifest.json:5-6`）。
- 结果没有进入实测，直接被 `withdrawn`，理由是 1M context 下节省不到 1%，结构保真风险大于收益（证据：同文件 `:7-9`）。
- `leaderboard.json` 也同步记录“拒绝为优化而优化”的 ROI 原则（证据：历史提交 `f9dd02e` 中 `.claude/harness-lab/leaderboard.json:47-56`）。
- 这是否定了“继续做前缀微优化”优先级。

### 2.3 `independent-audit-v1`：已提案，但还不是已晋升基线

- manifest 里它还是 `status: proposed`，还没有 promotion 证据（证据：历史提交 `f9dd02e` 中 `.claude/harness-lab/candidates/independent-audit-v1/manifest.json:1-21`）。
- 它的提出不是空想，而是直接由 full-audit 低分与问题发现率支撑（证据：历史提交 `f9dd02e` 中 `.claude/harness-lab/traces/2026-04-14-full-audit/scorecard.json:15-34`）。
- 但就当前 ZeroMagic 证据来说，它仍应被视为“高置信方向、未完成主线晋升”的候选，而不是已验证基线。

### 2.4 项目级 shadow harness：自动调用解锁方案被提交后又回滚

- `12ac80d` 的意图是复制一套项目级 `.claude/skills/harness/`，移除 `disable-model-invocation: true`，从而让本项目会话可自动调起 harness。
- 但 `bdb9566` 立刻回滚了整个 shadow，理由是 Claude Code skill loader 对 `disable-model-invocation` 采用跨源 OR 语义，project-level 无法覆盖 user-level 的禁用位（证据：提交 `bdb9566` 摘要）。
- 回滚提交还明确写出实测结果：Skill 列表里能看到 harness，但调用时仍返回 `cannot be used due to disable-model-invocation`（证据：提交 `bdb9566` 摘要）。
- 紧接着，Repo B 转向 `fengshui-phase-coordinator` subagent 路线（证据：提交 `e691df7` 摘要）。
- 结论：这是否定了“项目级 shadow skill 是自动编排通路”的假设。

## 3. 与 skills pack 的对比：缺口与“方向对但未锚定”项

### 3.1 已有正确方向

- Repo A 已经把 `trace`、`scorecard`、`structural_fidelity`、`proof plane` 放到核心位置（证据：`UNIFIED-ROADMAP.md:16-23`、`UNIFIED-ROADMAP.md:352-364`）。
- Repo A 已经把 `self-eval blind spot` 显式列成 failure mode，并把 `multi-agent-design` + `harness-verify` 作为主要解法（证据：`FAILURE-MODES.md:24-35`）。
- Repo A 已经把 `slim-report-v1` 合入 `skills/harness/SKILL.md` 的 REPORT 阶段（证据：`skills/harness/SKILL.md:599-636`）。

### 3.2 现实中已出现、但 Repo A 还没有写透的模式

- Repo A 的 `PreWorkerDispatch` 还是通用 hook API：允许“追加 prompt / 缩小 target_paths / skip worker”（证据：`skills/harness/SKILL.md:385-395`）。
- Repo B 的实证模式更具体：要把跨层字段、事件名、header 直接写成对照表，最好挂 file:line（证据：`2026-04-19-stage-7-personality-safety/worker-2-result.md:47-54`、`2026-04-20-stage-7-personality-safety-batch2/verification.md:61-72`）。
- Repo A 的 REPORT 仍假设“verification/scorecard/commands.log/diff.patch 不需要 Coordinator 手写”（证据：`skills/harness/SKILL.md:632-636`）。
- 但 Repo B 在 batch2 遇到了 verify Worker 因 trace 目录日期错位无法写入、最后由 Coordinator 补齐 trace 文件的案例（证据：`2026-04-20-stage-7-personality-safety-batch2/scorecard.json:31-44`）。
- Repo A 的 M2 文档仍是 generic candidate pipeline；Repo B 已经给出具体的“被拒 / promoted / withdrawn / proposed”样本及拒绝理由（证据：`UNIFIED-ROADMAP.md:380-414` 对比历史提交 `f9dd02e` 中 `leaderboard.json:24-56` 与四个 manifest）。
- Repo A 的 `harness-lite` 只覆盖“单叶子模块、<=2 文件、单 worker 快速路径”（证据：`skills/harness-lite/SKILL.md:15-34,76-89`）。
- Repo B 实际为风水 vertical 新引入的是“plan-only / execute 双模式 + 父会话持有 APPROVE 门 + OpenSpec artifact bridge + 多角色 worker 池”的 phase coordinator，而不是 lite path（证据：`.claude/agents/fengshui-phase-coordinator.md:3-4,24-27,38-58,94-120`，提交 `e691df7`）。

### 3.3 “方向对，但还没有现实锚点”的 skill / 文档

- `harness-lite` 的边界设计是清楚的，但在本次 Repo B 证据集中没有看到任何一轮 trace 真的通过 `harness-lite` 跑风水 Phase；实际采用的是独立 subagent coordinator（证据：`skills/harness-lite/SKILL.md:15-34` 对比 `.claude/agents/fengshui-phase-coordinator.md:15-27`）。
- `multi-agent-design` 的 Planner / Generator / Evaluator 解释非常完整，但没有 phase-scoped、parent-approved、external-spec-driven 的 coordinator 变体（证据：`skills/multi-agent-design/SKILL.md:330-470`）。
- `UNIFIED-ROADMAP.md` 仍把 `P3/M0/M1/M2/M3` 标成未启动主线，而 ZeroMagic 的单仓历史里已经跑出一个“小规模 M2 样机”（候选、leaderboard、promoted baseline），但这些实证尚未回流到 Repo A（证据：`UNIFIED-ROADMAP.md:305-414` 对比历史提交 `f9dd02e` 中 `leaderboard.json:3-56`）。
- `FAILURE-MODES.md` 已经命名了自评盲点，但还没有把 `0.99 → 0.72` 的 full-audit 反转案例写成具体索引样本（证据：`FAILURE-MODES.md:24-35` 对比历史提交 `f9dd02e` 中 `2026-04-14-full-audit/scorecard.json:15-29`）。

## 4. `fengshui-phase-coordinator.md` 分析

### 4.1 它更像什么

- 该文件自述“模仿 harness skill 的 Coordinator 协议，但不是 harness skill 本身，不写 harness-lab/traces，APPROVE 门由主会话承担”（证据：`.claude/agents/fengshui-phase-coordinator.md:17-20`）。
- 它强制自己“不写业务代码，必须派 Worker”，这与 harness Coordinator 的“Coordinator 禁止直接做实质工作”是一致的（证据：`.claude/agents/fengshui-phase-coordinator.md:22-27`；`skills/harness/SKILL.md:61-69`）。
- 但它把调用契约改成了 `mode: plan-only | execute`，并把 `approved_plan` 作为父会话传入参数（证据：`.claude/agents/fengshui-phase-coordinator.md:28-37`）。

### 4.2 它不是 `Planner/Generator/Evaluator` 的直接子模式

- `multi-agent-design` 的三角色模式围绕的是跨 sprint 长任务、`sprint-contract.json`、`feature_list.json`、`evaluator-report.md` 等工件（证据：`skills/multi-agent-design/SKILL.md:348-382`）。
- `fengshui-phase-coordinator` 不维护这些工件，也不把 Generator / Evaluator 作为独立长期角色实例来运作；它做的是单 change、单 phase 的 `SCAN + PLAN` 或 `EXECUTE + REPORT`（证据：`.claude/agents/fengshui-phase-coordinator.md:38-58,94-186`）。
- `[speculation]` 更准确的归类是“phase-scoped nested coordinator”，它借用了三角色哲学里的“禁止自评 / 必须外置验证 / 必须拆角色池”，但并不直接实例化 Planner / Generator / Evaluator 三工件闭环。

### 4.3 它与 `harness-lite` 的差异不是轻重，而是维度不同

- `harness-lite` 解决的是叶子任务：<=2 文件、无公共接口变更、无并发 worker、必要时最多追加 verify（证据：`skills/harness-lite/SKILL.md:15-34,76-89`）。
- `fengshui-phase-coordinator` 解决的是 phase orchestration：它默认有 Worker 分配表、并行度分层、跨层契约校验、Phase 末验证命令、REPORT 产物路径（证据：`.claude/agents/fengshui-phase-coordinator.md:58-91,98-184`）。
- `harness-lite` 是 user-facing fast path。
- `fengshui-phase-coordinator` 是 subagent-facing orchestration cell，且 APPROVE 门外置给父会话（证据：`.claude/agents/fengshui-phase-coordinator.md:20,214-215`）。
- 因此它不是 `harness-lite` 的“加重版”，也不是 `harness` 的“减重版”；它是“外部 spec 系统 + 内部 worker 池”之间的桥接层。

### 4.4 它与 `multi-agent-design` 的关系

- `multi-agent-design` 里有两个相关思想：
- 第一，Coordinator 可以只是“prompt + 强制异步 + 通知消息”，不必是重型执行引擎（证据：`skills/multi-agent-design/SKILL.md:139-152,301-307`）。
- 第二，长任务要靠角色分离来对抗 self-eval blind spot（证据：`skills/multi-agent-design/SKILL.md:330-346`）。
- `fengshui-phase-coordinator` 继承了第一条，却没有采用第二条的长工件体系。
- `[speculation]` 最合适的表示方式是：
- 在 `multi-agent-design` 中新增一个“nested coordinator / parent-approved phase coordinator”小节。
- 另起一个 portable skill，专讲“外部 workflow/spec 系统驱动的 phase 协调”，不要塞进 `harness-lite`。

## 5. 11 个 `openspec-*` skills 的泛化价值

### 5.1 值得回流的通用模式

#### 模式 A：用外部工具的 JSON introspection 驱动流程，而不是硬编码工件名

- `openspec-apply-change` 先读 `openspec status --json` 拿 `schemaName`，再读 `openspec instructions apply --json` 拿 `contextFiles`，由 CLI 决定后续工件集合（证据：`openspec-apply-change/SKILL.md:27-57`）。
- `openspec-continue-change` 也是先看 artifact 状态的 `ready / blocked / done`，再决定下一步，而不是把顺序写死（证据：`openspec-continue-change/SKILL.md:34-57,76-82`）。
- `openspec-propose` 与 `openspec-ff-change` 则用 `applyRequires` 决定什么时候“已经足够进入 implementation”（证据：`openspec-propose/SKILL.md:44-76`；`openspec-ff-change/SKILL.md:35-67`）。
- 这类“外部系统给出 machine-readable workflow state，内部 coordinator 只负责解释和执行”的桥接模式可以泛化到任何 spec/tool-backed workflow。

#### 模式 B：`contextFiles` 桥接比约定固定文件名更健壮

- `openspec-apply-change` 明说“使用 CLI 输出的 `contextFiles`，不要假设固定文件名”，并允许 schema 不同时上下文集合不同（证据：`openspec-apply-change/SKILL.md:52-57,149`）。
- `openspec-verify-change` 也复用 `instructions apply --json` 返回的 `contextFiles` 读取所有可用 artifacts（证据：`openspec-verify-change/SKILL.md:36-49`）。
- `[speculation]` 这正适合抽象成“external-spec-system x LLM workflow bridge”的通用模式，因为它把 repo-specific artifact naming 交还给系统接口。

#### 模式 C：验证维度做成 `Completeness / Correctness / Coherence`

- `openspec-verify-change` 初始化报告时先把验证分成三维，再按 `CRITICAL / WARNING / SUGGESTION` 产出（证据：`openspec-verify-change/SKILL.md:44-52,53-109,124-159`）。
- 这与 Repo A `harness-verify` 的 `build_lint_typecheck / smoke_tests / runtime_invariants / structural_fidelity / verification_coverage` 并不冲突；前者更偏 artifact/spec 视角，后者更偏 execution/runtime 视角。
- `[speculation]` 这可以回流为 `harness-verify` 的“artifact-facing explanation layer”，但不该替代现有 scorecard 维度。

#### 模式 D：delta spec sync 的“智能合并而非全文替换”

- `openspec-sync-specs` 明确把自己定义成 `agent-driven` operation，并强调 delta 代表“intent, not wholesale replacement”（证据：`openspec-sync-specs/SKILL.md:12-18,48-67,108-113`）。
- `openspec-bulk-archive-change` 更进一步，把冲突解析建立在“读 delta specs + 搜代码看哪个 change 真被实现了”之上（证据：`openspec-bulk-archive-change/SKILL.md:62-79,123-126,165-195`）。
- 这类“文档合并必须回看代码证据”的策略，与 Repo B Stage-7 的 code-first spec 复盘高度一致。

#### 模式 E：教学型 workflow 需要显式过渡语法

- `openspec-onboard` 要求 `EXPLAIN → DO → SHOW → PAUSE` 节奏，并在关键节点强制暂停让用户确认（证据：`openspec-onboard/SKILL.md:544-549`）。
- 这个模式对生产 harness 主链不重要，但对“如何教会团队使用 workflow”是有价值的辅助层。

### 5.2 不值得直接回流的 OpenSpec-specific 细节

- `openspec/changes/<name>/`、`specs/<capability>/spec.md`、`.openspec.yaml` 这些路径约定本身不值得进入 harness pack。
- `ADDED / MODIFIED / REMOVED / RENAMED Requirements` 这套 delta spec grammar 是 OpenSpec 专属语法，不宜强塞成通用文档协议（证据：`openspec-sync-specs/SKILL.md:28-38,79-106`）。
- `archive/YYYY-MM-DD-<name>/` 与“归档前是否 sync main specs”是 OpenSpec 的生命周期语义，不值得抽象成 harness 主线（证据：`openspec-archive-change/SKILL.md:53-83,94-114`）。
- `openspec-onboard` 的教学叙事不属于 execution/control plane，本质上是 onboarding content（证据：`openspec-onboard/SKILL.md:2-8,37-49,544-549`）。
- `openspec-new-change` 关于默认 schema 与 schema-specific first artifact 的细则，也属于 OpenSpec CLI 契约，不是可迁移能力本体（证据：`openspec-new-change/SKILL.md:29-31,46-54`）。

### 5.3 本轮对 11 个 skill 的归类结论

- `openspec-apply-change`：值得回流“status/instructions/contextFiles”桥接模式。
- `openspec-continue-change`：值得回流“artifact state machine”桥接模式。
- `openspec-propose`：值得回流“applyRequires 驱动 artifact 生成停止条件”。
- `openspec-ff-change`：与 propose 共用同一桥接模式，细节不必单独回流。
- `openspec-verify-change`：值得回流“三维 artifact-facing 验证框架”。
- `openspec-sync-specs`：值得回流“intelligent merge + code evidence”原则。
- `openspec-archive-change`：大部分是 OpenSpec lifecycle，不建议回流主 pack。
- `openspec-bulk-archive-change`：值得回流“冲突解析先看代码证据”，但不必回流归档细节。
- `openspec-explore`：更像 workflow 前置探索，不是 execution plane 核心。
- `openspec-onboard`：教学用，建议留在 OpenSpec 侧。
- `openspec-new-change`：CLI scaffolding 细节，不建议回流主 pack。

## 6. 优先演进建议

### 建议 1：把“契约优先的 PreWorkerDispatch 注入”升格为一等模式

- 名称：`Contract-First PreWorkerDispatch`
- 影响范围：`skills/harness/SKILL.md`、`skills/harness/harness-hooks-schema.md`
- 动机：Repo A 目前只定义了“hook 可追加 prompt / 缩小 target_paths”的 generic 能力，Repo B 的实证已经表明高价值部分是“显式对照表 + file:line 双端约束”。
- 直接证据：
- 提交 `0fb658b232048387e8e03b754e868b2ce5d5e0bc`
- 提交 `9f1b36523aa2b9f1c536af8360dc4b84fefde3c2`
- `skills/harness/SKILL.md:388-395`
- `2026-04-19-stage-7-personality-safety/worker-2-result.md:47-54`
- `2026-04-19-stage-7-personality-safety/verification.md:121-129`
- `2026-04-20-stage-7-personality-safety-batch2/verification.md:61-72`
- `.claude/harness-state.json:199-200`
- Effort：`single-round`
- Risk：`low`
- 建议落点：
- 在 hook schema 里新增推荐字段，如 `contract_checks` 或 `cross_layer_pairs` 的示例。
- 在 harness 示例 prompt 中直接展示“字段名 / 事件名 / header / schema 两端 file:line 对照表”模板。
- 预期收益：减少跨层命名漂移，且把成功经验从 Repo B 回流到 pack 主线。

### 建议 2：显式记录“shadow harness 不可行”，并引入可迁移的 phase-coordinator 模式

- 名称：`Document Shadow Failure, Add Phase-Coordinator Pattern`
- 影响范围：`skills/multi-agent-design/SKILL.md` + 新 skill（建议名 `[speculation] skills/spec-phase-coordinator/SKILL.md`）
- 动机：Repo B 已经跑过一轮失败路线：项目级 shadow harness (`12ac80d`) 很快被 `bdb9566` 回滚，随后转向 `e691df7` 的 subagent coordinator。
- 直接证据：
- 提交 `12ac80d327c8e3812c3af7186d6b2fcb1519b9a1`
- 提交 `bdb956606ce593c6108bf8ff56b232dc0e91212e`
- 提交 `e691df7decba0282dfa85b34c28ddb1df56401b8`
- `.claude/agents/fengshui-phase-coordinator.md:3-4,17-20,24-27,28-37,94-120`
- `skills/multi-agent-design/SKILL.md:139-152,301-307,330-346`
- Effort：`multi-round`
- Risk：`medium`
- 建议落点：
- 在 `multi-agent-design` 里新增“nested coordinator / parent-approved coordinator”小节。
- 明确写出“不要用 project-level shadow 去绕过 disable-model-invocation；优先用 subagent coordinator”。
- `[speculation]` 新 skill 应抽象成“外部 workflow/spec 系统驱动的 phase 协调”，不要写死 OpenSpec。

### 建议 3：把 state/trace 卫生门槛写进主链，而不是只留在 learnings

- 名称：`Meta-Harness Hygiene Gates`
- 影响范围：`skills/harness/SKILL.md`、`skills/harness-verify/SKILL.md`
- 动机：Repo B 已经暴露出 3 类卫生问题：历史 state JSON 静默损坏、`trace-index.json` 未跟上最新 trace、verify Worker 因 trace 目录日期错位无法写回。
- 直接证据：
- 提交 `ea0df3cd3fce25388e1e3f09125ef11d15c1e1ea`
- 提交 `9f1b36523aa2b9f1c536af8360dc4b84fefde3c2`
- `2026-04-16-harness-config-fill/worker-1-result.md:30-42`
- `2026-04-16-harness-config-fill/verification.md:24-31,45-46,79-89,182-188`
- `2026-04-20-stage-7-personality-safety-batch2/scorecard.json:31-44`
- `.claude/harness-lab/trace-index.json:1-14`
- `.claude/harness-state.json:113-123`
- `skills/harness/SKILL.md:632-636`
- Effort：`single-round`
- Risk：`low`
- 建议落点：
- REPORT 前强制 `python -m json.tool` 校验 `harness-state.json` 与 hook 配置。
- 每轮结束后把 `trace-index.json` 刷新作为硬性步骤，而不是“有 traces 时按需维护”。
- `harness-verify` 写 trace 失败时，允许 Coordinator 进入 documented fallback 模式，而不是依赖隐式补救。

### 建议 4：把真实 M2 候选 heuristics 回写到 proof-plane 文档

- 名称：`Backport Real M2 Heuristics`
- 影响范围：`UNIFIED-ROADMAP.md`、`EXECUTION_PLAN.md`、`skills/harness/SKILL.md`
- 动机：Repo A 目前对 M2 的描述仍偏 generic；Repo B 已经给出清晰的“哪些假设值得测，哪些不值得测”的具体经验。
- 直接证据：
- 提交 `f9dd02e7ce9b77dd1c443c78ce8bc5bbc456a272`
- `UNIFIED-ROADMAP.md:380-414`
- 历史提交 `f9dd02e` 中 `.claude/harness-lab/leaderboard.json:24-56`
- 历史提交 `f9dd02e` 中 `.claude/harness-lab/candidates/prompt-self-save-v1/manifest.json:19-28`
- 历史提交 `f9dd02e` 中 `.claude/harness-lab/candidates/lean-prefix-v1/manifest.json:5-9`
- 历史提交 `f9dd02e` 中 `.claude/harness-lab/leaderboard.json:33-45`
- Effort：`single-round`
- Risk：`low`
- 建议落点：
- 在 M2 文档中新增“高 ROI 候选特征 / 低 ROI 候选特征”。
- 明确写出：不要把 Worker 服从性问题（prompt-self-save）误当执行面问题；不要把 prefix 微优化当主瓶颈；优先优化 REPORT / verify 协议。
- 这样 P3/M2 不再只是蓝图，而是带有第一批 empirical priors。

### 建议 5：把独立审计从“可选附加”升级为“风险触发默认”

- 名称：`Risk-Triggered Independent Audit`
- 影响范围：`skills/harness-verify/SKILL.md`、`FAILURE-MODES.md`、`skills/harness/SKILL.md`
- 动机：Repo B 的 full audit 已证明自评盲点是真实而且昂贵的；但 `independent-audit-v1` 还停留在 proposed。
- 直接证据：
- 提交 `f9dd02e7ce9b77dd1c443c78ce8bc5bbc456a272`
- 历史提交 `f9dd02e` 中 `.claude/harness-lab/traces/2026-04-14-full-audit/scorecard.json:15-34`
- 历史提交 `f9dd02e` 中 `.claude/harness-lab/candidates/independent-audit-v1/manifest.json:5-21`
- `.claude/harness-state.json:185-190`
- `FAILURE-MODES.md:24-35`
- `skills/harness-verify/SKILL.md:98-129,204-216`
- Effort：`multi-round`
- Risk：`medium`
- 建议落点：
- 当命中高风险信号时默认加 independent audit：跨层接口、权限/安全、全栈 diff、阶段切换、或 `structural_fidelity < 1.0`。
- 不必每轮都全量审计，但要把“何时触发独立审计”写成明确 admission rule。
- 这样既保留运行速度，也把 full-audit 的教训固化为流程规则。

## 7. 总结判断

- Repo B 已经不只是“拿 skills pack 落地一次”，而是产生了足以反哺 skills pack 的真实进化证据。
- 最强的三条证据链分别是：
- `PreWorkerDispatch` 契约注入如何把跨层一致性打到 1.0。
- full-audit 如何把自评高分纠偏成真实质量画像。
- 候选系统如何给出 promoted / rejected / withdrawn 的具体 ROI 规则。
- Repo A 当前最大的缺口不是缺更多 skill，而是缺把这些实战 heuristics 回写成主线规则。
- `[speculation]` 如果下一轮只做文档回流而不改任何 skill 主体，价值最高的顺序应是：先补 M2 heuristics 和 shadow-harness 失败，再补 phase coordinator pattern，再决定是否新建 portable skill。

## 8. 未读/不可直接读取项说明

- 未发现不可读的 Repo A 指定文件。
- Repo B 的 `leaderboard.json`、`candidates/*`、`2026-04-14-full-audit/*`、`2026-04-17-round3-audit/*` 在 `2537e06` 当前工作树中未直接列出，但其历史版本已从 `f9dd02e` 读取并用于本报告。
- 本报告没有修改 Repo A 任一 skill 文件，也没有修改 Repo B 任一文件。

---

## 9. 2026-04-21 更新：Phase 5 Archive-Ready 实战观察

> **上下文**：原报告 §1-§8 基于 2026-04-20 `feature/fengshui-mvp` HEAD = `2537e06` 撰写。用户在该分支继续开发 1 天，推 18 commits 完成 `add-fengshui-demo-workbench` OpenSpec change 的 Phase 1-5 + Archive-Ready 验证（HEAD = `b930fea`）。本节仅**追加新证据**，不修改原报告 §1-§7 结论。

### 9.1 新增证据：W-VERIFY-NEW-1（LLM 字段映射失败 → 代码层修复）

**场景**：Phase 5 手工联调，华泰风水评估 case
- formSnapshot 6 字段全填，qwen-plus persona/guard prompt 仍按"缺失清单"返回 307 字节占位输出
- 根因：LLM 无法稳定建立**英文 key → 中文 label 映射**

**修复方案 A（代码层）**：
- Runtime 新增 `parse_form_snapshot_from_message()` + `detect_required_fields()`
- `MISSING_FIELD_GUARD_PROMPT_WITH_DETECTION` 两态 prompt 把"已检测到字段 / 检测为缺失字段"显式注入
- LLM 不再做映射，只做语义判断
- 结果：华泰 case run_id `2121318c...` 端到端见证 `code-layer filled=6 missing=0`，runtime 测试从 28 → 39 全绿

**直接证据**：
- 提交 `9e9c815` 修复: Phase 5 联调 P0 - 流水线 artifact + LLM 字段识别
- 提交 `1970043` Archive-Ready 审计追加 W-VERIFY-NEW-1 收口记录
- `docs/audit/2026-04-21_archive_ready_final.md` W-VERIFY-NEW-1 段

**对 E4（M2 实证启发式）的增量**：
- 原 E4 低 ROI 反例 `prompt-self-save-v1` 讲的是"让 Worker 自保存 prompt 失败"——Worker 执行侧问题
- W-VERIFY-NEW-1 是同一类失败模式的**新变种**——不是 Worker 不愿做，是 LLM 做不稳（英文→中文语义映射）
- [speculation] 基于 2 个样本（`prompt-self-save-v1` + W-VERIFY-NEW-1）推断的**共同模式**：凡是让 LLM 做**确定性机械映射**（字段名、枚举值、类型标签）的事，多半该下移到代码层。样本基数小，作为启发式可参考，不作为硬规则
- 建议 UNIFIED-ROADMAP §M2 低 ROI 特征表追加一行："依赖 LLM 做确定性机械映射（字段名 / 枚举 / 类型标签）"

### 9.2 Archive-Ready 用 general-purpose Worker 做独立评审（E5 活体证据）

**审查机制原文**（见 `docs/audit/2026-04-21_archive_ready_final.md` 开头）：
> 审查人：独立 general-purpose Worker + 主会话现场验证命令见证

**对 E5（独立审计作为风险触发默认）的含义**：
- E5 当前是 "multi-round / medium / proposed"
- **Repo B 确实在用独立 agent 做 change-level 审，但用的是 general-purpose agent，不是 `harness-verify` skill**
- 说明：
  - [speculation] E5 的必要性有**初步实战支持**——Archive-Ready 报告显式使用独立评审人。但需要说明：**这是本项目 1 次选择**，不是 OpenSpec `archive` 工作流的强制要求（已核对 `.claude/commands/opsx/archive.md` 无独审硬要求），因此不能从此样本推广到"E5 必然在所有项目都被需要"
  - 事实：现有 `harness-verify` skill 没被选中承担这个角色
- [speculation] 未被选中的原因**可能是** `harness-verify` 针对 **Phase 级**验证，而 Archive-Ready 是 **change 级**（跨 Phase）。此推测未经多项目对照验证
- **浮出的设计问题**：`harness-verify` 粒度是否需要拆成 Phase-level 和 Change/Stage-level 两档？[speculation] 如果补 change-level mode（跨 Phase 聚合 diff、跨 spec 交叉检查），**可能**替代 general-purpose agent 的角色——但这只是从接口能力角度的初步推断，未验证其 prompt 质量是否足够匹配现有 general-purpose 的审查严格度
- 建议：做 E5 前先回答这个粒度问题，但不急着把 Archive-Ready 的单次做法升级成普遍规则

### 9.3 fengshui-phase-coordinator 模式完整验证（E2 证据加厚）

18 commits 按 Phase 1-5 节奏完整推进：

| Phase | 关键 commits |
|-------|-------------|
| Phase 1 数据模型与契约 | `e8cd20e` `2537e06` |
| Phase 2 Gateway 业务 API | `23d8180` |
| Phase 3 Runtime Agent | `7cad4dd` |
| Phase 4 Frontend 工作台 + W1/W2/W5 修复 | `65af314` `130de92` `d04f9eb` |
| Phase 5 最终收口 + W-VERIFY-NEW-1 | `6677611` `9e9c815` `1970043` `3172870` `b930fea` |

每 Phase 有独立验证 + Codex 审查；最终 Archive-Ready 三维验收全绿、OpenSpec change 正式归档。

**对 E2（phase-coordinator skill）的含义**：
- 原评估 "multi-round / medium"，基于单个 `fengshui-phase-coordinator.md` 文件推断
- 新证据：**完整 5 Phase × 35 tasks 的 successful run**（单项目单 change）
- APPROVE 由父承担 / 服务单 change / 不写 harness-lab trace 的设计都**没出问题**，一次跑通到 Archive
- [有限样本] **Risk 初步从 medium 降到 low-medium**——基于 **1 个项目 × 1 个 change × 5 Phase** 的 successful run；跨项目 / 跨 vertical 验证未做，所以保留"初步"限定。与 §9.6 的"未重新全量读 harness-lab"保持一致口径
- [speculation] `fengshui-phase-coordinator.md` 可作为 reference implementation 直接引用，不用从 0 抽象——此判断依赖未来抽象者确认该文件的 vertical 特定假设（硬编码模型 / 单 change 服务域）能否被清晰剥离，当前未做可移植性审核

### 9.4 Vertical-specific scorecard 维度

Archive-Ready 用 **完整性 / 正确性 / 一致性** 三维，不是 `harness-verify` 的 6 维（`build_lint_typecheck / smoke_tests / runtime_invariants / structural_fidelity / verification_coverage / code_quality`）。

**直接证据**：`docs/audit/2026-04-21_archive_ready_final.md` "总评" 表

**新问题浮出**（[speculation] 基于单次 Archive 观察推断）：`harness-verify` 6 维**可能**覆盖不了"跨层常量语义对齐"（本次 Archive 提到 `SLUG / 6 必填字段 / DISCLAIMER 文案 / 11 错误码` 的语义一致性）这类业务级一致性。单次样本不足以证明通用缺口，仅作为方向性观察。

[speculation] 可能需要**可扩展 scorecard schema**：6 个通用维度 + vertical 自定义扩展维度。E5 或独立 E6 可以考虑此方向。

### 9.5 对 §6 优先级推荐的更新（不覆盖原文，只补增量）

| E# | 原评估 | 新评估 | 主要依据 |
|----|--------|--------|---------|
| E2 phase-coordinator | multi-round / medium | multi-round / **low-medium** | 9.3 — 完整 5 Phase successful run |
| E4 M2 启发式 | ✅ 已合（PR #19）| 可追加"LLM 确定性映射"低 ROI 反例 | 9.1 — W-VERIFY-NEW-1 |
| E5 独立审计风险触发 | multi-round / medium | multi-round / medium（**新设计问题**：Phase-level vs Change-level 粒度） | 9.2 — Archive-Ready 用 general-purpose agent 而非 harness-verify |
| [new] E6? Vertical scorecard 扩展 | — | 暂列为 speculation，等第二个 vertical 项目再决定是否立项 | 9.4 |

**综合下一步建议**：
1. **小增量**：把 W-VERIFY-NEW-1 的"LLM 确定性映射"反例追加到 UNIFIED-ROADMAP §M2 低 ROI 表（5 分钟）
2. **中增量**：启动 E2，用 `fengshui-phase-coordinator.md` 作为 reference implementation
3. **启动 E5 前先回答**：`harness-verify` 是否要分 Phase-level 和 Change-level 两档粒度？[speculation] 这个设计决策**可能**影响 E5 的实现边界——基于 §9.2 的单次观察推断，尚未经多项目验证

### 9.6 本次更新的限制

- 本节基于 2026-04-21 的 git log + Archive-Ready audit 报告 + OpenSpec specs 目录，未重新全量读 harness-lab
- `.claude/harness-state.json` 在 fengshui-mvp 分支与 `2537e06` 一致（未新增 harness 轮次），18 commits 全部在推进 OpenSpec 的 Phase 1-5，不是 harness stage
- [speculation] 若 Zero Magic 未来切换回 harness stage-7 节奏，会有新的 harness-lab trace 数据可用作 M2 candidate 对比
