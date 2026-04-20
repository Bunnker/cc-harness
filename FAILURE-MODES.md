# 失败模式驱动视图

> 从"要防什么失败"找 skill，而非从"实现什么维度"找 skill。
>
> 现有 47 个 skill 按实现维度（loop / memory / permission ...）组织，这份索引提供正交视图：把 skill 归类到它们真正治疗的失败模式。遇到具体症状时先查本文，再去看对应 skill。

## 一、Anthropic 显式命名的两大失败模式

这两个是当前 harness 设计的主要驱动力，来自 Anthropic 的 "Effective harnesses for long-running agents"。

### FM-1: Context Anxiety（容量焦虑）

**症状**：Agent 任务未完成但开始说"我已完成初步工作"/"总结一下目前进度"——不是上下文真满了，是模型**主观感觉**该收尾了。

**区分点**：上下文还有余量。如果真满了（`prompt_too_long`）是内存失败，走压缩路径。

| 角色 | Skill | 解决什么切面 |
|------|-------|------------|
| 主 | [agent-resilience](skills/agent-resilience/SKILL.md) §7 | 定义 + 3 种锚点策略 + 2 个检测用例 |
| 辅 | [compact-system](skills/compact-system/SKILL.md) | 真到容量上限时的渐进压缩 |
| 辅 | [session-memory](skills/session-memory/SKILL.md) | 压缩后的状态保留 |
| 辅 | [architecture-invariants](skills/architecture-invariants/SKILL.md) §4 | Opus 4.6 修好后原有 context-reset 脚手架如何下线 |

### FM-2: Self-Evaluation Blind Spot（自评盲点）

**症状**：让 Agent 评估自己刚写的代码，它说"一切良好"。本质是同一 context 内没有怀疑先验。

**关键不对称**（Anthropic 原文）：让独立 Evaluator 挑刺，比让 Generator 自我怀疑容易得多。

| 角色 | Skill | 解决什么切面 |
|------|-------|------------|
| 主 | [agent-reflection](skills/agent-reflection/SKILL.md) §7 | 3 种外部校验信号 + Evaluator 校准模板 |
| 主 | [multi-agent-design](skills/multi-agent-design/SKILL.md) | Planner/Generator/Evaluator 三角色 + Sprint Contract |
| 辅 | [harness-verify](skills/harness-verify/SKILL.md) | 确定性 Oracle（跑命令/测试/审计）+ trace 留证 |
| 辅 | [eval-driven-design](skills/eval-driven-design/SKILL.md) | 轨迹评估 vs 端态评估区分 |

## 二、长运行 Agent 典型失败

### FM-3: 跨会话状态丢失

**症状**：新会话继续任务时 Agent 不知道上次做到哪、为什么这么设计。

| 角色 | Skill | 解决什么切面 |
|------|-------|------------|
| 主 | [session-recovery](skills/session-recovery/SKILL.md) | JSONL 追加 + parentUuid 链表重建 + sessionId 键恢复 |
| 主 | [agent-memory](skills/agent-memory/SKILL.md) | 跨会话记忆 4 类型 + 索引常驻 |
| 辅 | [session-memory](skills/session-memory/SKILL.md) | 会话内压缩后的状态保留 |
| 辅 | [team-memory-sync](skills/team-memory-sync/SKILL.md) | 团队成员共享知识同时防密钥泄露 |
| 辅 | [agent-reflection](skills/agent-reflection/SKILL.md) | feedback 记忆捕获纠正和确认 |

### FM-4: Harness 组件假设过期

**症状**：某个脚手架原本是治某个模型缺陷的，模型升级后缺陷消失，脚手架变成负债（掩盖真问题）。

**经典案例**：context reset 基础设施 → Opus 4.6 自修 → 被 Anthropic 整块删除。

| 角色 | Skill | 解决什么切面 |
|------|-------|------------|
| 主 | [architecture-invariants](skills/architecture-invariants/SKILL.md) §4 | Assumption Registry + 4 种 prune 触发信号 |
| 辅 | [eval-driven-design](skills/eval-driven-design/SKILL.md) | `@[MODEL LAUNCH]` 门控 + 版本间回归检测 |
| 辅 | [feature-flag-system](skills/feature-flag-system/SKILL.md) | 渐进下线过时组件 |
| 辅 | [magic-docs](skills/magic-docs/SKILL.md) | 文档随对话演进防止说明过期 |

