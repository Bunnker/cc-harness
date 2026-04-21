# OpenSpec 与 harness 共存/冲突分析

本分析只依据已读文件下结论；凡是从现有证据向前推一步的地方，均标记为 `[speculation]`。

本次读取中，以下用户点名路径未找到：`D:\ai\claude-code\harness-skills-pack\stage-roadmap.md`、`D:\ai\claude-code\harness-skills-pack\dependency-graph.md`、`D:\ai\claude-code\harness-skills-pack\execution-policy.md`、`D:\ai\claude-code\harness-skills-pack\harness-hooks-schema.md`、`D:\ai\claude-code\harness-skills-pack\skill-catalog.md`、`D:\ai code\Zero_magic\openspec\changes\add-fengshui-demo-workbench\proposal.md`、`tasks.md`、`design.md`。因此，凡涉及该 OpenSpec change 的实物工件，以下都以实际可读的归档目录 `D:\ai code\Zero_magic\openspec\changes\archive\2026-04-21-add-fengshui-demo-workbench\...` 为准。

## 引用缩写

- `H-HAR` = `D:\ai\claude-code\harness-skills-pack\skills\harness\SKILL.md`
- `H-VER` = `D:\ai\claude-code\harness-skills-pack\skills\harness-verify\SKILL.md`
- `H-FM` = `D:\ai\claude-code\harness-skills-pack\FAILURE-MODES.md`
- `H-EVO` = `D:\ai\claude-code\harness-skills-pack\EVOLUTION-FROM-ZEROMAGIC.md`
- `ZM-STATE` = `D:\ai code\Zero_magic\.claude\harness-state.json`
- `ZM-APPLY` = `D:\ai code\Zero_magic\.claude\skills\openspec-apply-change\SKILL.md`
- `ZM-VERIFY` = `D:\ai code\Zero_magic\.claude\skills\openspec-verify-change\SKILL.md`
- `ZM-ARCH` = `D:\ai code\Zero_magic\.claude\skills\openspec-archive-change\SKILL.md`
- `ZM-ARCHCMD` = `D:\ai code\Zero_magic\.claude\commands\opsx\archive.md`
- `ZM-PHASE` = `D:\ai code\Zero_magic\.claude\agents\fengshui-phase-coordinator.md`
- `ZM-AUDIT` = `D:\ai code\Zero_magic\docs\audit\2026-04-21_archive_ready_final.md`
- `ZM-P1` = `D:\ai code\Zero_magic\docs\audit\2026-04-20_phase_1_data-model-contract.md`
- `ZM-PROP` = `D:\ai code\Zero_magic\openspec\changes\archive\2026-04-21-add-fengshui-demo-workbench\proposal.md`
- `ZM-TASKS` = `D:\ai code\Zero_magic\openspec\changes\archive\2026-04-21-add-fengshui-demo-workbench\tasks.md`
- `ZM-DESIGN` = `D:\ai code\Zero_magic\openspec\changes\archive\2026-04-21-add-fengshui-demo-workbench\design.md`
- `ZM-OSYAML` = `D:\ai code\Zero_magic\openspec\changes\archive\2026-04-21-add-fengshui-demo-workbench\.openspec.yaml`

## §1 Two-workflow capability matrix

