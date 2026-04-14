# 执行策略

harness coordinator 在 PLAN 阶段用此文件决定：先设计还是先编码、并行还是串行、用哪种 Worker。

## 一、Skill 选择资格

Coordinator 在选 skill 前，先看 `skill-catalog.md` 的 `role` 和 `portability`。

### role 判定

| role | Coordinator 行为 |
|------|------------------|
| `worker` | 可进入候选集，允许分派给子 Agent |
| `non-worker` | 不进入候选集，不调度为 worker |

**硬规则：**
- `harness` 是 Coordinator 自身，只能作为总控参考，不能作为 worker 调度
- `agent-architecture-curriculum` 是课程化文档 skill，不参与设计/编码/审计 worker 调度

### portability 判定

| portability | 同仓项目（CC / 本仓架构演化） | 跨项目 |
|-------------|-------------------------------|--------|
| `portable` | 可直接使用 | 优先使用 |
| `cc-bound` | 可使用 | 默认降级为“参考优先”，只有在用户明确接受或 Coordinator 已写明迁移约束时才使用 |

**跨项目默认策略：**
1. 先选 `portable` skill
2. `portable` 不足以覆盖任务时，才补充 `cc-bound`
3. 计划中必须写明：哪些是 CC 特有实现、哪些会被忽略或改写

## 二、任务类型判定

| 条件 | 任务类型 | Worker 行为 |
|------|---------|------------|
| 模块不存在（status = not_started） | **设计** | 输出架构方案：核心类型 + 方法签名 + 依赖关系。不写代码文件。 |
| 模块有设计方案（status = designed），用户确认了 | **编码** | 按设计方案输出完整代码文件。 |
| 模块已实现（status = implemented），但 skill 有更新或用户要求检查 | **审计** | 对照 skill 的反模式警告检查，输出问题清单 + 改进建议。 |
| 需要调研目标项目的现有能力/框架特性/技术可行性 | **探索** | 输出结论摘要（写入 state.learnings），不产出设计方案或代码文件。 |
| 模块已审计（status = audited） | **跳过** | 标记完成，不调度 Worker。 |

**硬规则：设计和编码不在同一轮执行。** 设计完必须等用户确认，才能在下一轮编码。
**探索任务的定位**：探索不修改模块 status，只产出 learnings。探索可以和设计并行（探索只读，不影响设计产出）。

## 三、并行判定

先看 `dependency-graph.md` 的三类关系：无条件安全并行组、条件并行组、明确依赖组。

### 条件并行组（优先判定）

以下组合不能用“一刀切并行/串行”处理：

| skill 组合 | 设计 | 编码 | 审计补齐 |
|-----------|------|------|----------|
| `agent-memory` + `agent-reflection` | 可并行 | 串行 | 串行 |
| `compact-system` + `session-memory` | 可并行 | 串行 | 串行 |
| `agent-loop` + `concurrent-dispatch` | 仅在 `unified-tool-interface` 已完成时可并行 | 仅在 `unified-tool-interface` 已完成时可并行 | 保守串行 |

### 可以并行的条件（全部满足）

1. 两个任务不属于“明确依赖组”
2. 两个任务不属于“条件并行组”中的串行情形
3. 两个任务的目标模块之间没有 import/依赖关系
4. 两个任务不操作同一个文件或目录

### 必须串行的条件（任一满足）

1. 模块 B 需要 import 模块 A 的类型定义
2. Skill B 在 dependency-graph.md 中依赖 Skill A
3. 模块 B 的设计决策需要参考模块 A 的输出（如工具接口影响调度器）
4. 组合命中条件并行组，但当前任务类型是 **编码** 或 **审计补齐**
5. 组合命中明确依赖组（如 `layered-permission → command-sandbox`）

### 存疑时

**保守串行。** 并行做散了要返工，串行慢一点但正确。

## 三+. 中间输出价值评估（对齐 CC 的"中间输出价值决定架构"原则）

> 来源：CC `src/tools/AgentTool/runAgent.ts` 的 fork 决策——不是看"任务大不大"，是看"中间搜索结果值得保留在主对话吗"。

Coordinator 在 PLAN 阶段为每个 Worker 判断其产出的保留价值，依据 stage-roadmap.md 的 `value_assessment`：