### FM-5: 评估信号噪音

**症状**：端态对了就说"通过"——但 agent 其实绕了大圈 / 用了危险工具 / 反复试错。或者反过来，轨迹看起来合理但最终状态错误。

| 角色 | Skill | 解决什么切面 |
|------|-------|------------|
| 主 | [eval-driven-design](skills/eval-driven-design/SKILL.md) Step 6-8（Step 9 *[见 PR #3](https://github.com/Bunnker/cc-harness/pull/3)* 待合并） | 轨迹 vs 端态 + pass@k vs pass^k + online/offline + **transcript shape（冗余/震荡/过早总结/能力下降，Step 9 内容）** |
| 辅 | [harness-verify](skills/harness-verify/SKILL.md) | 同时产出 verification.md（端态）+ commands.log（轨迹）+ audit-findings.md（shape 证据） |
| 辅 | [telemetry-pipeline](skills/telemetry-pipeline/SKILL.md) | online eval 的采样源 |

## 三、工具层失败

### FM-6: 工具选择成本爆炸

**症状**：工具变多后 Agent 花越来越多时间决定用哪个，或者用错工具。Anthropic 反例：60 工具全 loaded 时选择错误率显著上升。

| 角色 | Skill | 解决什么切面 |
|------|-------|------------|
| 主 | [agent-tool-budget](skills/agent-tool-budget/SKILL.md) | 默认 <20 + defer 加载 + 选择成本 |
| 主 | [tool-authoring](skills/tool-authoring/SKILL.md) | ACI 设计（文档质量、命名、自然文本格式） |
| 辅 | [unified-tool-interface](skills/unified-tool-interface/SKILL.md) | 工具契约一致性（命名冲突、schema 稳定） |
| 辅 | [mcp-runtime](skills/mcp-runtime/SKILL.md) | MCP 工具默认 deferred，只有 name 占上下文 |

### FM-7: 递归 / 无限循环

**症状**：Agent 调用自身、或多 agent 互相递归调用直到资源耗尽。

| 角色 | Skill | 解决什么切面 |
|------|-------|------------|
| 主 | [multi-agent-design](skills/multi-agent-design/SKILL.md) | `ALL_AGENT_DISALLOWED_TOOLS` 硬性递归防护 + AgentTool 对非 ant 用户禁用 |
| 主 | [agent-loop](skills/agent-loop/SKILL.md) | 10 种终态 + transition 追踪，防止循环无法退出 |
| 辅 | [concurrent-dispatch](skills/concurrent-dispatch/SKILL.md) | Bash 失败级联取消防止工具循环 |

### FM-8: 权限绕过 / 危险操作未经审批

**症状**：agent 直接 `rm -rf`、推生产、调用未授权 API。

| 角色 | Skill | 解决什么切面 |
|------|-------|------------|
| 主 | [layered-permission](skills/layered-permission/SKILL.md) | 顺序评估 + deny 不可覆盖的 fail-safe |
| 主 | [command-sandbox](skills/command-sandbox/SKILL.md) | 23 项检查 + AST 解析 + 解析器差异攻击防御 |
| 辅 | [plan-mode](skills/plan-mode/SKILL.md) | 执行前强制审批 |
| 辅 | [policy-limits](skills/policy-limits/SKILL.md) | 企业侧远程策略门控 |
| 辅 | [auth-identity](skills/auth-identity/SKILL.md) | 凭证管理不泄露 |

## 四、基础设施失败

### FM-9: Prompt Cache 命中率崩溃

**症状**：Agent 运行时发现大量 `cache_creation_tokens`，推理成本爆涨（如 10% fleet-wide）。

| 角色 | Skill | 解决什么切面 |
|------|-------|------------|
| 主 | [prompt-cache-economics](skills/prompt-cache-economics/SKILL.md) | cache key 稳定性 + 手术级变更 + 经济调度 |
| 辅 | [context-engineering](skills/context-engineering/SKILL.md) | 多源 System Prompt 组装 + 二级缓存 |
| 辅 | [speculative-execution](skills/speculative-execution/SKILL.md) | 用户未提交前预执行，命中则秒出 |
| 辅 | [multi-agent-design](skills/multi-agent-design/SKILL.md) | fork 的 `CacheSafeParams` 5 字段 byte-identical 约束 |

### FM-10: 孤儿进程 / 资源泄漏

**症状**：Agent 退出后仍有后台 Bash / MCP 连接 / 临时 worktree 存活。

| 角色 | Skill | 解决什么切面 |
|------|-------|------------|
| 主 | [process-lifecycle](skills/process-lifecycle/SKILL.md) | 优雅关闭 + 不留孤儿 + 不坏终端 |
| 辅 | [concurrent-dispatch](skills/concurrent-dispatch/SKILL.md) | 并发分区 + 错误级联取消 |
| 辅 | [platform-integration](skills/platform-integration/SKILL.md) | 防系统休眠 + 完成通知 |

### FM-11: 配置跨机器 / 跨团队漂移

**症状**：本机能跑别人跑不了；组织策略无法强制；同步后密钥意外扩散。

| 角色 | Skill | 解决什么切面 |
|------|-------|------------|
| 主 | [config-cascade](skills/config-cascade/SKILL.md) | 5 源合并 + 后者覆盖前者 + Zod 验证 |
| 主 | [settings-sync](skills/settings-sync/SKILL.md) | 跨设备同步不锁定 |
| 主 | [remote-managed-settings](skills/remote-managed-settings/SKILL.md) | 管理员远程覆盖 + 网络故障不阻塞 |
| 辅 | [team-memory-sync](skills/team-memory-sync/SKILL.md) | 团队共享记忆 + 密钥过滤 |
| 辅 | [instruction-file-system](skills/instruction-file-system/SKILL.md) | CLAUDE.md 向上遍历 + 条件规则 |
| 辅 | [policy-limits](skills/policy-limits/SKILL.md) | 企业功能禁用 |

### FM-12: 可观测性缺失

**症状**：用户等了 30 秒不知道 agent 在做什么；出问题后查不到当时的工具调用 / 输入 / 输出。

| 角色 | Skill | 解决什么切面 |
|------|-------|------------|
| 主 | [telemetry-pipeline](skills/telemetry-pipeline/SKILL.md) | 数据收集 + 隐私保护 |
| 主 | [runtime-summaries](skills/runtime-summaries/SKILL.md) | 运行中进度展示 |
| 主 | [harness-verify](skills/harness-verify/SKILL.md) | commands.log + diff.patch + verification.md 证据链 |
| 辅 | [ide-feedback-loop](skills/ide-feedback-loop/SKILL.md) | 代码修改后的错误自动感知 |
| 辅 | [tip-system](skills/tip-system/SKILL.md) | 等待时的相关提示而非空白 |

## 五、模型 / 交互进化失败

### FM-13: 模型换代行为回归

**症状**：新模型在已验证维度上回归（如 v4 → v8 false-claim 率从 16.7% → 29-30%）。

| 角色 | Skill | 解决什么切面 |
|------|-------|------------|
| 主 | [eval-driven-design](skills/eval-driven-design/SKILL.md) | `@[MODEL LAUNCH]` 门控 + A/B 验证 |
| 主 | [model-routing](skills/model-routing/SKILL.md) | 运行时动态选模型 + 凭证刷新 |
| 辅 | [api-client-layer](skills/api-client-layer/SKILL.md) | 多 Provider 抽象 + 重试 |
| 辅 | [architecture-invariants](skills/architecture-invariants/SKILL.md) §4 | 大版本升级强制重审 ASM 全部 |

### FM-14: 用户纠正未被内化

**症状**：用户同样的纠正要说 3 次；或者 agent 只记纠正不记确认，变得越来越保守。

| 角色 | Skill | 解决什么切面 |
|------|-------|------------|
| 主 | [agent-reflection](skills/agent-reflection/SKILL.md) | feedback 记忆双信号（纠正 + 确认） |
| 辅 | [agent-memory](skills/agent-memory/SKILL.md) | 跨会话持久化 feedback |
| 辅 | [magic-docs](skills/magic-docs/SKILL.md) | 文档根据对话演进 |

## 六、产出质量失败

### FM-15: 结构保真失败

**症状**：Worker 产出的代码**语法对 / 类型对 / 构建通过**，但破坏了模块边界、擅自改了公共接口、或违反了框架不变式。scorecard 的 `build_lint_typecheck` 过关，真实可维护性却崩盘——这是"虚高分数"最常见的来源，也是 Codex 审阅 HARNESS_EVOLUTION_PLAN.md 时点名的现有 FM 集合盲区。

**识别指标**：
- Worker 在输出开头没写 `INTERFACE_CHANGE:` 声明，但 diff 里公共 export 签名变了
- 修改路径超出 `target_paths`（越界实现）
- 新增行为分支没有对应测试
- 职责分层与相邻文件不一致（A 文件里做了 B 文件该做的事）

| 角色 | Skill | 解决什么切面 |
|------|-------|------------|
| 主 | [harness-verify](skills/harness-verify/SKILL.md) §6（代码审计） + scorecard 6 维 | `code_quality` 维度捕获结构保真问题，补齐单看 `build_lint_typecheck` 的盲区 |
| 主 | [harness](skills/harness/SKILL.md) Worker prompt 固定前缀 | `target_paths` 路径约束 + `INTERFACE_CHANGE:` 声明要求 + `ESCALATE:` 跨文件逃生舱 |
| 辅 | [multi-agent-design](skills/multi-agent-design/SKILL.md) | Sprint Contract 的 `scope_in` / `scope_out` 显式划定 Worker 的职责边界 |
| 辅 | [eval-driven-design](skills/eval-driven-design/SKILL.md) Step 9 *(见 PR #3)* | transcript shape 分析里的"过早自我总结"常对应此类失败——Worker 声称完成但没自审边界 |
| 辅 | [architecture-invariants](skills/architecture-invariants/SKILL.md) §四 | Assumption Registry 追踪哪些框架不变式是"升级后过期 vs 仍需守护" |

**为什么独立为一条 FM**：它不是工具问题（FM-6）、不是权限问题（FM-8）、也不是评估噪声（FM-5）——而是一个独立的**输出质量维度**。Codex 在审阅 HARNESS_EVOLUTION_PLAN.md 时显式指出这是现有 FM 集合的盲区，新合入的 `code_quality` 维度是第一个能观测它的工具。

## 七、不映射到失败模式的 skill

这些 skill 是**基础设施 / 能力扩展 / 教学**，不是为了治疗某个失败模式而存在。独立查阅即可：

| Skill | 用途 |
|-------|------|
| [harness](skills/harness/SKILL.md) | Coordinator 级企业工作流编排 |
| [harness-entry-points](skills/harness-entry-points/SKILL.md) | CLI / Headless / Bridge / SDK 四入口接入 |
| [harness-lite](skills/harness-lite/SKILL.md) | 简化版 harness |
| [agent-loop](skills/agent-loop/SKILL.md) | Agent 循环状态机参考（同时治 FM-7） |
| [plugin-loading](skills/plugin-loading/SKILL.md) | Skill / 插件加载 7 源合并 |
| [event-hook-system](skills/event-hook-system/SKILL.md) | 声明式 hook 扩展点 |
| [startup-optimization](skills/startup-optimization/SKILL.md) | 启动性能优化 |
| [voice-input](skills/voice-input/SKILL.md) | 语音输入能力 |
| [agent-architecture-curriculum](skills/agent-architecture-curriculum/SKILL.md) | 课程化学习路径（meta） |

## 如何使用本索引

**自顶向下（从症状找 skill）**：
1. 你观察到的是**行为失败**（agent 不该收尾却收尾 / 自我吹嘘 / 绕圈子）→ 第一、二节
2. 你观察到的是**工具失败**（选错 / 递归 / 越权）→ 第三节
3. 你观察到的是**基础设施失败**（慢 / 爆内存 / 丢状态）→ 第四节
4. 你观察到的是**版本 / 用户交互失败**（升级后变坏 / 纠正无效）→ 第五节

**自底向上（从 skill 理解它治什么）**：每个 skill 的 SKILL.md 开头都说了实现维度，本索引补充**"这个 skill 究竟防什么"**的反向视角。

**维护规则**：
- 新增 skill 时判断它是否治疗本文某个 FM，若是则登记为主/辅
- 新增 FM 时要求至少有一个主 skill 承载，否则说明识别出了真 gap（建新 skill 或扩现有 skill）
- 某个 FM 的主 skill 全被删除时触发警报——意味着某种失败现在无人照看

## 源与理论依据

- Anthropic "Effective harnesses for long-running agents"（FM-1、FM-2、FM-4 显式命名）
- Anthropic "Demystifying evals for AI agents"（FM-5 方法论）
- Anthropic "Building Effective Agents"（FM-6、FM-7 的 ACI 原则）
- Anthropic "Harness design for long-running application development"（FM-4 经典案例、FM-3 artifacts）
- Claude Code 源码（FM-8、FM-9、FM-10 的具体实现边界）