| 维度 | harness | OpenSpec / Zero Magic | 共存含义 |
|---|---|---|---|
| 外层协调协议 | harness Coordinator 的唯一职责是 `Plan -> Approve -> Execute -> Report`，并且禁止自己直接写代码或设计模块。[H-HAR 11-12,61-69] | `fengshui-phase-coordinator` 明说“模仿 harness 协议，但不是 harness 本身”，并拆成 `mode: plan-only | execute` 两模态；APPROVE 门由父会话承担。[ZM-PHASE 17-20,28-40,94-97,214-215] | 两者都属于 coordinator-first，但批准门持有者不同；这不是表层文案差异，而是控制面所有权差异。[H-HAR 61-69][ZM-PHASE 17-20,214-215] |
| 规范/计划来源 | harness 在 PLAN 阶段依赖 `skill-catalog.md`、`stage-roadmap.md`、`dependency-graph.md`、`execution-policy.md` 做决策。[H-HAR 237-243] | 归档 change 明确采用 `spec-driven` schema，并以 `proposal.md`、`design.md`、`tasks.md`、`specs/*` 作为主工件面。[ZM-OSYAML 1-2][ZM-PROP 7-24][ZM-DESIGN 15-27][ZM-TASKS 1-49] | 当前 harness pack 更像“协议壳 + 缺失辅助文档”，OpenSpec 则是“artifact-first”。 |
| 调度粒度 | harness 以“项目阶段 + Worker 分配表 + target_paths + isolation”组织执行。[H-HAR 264-315,338-395] | OpenSpec change 以“单 change 下的 Phase 1..5 + tasks 复选框”组织执行；自定义 phase coordinator 再把每个 Phase 切成 Worker A/B/C...。[ZM-TASKS 1-49][ZM-PHASE 58-91,98-124] | 一个是项目/阶段面，一个是 change/phase 面；粒度不对齐是后续边界设计的核心。 |
| 规范工件是否只读 | harness 自身没有“不得修改外部 spec 工件”的专门条款；它主要约束 `.claude/`、公共接口、越界修改和 `target_paths`。[H-HAR 487-508,523-531] | `fengshui-phase-coordinator` 把 `proposal / design / specs / tasks.md` 明确设为只读参考，任何契约漂移都要 ESCALATE 给父 Agent。[ZM-PHASE 24-27,42-50] | 这使 OpenSpec 工件在 Zero Magic 中被当作“契约源”，不是执行 trace 的一部分。 |
| Worker 调度接口 | harness 只允许调度 `role = worker` 的 skill，并要求固定前缀 + 动态后缀的两段式 prompt。[H-HAR 258-262,466-547] | `fengshui-phase-coordinator` 调度的是 `subagent_type` 工作池，并把任务边界、验收标准、跨层契约和输出要求直接内联进 prompt。[ZM-PHASE 68-85,100-124,188-201] | 两边的“worker 身份模型”不同：一个以 skill 分类，一个以角色池分类。 |
| Prompt 约束 | harness Worker prompt 禁用 Agent tool、AskUserQuestion、不可逆命令，并要求 `INTERFACE_CHANGE` / `ESCALATE` / `target_paths` 等结构化约束。[H-HAR 485-508,520-531] | phase coordinator prompt 强调任务边界、Given/When/Then 验收标准、跨层契约注释、以及“只返回 touched_files + 关键决策”。[ZM-PHASE 103-120] | 两边并非语义重复；它们在“谁可问用户、谁可再派 Agent、返回什么结构”上确实不同。 |
| 进度持久化 | harness 将 `current_stage`、`completed_stages`、`last_execution`、`results`、`open_risks`、`learnings` 持久化到 `.claude/harness-state.json`。[H-HAR 74-105,687-694,758-762][ZM-STATE 111-150] | OpenSpec 的 change 进度主要体现在 `tasks.md` 复选框、phase audit 报告和最终 archive-ready 审核文档中。[ZM-TASKS 1-49][ZM-P1 11-19][ZM-AUDIT 22-37] | 一个是项目级状态容器，一个是 change 级工件/报告容器。 |
| 验证目标 | `harness-verify` 做技术验证 + 代码审计，评分维度包括 `build_lint_typecheck`、`runtime_invariants`、`structural_fidelity`、`verification_coverage`、`code_quality` 等。[H-VER 9-13,33-129,158-216] | `openspec-verify-change` 做 artifact-facing 验证，分成 `Completeness / Correctness / Coherence` 三维，并按 `CRITICAL / WARNING / SUGGESTION` 产出。[ZM-VERIFY 44-52,53-109,124-159] | 两套 verify 的目标平面不同；这意味着它们更适合叠加，而不是二选一。 |
| 验证输出位置 | harness coding/audit 轮的 verify 输出会直接写到 `.claude/harness-lab/traces/{date}-{stage}/`，包括 `commands.log`、`diff.patch`、`verification.md`、`scorecard.json`、`failure-reason.md`。[H-HAR 556-583,601-633][H-VER 218-285] | phase coordinator 明确“不写 harness-lab/traces”，而是把 REPORT 写到 `docs/audit/2026-04-20_phase_{N}_<name>.md`；最终 archive-ready 审核也落在 `docs/audit/`。[ZM-PHASE 17-20,82-85,136-186][ZM-AUDIT 1-18] | 目前是“双证据面分离”而非“同目录争用”。 |
| 归档/收口 | harness 的 REPORT 重点是状态更新、trace 完整性和 M2 证据卫生门，不包含 change archive 语义。[H-HAR 665-750,784-793] | OpenSpec 有显式 archive 终点：检查 artifacts、tasks、delta spec sync，然后移动到 `openspec/changes/archive/YYYY-MM-DD-<name>`。[ZM-ARCH 27-83,94-114][ZM-ARCHCMD 23-79,150-157] | 一个偏 proof-plane / execution-plane 收口，一个偏 change lifecycle 收口。 |
| 失败表达 | harness 失败会进入 `failure-reason.md`、`learnings(type=failure)`、`open_risks`、以及 trace-write fallback 结构化块。[H-HAR 621-623,680-694,727-750][H-VER 236-279][ZM-STATE 135-202] | OpenSpec verify 规范化的是 `CRITICAL / WARNING / SUGGESTION`；实际归档前审计也按这三类给出非阻塞问题与建议。[ZM-VERIFY 124-159][ZM-AUDIT 40-67] | 两边都记录失败，但“单位”不同：harness 记执行教训，OpenSpec 记 change readiness。 |
| M2 / proof-plane | harness 明确把 M2 候选实验、scorecard、leaderboard 视为主线的一部分，并列出 `slim-report-v1`、`independent-audit-v1` 等候选语义。[H-HAR 665-750,784-793][H-EVO 69-90,280-297] | OpenSpec / Zero Magic phase 报告与 archive-ready 报告没有暴露 harness 的 candidate/leaderboard 协议；其主线是 Phase 报告与 archive 决策。[ZM-PHASE 136-186][ZM-AUDIT 10-18,148-167] | 因此两边的“高分”默认不能直接进同一个比较池。 |
| 当前 Zero Magic 观测状态 | `harness-state.json` 当前 `current_stage` 是 `stage-7-personality-safety`，最近一次执行也是该阶段第二批，并使用了 `harness-verify`。[ZM-STATE 111-123] | 风水 OpenSpec change 已经存在于归档目录，且 archive-ready 审核给出 `YES — 可以 /opsx:archive`。[ZM-OSYAML 1-2][ZM-AUDIT 148-167] | 当前观测到的是“同仓共存”，不是“同一 change 被两套系统同时驱动”。 |