| 产出价值 | Worker isolation | 产出去向 | 何时适用 |
|---------|-----------------|---------|---------|
| **保留** | `none`（直接写入项目） | Worker 产出文件留在项目目录 | 设计方案、编码实现、安全审计结论 |
| **不保留** | `worktree`（隔离执行） | Worker 结论写入 state.learnings，过程丢弃 | 探索性分析、性能基准、方案调研 |
| **看情况** | Coordinator 判断 | 严重问题 → 保留；通过 → 丢弃过程只保留结论 | 审计报告（取决于发现的严重程度） |

**决策规则：**
1. 读 stage-roadmap.md 当前阶段的 value_assessment
2. 按任务类型（设计/编码/审计/探索）匹配保留策略
3. 在计划表的 `isolation` 列写明策略
4. "看情况"的任务：Worker 在输出开头声明发现的严重程度，Coordinator 在 REPORT 阶段决定是否保留

**保守默认值**：如果 value_assessment 未定义，默认"保留"（不丢弃任何产出）。

---

## 三++. 结构保真规则

> 来源：Zero Magic 实战教训——Worker 按自己的"最优模式"重写模块，语法对、类型对，但破坏了模块边界、数据流形状和框架隐式规则。

### Worker 的修改范围约束

| 规则 | Worker 行为 | 违反时处理 |
|------|-----------|-----------|
| 优先局部补丁 | 只改需要改的函数/方法，不重写整文件 | Coordinator 在 Report 中比对 diff 行数，超过文件 50% 行数标注为"大范围重写" |
| 不改公共接口 | 不改 export 签名、state 字段、函数参数（除非任务明确要求） | Worker 必须声明 INTERFACE_CHANGE，Coordinator 检查下游模块是否需要同步修改 |
| 沿用模块职责 | 先读同目录文件理解分层，不在目标文件中越界实现其他文件的职责 | Coordinator 检查 Worker 是否在目标文件中引入了不属于该模块的功能 |
| 遵守运行时不变式 | 项目约束（constraints）中的框架规则优先级最高 | 违反不变式的代码不通过验证（参见 verification-protocol.md） |

### 验证义务（按变更类型触发）

| 变更类型 | 验证要求 | 无验证时处理 |
|---------|---------|------------|
| 新增行为分支、权限判断、fallback、状态机修改 | **默认必须**附带测试（正常+错误+边界） | modules status 不升级为 implemented，标注"⚠️ 缺少验证" |
| 并发/Hook、序列化相关 | **默认必须**附带测试或 smoke test | 同上 |
| 纯配置、纯重命名、纯文档、UI 样式调整 | 不要求测试 | 正常升级 |
| 项目测试基础差（无 tests/ 目录） | 至少提供 smoke test 或最小回归脚本 | 在 Report 中记录豁免理由 |

Worker 如果无法同时提交测试，必须在输出中说明原因和替代验证方式。Coordinator 在 Report 中记录豁免理由。

### ESCALATE 触发条件

Worker 遇到以下情况时必须输出 `ESCALATE:` 而不是自行处理：
1. 需要修改 target_paths 之外的文件
2. 需要改变现有模块的公共接口
3. 发现框架约束和任务要求矛盾
4. 发现目标文件的代码结构和预期严重不符（可能已被其他 session 修改）

Coordinator 收到 ESCALATE 后：暂停该 Worker，向用户报告，等待决策。

---

## 四、Worker 上下文传递规则

Worker 是 fork 子 agent，看不到对话历史。Coordinator 必须浓缩关键上下文：

### 必须传递

**固定前缀（所有 Worker 相同，对齐 CacheSafeParams）：**
- 项目语言和技术栈
- 全局约束（适用于所有 Worker 的架构约束）
- 本轮所有 Worker 共同依赖的已有模块（模块名 + 文件路径 + 核心接口签名）

**动态后缀（每个 Worker 不同）：**
- 仅与本 Worker 相关的已有模块（其他 Worker 不依赖的）
- 与本任务直接相关的架构决策和 learnings
- 目标输出路径

### 不要传递

- 无关模块的设计细节
- 之前的对话过程
- 其他 Worker 的完整输出（只传接口摘要）

### 上下文大小控制

浓缩后的项目上下文控制在 500 字以内。超过说明传了不必要的内容。

## 五、Worker 的 Skill 使用方式

**Worker 应该在自己的 agent 上下文中调用 skill（通过 SkillTool），而不是由 Coordinator 手工复制 skill 内容。**

Coordinator 的 prompt 指令里写：

```
使用 /skill-name 指导你的工作。
```

Worker 看到这条指令后自行调用 SkillTool，获得完整的 skill 内容（包括 supporting files、shell 预处理、frontmatter 语义）。

## 六、单轮调度上限