- `fengshui-phase-coordinator` 自述会在 `/openspec-apply-change` 命中 5 判据时被主会话调用，但当前可见的通用 `openspec-apply-change` skill 文件本身没有写出这条 bridge；也就是说，桥接协议主要记录在 Zero Magic 的自定义 agent 文件，而不是通用 OpenSpec skill 中。[ZM-PHASE 3][ZM-APPLY 16-79]
- `FAILURE-MODES.md` 把 `harness-verify` 放在 `Self-Evaluation Blind Spot`、`评估信号噪音`、`可观测性缺失`、`结构保真失败` 等失败模式下，说明 harness 这一侧把 verify 看成 proof-plane 的核心构件，而不是可有可无的附属步骤。[H-FM 24-35,64-72,145-154,182-200]
- `EVOLUTION-FROM-ZEROMAGIC.md` 已经把 `fengshui-phase-coordinator` 归纳成“phase-scoped nested coordinator”，并明确指出它不是 `harness-lite` 的简单轻量版，而是“外部 spec 系统 + 内部 worker 池”的桥接层。[H-EVO 131-161]

## §2 Real conflict points

### 2.1 `harness-state.json` vs `openspec/changes/*/tasks.md`

- `tasks.md` 的语义是“单 change 内的 Phase/任务复选框”；`openspec-apply-change` 明确要求在每个 pending task 完成后立即把 `- [ ]` 改成 `- [x]`。[ZM-APPLY 67-75,147-149][ZM-TASKS 1-49]
- `harness-state.json` 的语义是“单项目当前阶段 + 最近执行 + learnings + open_risks + module 状态”；它不是 per-change checklist 容器。[H-HAR 74-105,687-694][ZM-STATE 111-150]
- 当前 Zero Magic 的 `harness-state.json` 没有任何 `openspec`、`fengshui`、`active_change` 或类似字段；它记录的是另一条主线 `stage-7-personality-safety`。[ZM-STATE 111-123]
- 因此，今天可直接证实的不是“两个文件已经互相覆盖同一份进度”，而是“两个文件服务于不同坐标系”。一个是 project-stage；一个是 change-phase。[ZM-STATE 111-123][ZM-TASKS 1-49]
- 真正的冲突点出现在 Zero Magic 的 bridge 设计里：通用 `openspec-apply-change` 期望执行者更新 `tasks.md` 复选框，但 `fengshui-phase-coordinator` 又把 `proposal / design / specs / tasks.md` 定义为只读参考。[ZM-APPLY 67-75][ZM-PHASE 24-27]
- 这说明“谁拥有 OpenSpec 任务进度真相”在当前文本中并没有一个统一答案：generic OpenSpec skill 说“执行者更新”，custom phase coordinator 说“执行者只读”。这是实质性冲突，不是表层术语差异。[ZM-APPLY 67-75][ZM-PHASE 24-27]
- [speculation] 如果未来让 harness 直接驱动某个活跃 OpenSpec change，那么最需要先解决的不是 JSON/Markdown 格式差异，而是“谁负责勾任务、谁负责改阶段、哪个是唯一真相源”。[ZM-APPLY 67-75][H-HAR 687-694]

### 2.2 “同一个 skill 能否被两条轨道同时调度”

- harness 只调度 `role = worker` 的 skill，并且在 Worker prompt 里显式禁止 `Agent` tool 和 `AskUserQuestion` tool；Bash 也被收窄为只读命令与构建命令。[H-HAR 258-262,468-495]
- `openspec-apply-change`、`openspec-verify-change`、`openspec-archive-change` 都把 `AskUserQuestion` 写进主流程：当 change 名缺失或有歧义时，必须让用户选择，而不是自动猜测。[ZM-APPLY 14-25][ZM-VERIFY 18-27][ZM-ARCH 18-25]
- `openspec-archive-change` 还要求在用户选择同步时再起一个 Task/subagent 去跑 `openspec-sync-specs`，并执行 `mkdir -p`、`mv` 这类 archive 操作。[ZM-ARCH 53-83,113-114][ZM-ARCHCMD 49-79,150-157]
- 因此，原样把 `openspec-apply-change` / `openspec-verify-change` / `openspec-archive-change` 当成 harness Worker skill 去派发，会直接撞上 tool contract：它们需要的交互/再派发/文件移动能力，正是 harness Worker 被禁止或收紧的能力。[H-HAR 491-499][ZM-APPLY 23-25][ZM-ARCH 66-83]
- 这也是为什么 `fengshui-phase-coordinator` 在 Zero Magic 中被做成单独 subagent，而不是把 `openspec-*` workflow 技能塞进 harness Worker 池。[ZM-PHASE 15-27][H-EVO 145-161]
- 反过来，`harness-verify` 更适合做桥接点：它本来就是独立 verify/audit worker，输入输出边界清楚，不需要向用户提问，也不需要再开 Agent。[H-VER 15-29,218-285]
- 结论：今天“同一个 skill 被两条轨道同时原样调度”的答案是否定的；真正可行的是“通过适配层调用对方某个子能力”，而不是互相直接派发 workflow skill。[H-HAR 468-495][H-VER 15-29][ZM-PHASE 129-186]

### 2.3 Worker dispatch prompt 模板是否冲突

- harness 的 worker prompt 是“固定前缀 + 动态后缀”两段式模板，固定前缀里有工具禁令、路径边界、`INTERFACE_CHANGE` / `ESCALATE` 等硬约束；动态后缀里有 `target_paths`、本任务相关模块和本轮 learnings。[H-HAR 470-547]
- `fengshui-phase-coordinator` 的 worker prompt 模板更偏“任务说明书”：它要求写明任务边界、Given/When/Then 验收标准、跨层契约注释，以及“只返回 touched_files 清单 + 关键决策”。[ZM-PHASE 103-120]
- 这两套模板并不在同一层抽象上：harness 更像执行沙箱契约，phase coordinator 更像外部 spec 到 worker 的实施 brief。[H-HAR 470-547][ZM-PHASE 103-120]
- 真实冲突点在输出契约：harness 允许编码 Worker 直接“输出完整可运行的代码文件”，审计 Worker 输出“检查清单 + 问题列表 + 改进建议”；phase coordinator 则要求返回“touched_files + 关键决策”，并显式说不要回传中间过程。[H-HAR 510-515][ZM-PHASE 117-120]
- 如果一个 worker 同时被要求满足这两套输出契约，就会出现“究竟是交代码正文、交摘要、还是交 touched_files 列表”的接口歧义；这是真实冲突，而不是措辞差异。[H-HAR 510-515][ZM-PHASE 117-120]
- 但这并不意味着两套模板不能叠加。`harness-verify` 需要的是 `project_path`、`trace_dir`、`plan_baseline_commit`、worker 清单、commands、constraints；而 phase coordinator 已经有 Worker 分配表和 phase 末验证命令，理论上足以喂给一个适配后的 harness-verify 调用。[H-HAR 567-575][H-VER 15-29][ZM-PHASE 68-85,129-136]
- [speculation] 更合理的做法不是“合并模板”，而是“Phase brief 负责 artifact/spec 语义，harness prefix 负责沙箱与可验证性语义”，让二者在桥接层拼接，而不是让某一边吞掉另一边。

### 2.4 Trace 输出位置：`harness-lab/` vs `openspec/changes/*/` / `docs/audit/`