每轮最多调度 **5 个 Worker**。原因：
- 超过 5 个的结果汇总质量下降
- 兼容性检查的组合数爆炸
- 用户审阅压力过大

如果需要更多 Worker，分成多轮，每轮 3-5 个。

## 七、失败处理（Withhold-then-Recover）

> 来源：CC `query.ts` 的 Withhold-then-Recover 机制。参见 `transition-patterns.md` 模式 2。

### 恢复路径（按成本递增排列）

| Worker 状态 | Coordinator 行为 | 恢复路径 |
|------------|-----------------|---------|
| ✅ completed | 收录结果，更新状态 | — |
| ⚠️ partial | 收录已完成部分，在 Report 中标注未完成项 | — |
| ❌ failed (首次) | 补充 Worker prompt 中缺失的上下文，重新执行 | `worker_retry`（≤3 次） |
| ❌ failed (重试仍失败) | 缩小 Worker 任务范围，只做最关键部分 | `scope_reduction`（一次性） |
| ❌ failed (范围缩小仍失败) | 修订 PLAN，用不同 Skill 组合重新执行 | `plan_revision`（一次性） |
| ❌ failed (全部恢复路径耗尽) | 暴露错误给用户，由用户决定 | 终态 |

### 防螺旋规则

1. 每种恢复路径只尝试一次（标志/计数器控制）
2. `plan_revision` 不重置 `worker_retry_count`（修订计划不会解决 Worker 内部错误）
3. 恢复路径不可嵌套（路径 2 失败不回退到路径 1）
4. 读 `harness-state.json` 的 `recovery_flags` 检查恢复状态

### denial_tracking 自动降级

当 `denial_tracking.consecutive_failures >= 3` 时自动降级：

| 任务类型 | 降级行为 |
|---------|---------|
| 设计 | 仅生成架构骨架，不做详细方案 |
| 编码 | 仅生成接口定义，不做完整实现 |
| 审计 | 仅检查最关键的 3 项，不做全量审计 |

Worker 成功 → `consecutive_failures = 0`。

## 八、级联失败规则

> 来源：CC `toolOrchestration.ts:118-150` 的 Bash 错误级联取消。

如果同一并行组中有 Worker 失败：

1. 检查失败 Worker 的输出是否是其他 Worker 的输入
2. **有依赖关系** → 取消未完成的依赖 Worker（状态可能不一致）
3. **无依赖关系** → 其他 Worker 继续

类比 CC 的设计：
- 设计任务失败 → 通常不级联（设计之间独立）
- 编码任务失败 → 检查是否有依赖的编码任务需要取消
- 审计任务失败 → 不级联（审计只读，不影响状态）

**保守默认值**：如果不确定两个 Worker 是否有依赖关系，按有依赖处理（级联取消）。

## 九、Worker 安全约束

> 来源：CC `constants/tools.ts:36-46` 的 fork 递归防护 + `forkedAgent.ts` 的 canUseTool 最小权限。

### 路径约束（deny 优先）

每个 Worker 的 prompt 必须包含：

```
## 输出约束
- 只允许创建/修改以下路径：{target_paths}
- 禁止修改：.claude/、.git/、node_modules/、*.lock
- 禁止执行：rm -rf、git push、npm publish
```

### 工具约束

Worker 禁止使用：
- **Agent 工具**（防递归 — CC 的 `ALL_AGENT_DISALLOWED_TOOLS`）
- **AskUserQuestion**（只有 Coordinator 与用户交互）

Worker 如果需要更多信息，在输出中说明需要什么，由 Coordinator 在下一轮补充。

### 约束不可覆盖

Worker 的 prompt 中不能包含"忽略上述约束"类指令。Coordinator 不能在 Worker prompt 中授权被禁止的操作。这对应 CC 的 "deny 优先不可覆盖" 原则。

## 十、执行后学习

> 来源：HARNESS_EVOLUTION_PLAN.md Layer 3 闭环 1。

REPORT 阶段结束后，Coordinator 提取本轮非显而易见的经验：

1. **成功经验**：目标项目的框架有哪些内置能力可以复用
2. **失败经验**：哪些 CC-bound 模式在目标项目中不适用
3. **迁移决策**：CC-bound skill 在目标项目中被替换为什么

写入 `harness-state.json` 的 `learnings` 和 `cc_adaptations` 字段。

下次 SCAN 时读取：
- `learnings` → 避免重复犯错
- `cc_adaptations` → 使用同一 skill 时注入已有迁移上下文