- harness 的 trace 是原始执行证据面：`worker-{n}-prompt.md`、`commands.log`、`result.md`、`diff.patch`、`failure-reason.md` 等都写到 `.claude/harness-lab/traces/{YYYY-MM-DD}-{stage}/`。[H-HAR 601-633]
- `fengshui-phase-coordinator` 明确声明“不写 harness-lab/traces/”，而把每个 Phase 的 REPORT 写到 `docs/audit/2026-04-20_phase_{N}_<name>.md`。[ZM-PHASE 17-20,82-85,136-180]
- 实际项目里这两块都已经存在：harness 侧有 `.claude/harness-lab/traces/...` 与 `trace_ref`；OpenSpec/Phase 侧有 `docs/audit/2026-04-20_phase_1_data-model-contract.md` 和 `2026-04-21_archive_ready_final.md`。[ZM-STATE 119-122,161-202][ZM-P1 1-19][ZM-AUDIT 1-18]
- 因此，“资源 contention”在今天不是文件路径冲突；真实问题是证据分裂。harness 有 `trace-index`、`scorecard`、`learnings` 体系，而 OpenSpec/Phase 证据停留在 `docs/audit/` 文档平面，没有纳入 harness 的索引与比较面。[H-HAR 138-156,721-746][ZM-PHASE 136-186]
- 这也解释了为什么 `archive-ready` 结论可以存在，但不会自然出现在 harness 的 `trace-index` 或 M2 候选池里；两个系统没有共享证据索引。[H-HAR 721-746,784-793][ZM-AUDIT 148-167]
- [speculation] 如果 OpenSpec Phase 后续加上 `harness-verify`，最关键的治理工作不是防止目录冲突，而是给 `docs/audit/...` 和 `.claude/harness-lab/traces/...` 建立双向引用。

## §3 Information layers worth sharing

### 3.1 `learnings` 与 OpenSpec 失败/验证记录，什么值得共享

- harness 的 `learnings` 是项目状态文件里的摘要层：`date / stage / type / insight / trace_ref`，并在 REPORT 阶段被明确要求写回 state。[H-HAR 680-694][ZM-STATE 150-202]
- OpenSpec 归档 change 目录本身只看到 `.openspec.yaml`、`proposal.md`、`design.md`、`tasks.md`、`README.md` 和 `specs/*`；没有独立的 `failure-reason.md` 或同类失败工件。[ZM-OSYAML 1-2][ZM-PROP 1-51][ZM-DESIGN 1-153][ZM-TASKS 1-49]
- OpenSpec 的“失败/风险/是否可归档”信息实际上落在验证/审计文档层：`openspec-verify-change` 规定 `CRITICAL / WARNING / SUGGESTION` 三档，真实的 `archive-ready` 审计文档也按这三档给出非阻塞问题与建议。[ZM-VERIFY 44-52,124-159][ZM-AUDIT 40-67]
- 这说明两边最值得共享的不是“把 tasks.md 复选框抄进 state”，也不是“把整份 audit prose 拼进 learnings”，而是一个更小的“经验摘要 + 证据引用”层。[H-HAR 680-694][ZM-VERIFY 124-159][ZM-AUDIT 40-67]
- [speculation] 一个可共享的最小包络应当长这样：

```json
{
  "source_track": "harness | openspec",
  "scope": "project | change | phase",
  "kind": "success | failure | warning",
  "summary": "一句话经验或风险",
  "evidence_ref": "trace 路径或 audit 路径",
  "normalized_at": "YYYY-MM-DD"
}
```

- 这样做的好处是：harness 仍保留自己的 `trace_ref` 学习面，OpenSpec 仍保留自己的 `CRITICAL/WARNING/SUGGESTION` 审核面，但跨系统共享时只交换“压缩过的经验索引”。[H-HAR 153-156,680-694][ZM-VERIFY 124-159]
- [speculation] 如果要把 OpenSpec 的失败教训回写到 `harness-state.json`，建议新增 `source_track` 与 `evidence_ref`，不要把整段 `archive-ready` 文本塞进 `insight`。

### 3.2 `skill-catalog.md` 是否应收录 `openspec-*` 技能

- harness 的 PLAN/EXECUTE 逻辑假定存在 `skill-catalog.md`，并且只从 `role = worker` 的 skill 里选；`non-worker` skill 只能给 Coordinator 参考，不能派给子 Agent。[H-HAR 239-243,258-262,466-468]
- 当前 pack 工作区没有 `skill-catalog.md`，所以“如何收录 OpenSpec 技能”现在是新增设计，不是补现有 catalog 的一条记录。
- `openspec-apply-change`、`openspec-verify-change`、`openspec-archive-change` 都是 workflow 级技能：它们要么问用户、要么查 `openspec` CLI、要么做 archive/sync 决策，而不是叶子 worker 技能。[ZM-APPLY 14-25,27-57][ZM-VERIFY 18-49][ZM-ARCH 18-25,53-83]
- 所以，如果未来真的补 `skill-catalog.md`，我不建议把 `openspec-*` 标成 `role = worker`；它们更像 `non-worker` 或 `[speculation] role = workflow-bridge` 一类的控制面技能。[H-HAR 258-262,466-468][ZM-APPLY 14-25][ZM-ARCH 53-83]
- 但要注意一个现实约束：当前 harness 文本只明示了 `role = worker` 与 `non-worker` 两类，没有可验证的第三类角色语义。[H-HAR 258-262,466-468]
- 因此，比“直接新增 `role = bridge`”更稳的做法是：保留 `role = non-worker`，再增加 `[speculation] track = openspec`、`category = vertical-workflow | bridge` 之类的附加元数据。这样不需要先改 harness 调度器的角色判断规则。[H-HAR 258-262,466-468]
- `H-EVO` 对 11 个 `openspec-*` skills 的归类也支持这一点：它把它们的主要可迁移价值归纳为“workflow bridge 模式”，而不是 `worker` 执行面能力。[H-EVO 163-217]

### 3.3 独立审计员名册：谁可以做 Archive-Ready audit

- `harness-verify` 本身就是正式的独立验证+审计 Worker，负责跑命令、读文件、写 `verification.md` / `audit-findings.md` / `scorecard.json`，并且强调自己“不是橡皮图章”。[H-VER 7-13,98-129,158-227]
- `archive-ready` 最终审计文档写得很明确：审查人是“独立 general-purpose Worker + 主会话现场验证命令见证”。[ZM-AUDIT 3-7]
- 实际的 Phase 1 报告也已经区分了实现者和验证者：`4 Worker（A/B/C/D）+ 1 Verify（主会话 typecheck 二次确认）`。[ZM-P1 4-7,11-19]
- 这意味着 Zero Magic 当前真实存在的 `Archive-Ready` 审计员名册，至少由三类角色构成：`artifact-facing reviewer`、`code/runtime verifier`、`command witness`。[ZM-AUDIT 3-7][ZM-P1 4-7][H-VER 7-13]
- [speculation] 其中只有 `harness-verify` 这种“可复用、有清晰输入输出的能力体”适合进入 skill catalog；`general-purpose Worker` 与“主会话见证者”更像流程角色槽位，应该写进根文档或 workflow-bridge doc，而不是伪装成 skill。

## §4 Three single-round integration actions

### Action 1：给 `harness-state.json` 增加 `active_openspec_changes`

- 判定：**确认，但要把它定义为“可见性元数据”，不是第二个阶段机。**
- 证据基础是：当前 `harness-state.json` 只有单一 `current_stage` / `completed_stages` 轴，而且完全看不见任何 OpenSpec change 名称或 phase 信息。[ZM-STATE 111-123]
- 同时，OpenSpec change 的主进度面是 `tasks.md` Phase 清单与 Phase/Archive 报告，而不是项目级单一阶段字段。[ZM-TASKS 1-49][ZM-P1 11-19][ZM-AUDIT 22-37]
- 所以加一个“当前有哪些 OpenSpec change 正在跑”的附加数组，确实是低风险高价值；它解决的是 `SCAN` 的 situational awareness，不是替代 `tasks.md`。[H-HAR 74-105][ZM-TASKS 1-49]
- [speculation] 我建议字段长这样：

```json
{
  "active_openspec_changes": [
    {
      "name": "add-fengshui-demo-workbench",
      "schema": "spec-driven",
      "status": "active | archived",
      "artifact_dir": "openspec/changes/<name>",
      "phase_reports_dir": "docs/audit/",
      "last_report": "docs/audit/2026-04-20_phase_2_gateway-api.md"
    }
  ]
}
```

- 低风险点在于它是**纯附加字段**；不碰现有 `current_stage` 语义。[ZM-STATE 111-150]
- 风险边界也要写清：在没有同步修改 harness SCAN 文档之前，这个字段只是提示信息，不应被当成“替代 stage-roadmap 的调度真相”。[H-HAR 74-105,120-156,237-243]

### Action 2：替换“`skill-catalog.md` 增加 `role=bridge`”为更安全的 catalog / doc 方案

- 判定：**替换候选。**
- 不建议原样采纳“`role = bridge`”这个提法，因为当前 harness 可验证的角色分流只有 `worker` vs `non-worker`；直接引入第三类角色，意味着还要改 catalog 语义与调度逻辑。[H-HAR 258-262,466-468]
- 更低风险的单轮动作是两步：
- 第一步，若未来补 `skill-catalog.md`，先把 `openspec-*` 与 `fengshui-phase-coordinator` 记录为 `non-worker`，再加 `[speculation] track = openspec` / `category = bridge` 之类的附加元数据。[H-HAR 258-262,466-468][ZM-PHASE 15-27][H-EVO 163-217]
- 第二步，同时补一份根文档级 bridge 说明，明确：哪些是“外部 workflow skill”，哪些是“phase-scoped coordinator”，哪些是“leaf worker/aux verifier”。[H-EVO 241-257,318-326]
- 这么做的好处是：分类价值先落地，而不需要立刻改 harness 的 worker 调度器。[H-HAR 258-262,466-468]
- [speculation] 如果以后真的把第三类角色写进 catalog，也应该把它定义成“不可被 harness Worker 直接派发的 workflow/bridge”，而不是另一个可执行 worker 类。

### Action 3：让 OpenSpec Phase 可以把 `harness-verify` 当作辅助 `code_quality` 信号

- 判定：**确认。**
- `harness-verify` 的职责平面是“技术验证 + 代码审计 + scorecard”，而 `openspec-verify-change` 的职责平面是“Completeness / Correctness / Coherence”；二者天然互补，而非同类替代。[H-VER 9-13,98-129,158-216][ZM-VERIFY 44-52,53-109]
- `fengshui-phase-coordinator` 已经具备桥接 `harness-verify` 所需的大部分输入：Worker 分配表、触达文件、依赖关系、Phase 末验证命令、REPORT 输出路径。[ZM-PHASE 68-85,98-136]
- 所以，把 `harness-verify` 作为 OpenSpec Phase 的**辅助 code/runtime audit** 是低风险高价值动作；它补的是“执行质量信号”，不会覆盖 OpenSpec 的 artifact completeness 判定。[H-VER 158-216][ZM-VERIFY 124-159]
- 我建议 4 条硬边界：
- 只在有代码变更的 Phase 后调用，不在纯 proposal/design 阶段调用。[H-HAR 556-583][ZM-PHASE 129-136]
- 输入必须由 phase coordinator 显式适配出 `project_path`、`trace_dir`、`baseline_commit`、worker 清单、commands、constraints`，不能让 `harness-verify` 自猜。[H-HAR 567-575][H-VER 15-29]
- `harness-verify` 的 scorecard 只作为辅助信号写进 `docs/audit/` 或桥接索引，不直接替代 `openspec-verify-change` / `archive-ready` 决策。[H-VER 229-235][ZM-VERIFY 141-168][ZM-AUDIT 148-167]
- [speculation] 若将来进入 M2 比较面，必须先单独打 `track=openspec-aux` 标签，避免把 OpenSpec phase 分段分数混入 harness 主 leaderboard。

## §5 Boundaries to keep separate

### Agree

- 我同意“spec artifacts（proposal / tasks / design / specs）不应进入 harness trace”。`fengshui-phase-coordinator` 已把这些工件定义为只读参考，而 harness trace 的设计目标是保存 prompt、命令、结果、diff、失败原因等执行证据；把两者混在一起会模糊“契约面”和“执行证据面”的边界。[ZM-PHASE 24-27,42-50][H-HAR 601-633]
- 我同意“spec 工件本体不应复制进 harness trace”，但 harness trace/REPORT 可以保留指针型引用，例如某条 learning 指向 `proposal.md` 或某份 phase audit；这属于引用，不属于把 spec 正文吸入 trace。[H-HAR 680-694][ZM-PHASE 24-27][speculation]
- 我同意“M2 candidate pool 不应默认纳入 OpenSpec-run changes”。harness 的 M2 依赖自己的 scorecard、trace-index、leaderboard 和 candidate heuristics；OpenSpec/Phase 报告当前没有输出相同的协议与分段基准。[H-HAR 721-746,784-793][H-VER 158-201,236-285][ZM-PHASE 136-186]
- `archive-ready` 审核文档给出的 `YES` 是 change lifecycle readiness，不等于 harness 的 M2 实验得分；把两者直接混排，会把“是否可归档”和“编排策略 ROI”两个问题混成一个分数。[ZM-AUDIT 10-18,148-167][H-HAR 784-793]

### Refute / Supplement

- 我没有看到需要直接反驳的边界判断；需要补充的是：真正要隔离的不是“文件目录名”，而是“评分语义”。即便未来 OpenSpec Phase 也落 `scorecard.json`，只要它的分段方式和样本单位仍是 `change-phase`，就不应直接并入 harness 的 stage/round leaderboard。[H-HAR 784-793][ZM-PHASE 136-186][speculation]
- [speculation] 如果以后确实需要比较 OpenSpec-run 与 harness-run 的质量，应该新增一个 bridge leaderboard，并把样本单位统一为“同一代码面、同一变更范围、同一验证协议”的可比轮次，而不是复用现有 M2 池。

## §6 Root-level doc vs new skill recommendation

- 结论先说：**现阶段应先落根文档，不应立即新建 `skills/workflow-tracks/SKILL.md`。**
- `FAILURE-MODES.md` 的定位是“从失败模式找 skill 的正交索引”；它能解释为什么需要 `harness-verify`、为什么要防自评盲点，但它不是双工作流共存的操作指南。[H-FM 1-5,24-35,64-72,145-154,182-200]
- `EVOLUTION-FROM-ZEROMAGIC.md` 的定位是“从 Zero Magic 反哺 pack 的实证回顾”；它已经明确把 `fengshui-phase-coordinator` 看成值得抽象的模式，但同时把这件事列成 `multi-round / medium risk` 的后续建议，而不是“一轮就该升格成 skill”的既定结论。[H-EVO 1-10,131-161,241-257]
- 这两个文档加在一起，已经能支撑“为什么要记录这个桥接模式”；但它们还不够支撑“团队今天该怎么同时运行 harness 与 OpenSpec”。前者是索引，后者是复盘，不是 operator-facing usage note。[H-FM 1-5][H-EVO 1-10,318-326]
- 按用户给的判定标准看，当前材料仍然更接近“这个 pack 在 Zero Magic / OpenSpec 场景下的使用说明”，而不是“任意 harness + 任意 specSystem 的稳定抽象模式”。证据有三条：
- 第一，当前证据来源是单项目、单 schema（`spec-driven`）、单自定义 coordinator。[ZM-OSYAML 1-2][ZM-PHASE 15-27]
- 第二，桥接协议有相当部分只写在 `fengshui-phase-coordinator` 里，而不是写进通用 `openspec-apply-change` 技能里。[ZM-PHASE 3][ZM-APPLY 16-79]
- 第三，当前 pack 侧连 `skill-catalog.md` 等辅助文档都未齐；现在就把桥接模式升格成 skill，容易把尚未稳定的接口过早冻结。 [H-HAR 237-243]
- 因此，最合理的当前落点是：继续保留根文档形态，把“桥接规则、边界、引用关系、何时调用 auxiliary verify”写清楚；本文件本身就已经是这种根文档的雏形。[speculation]
- 我也不建议现在新建名为 `workflow-tracks` 的 skill。这个名字更像 taxonomy，而不是 procedure；而 `H-EVO` 真正抽象出来的可复用单位，是“phase-scoped nested coordinator / parent-approved phase coordinator”。[H-EVO 143-161,241-257]
- [speculation] 如果未来满足以下条件，再考虑新建 portable skill 才更合适：
- 至少出现第二个外部 spec/workflow 系统，或者第二个仓库复用了同样的桥接协议。
- `status/instructions/contextFiles` 一类的 bridge 输入已经稳定，不再只绑定 OpenSpec CLI。[H-EVO 167-178]
- `skill-catalog` / role 语义已经稳定，能明确区分 worker、workflow-bridge、aux-verifier 之类的角色。
- 真到那一步，名字更贴切的可能是 `skills/spec-phase-coordinator/SKILL.md`，而不是 `skills/workflow-tracks/SKILL.md`。[H-EVO 241-257][speculation]

## §7 Analysis limitations

- 这份分析是 **n=1 project** 的观察结果；OpenSpec 侧也只读到了一个 `spec-driven` change 的实物工件与配套报告，因此泛化到“任何 spec 系统”时必须保守。[ZM-OSYAML 1-2][H-EVO 1-10]
- harness 主技能引用的若干关键辅助文档在当前工作区未找到：`stage-roadmap.md`、`dependency-graph.md`、`execution-policy.md`、`harness-hooks-schema.md`、`skill-catalog.md`。这限制了我对 skip-if、依赖图、catalog schema、降级策略原文的直接核验能力。[H-HAR 117,125-156,239-243,345-351,651-656]
- 用户指定的活跃 change 目录未找到；所以与 `add-fengshui-demo-workbench` 相关的事实，以下都是基于归档目录和 `docs/audit/*.md` 反推其实际落盘形态，而不是基于活跃目录现场状态。
- `fengshui-phase-coordinator` 说自己会在 `/openspec-apply-change` 命中 5 判据时被主会话调用，但当前可见的通用 `openspec-apply-change` skill 文件没有写出该桥；因此 bridge 的一部分是单侧文档，而不是双侧显式契约。[ZM-PHASE 3][ZM-APPLY 16-79]
- 当前 `harness-state.json` 描述的是 `stage-7-personality-safety`，不是风水 OpenSpec change；所以本文关于“信息重叠”和“路径冲突”的结论，更多是在分析协议接缝，而不是在描述一个正在被双工作流同时控制的活跃 change。[ZM-STATE 111-123]
