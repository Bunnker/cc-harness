# Harness 编排层：状态机 Transition 设计模式参考

> 来源：CC `src/query.ts` 源码抽象 | 日期：2026-04-03
> 目的：为 harness 的 SCAN→PLAN→EXECUTE→REPORT 状态机提供可迁移的 transition 设计模式

---

## 一、CC Query Loop 的 5 个可迁移模式

### 模式 1：Transition Reason 防螺旋

**CC 怎么做**：
每次 `continue` 都记录 `transition.reason`，恢复路径在决策前检查 reason 避免重复尝试同一恢复。

```
// CC 的三重防护体系
1. 一次性布尔标志  → hasAttemptedReactiveCompact（只试一次）
2. 计数器 + 上限  → maxOutputTokensRecoveryCount < 3
3. reason 检查     → transition.reason !== 'collapse_drain_retry'
```

**Harness 怎么用**：

```json
// harness-state.json 的 transition 追踪
{
  "current_phase": "EXECUTE",
  "transition": {
    "reason": "worker_retry",
    "attempt": 2,
    "from_phase": "EXECUTE"
  },
  "recovery_flags": {
    "has_attempted_plan_revision": false,
    "worker_retry_count": 0,
    "max_worker_retries": 3
  }
}
```

Coordinator 在 EXECUTE 阶段 Worker 失败时：
1. 检查 `worker_retry_count < max_worker_retries` → 重试
2. 重试后仍失败 → 检查 `has_attempted_plan_revision` → 修订计划后重试
3. 修订后仍失败 → 暴露错误给用户（不再重试）

**反模式**：CC 的 `stop_hook_blocking` 故意不重置 `hasAttemptedReactiveCompact`（query.ts:1292-1296）。Harness 类比：如果 Worker 失败后 Coordinator 修订了计划再重试，不要重置 `worker_retry_count`——修订计划不会解决 Worker 内部的重复错误。

---

### 模式 2：Withhold-then-Recover（扣住后恢复）

**CC 怎么做**：
可恢复错误不立即暴露给调用方。流式阶段扣住，退出决策阶段按成本递增尝试恢复，全部失败才暴露。

```
CC 的恢复成本排列：
  collapse drain（便宜，保留粒度上下文）
  → reactive compact（昂贵，生成摘要）
  → 暴露错误（终态）
```

**Harness 怎么用**：

```
Worker 返回异常结果：
  ├─ 扣住异常（不立即在 Report 中暴露）
  │
  ├─ 尝试恢复路径 1（便宜）：
  │    补充 Worker prompt 中缺失的上下文，重新执行
  │    └─ 条件：transition.reason !== 'context_补充_retry'
  │
  ├─ 尝试恢复路径 2（中等）：
  │    缩小 Worker 任务范围（只做最关键部分）
  │    └─ 条件：!has_attempted_scope_reduction
  │
  ├─ 尝试恢复路径 3（昂贵）：
  │    修订 PLAN，用不同 Skill 组合重新执行
  │    └─ 条件：!has_attempted_plan_revision
  │
  └─ 全部失败 → 暴露错误给用户
```

**关键约束**：每种恢复只试一次。恢复路径之间不可嵌套（恢复路径 2 失败不能回到路径 1）。

---

### 模式 3：State 对象 + Continue 赋值点

**CC 怎么做**：
所有跨迭代状态放在一个 `State` 对象中。每个 continue 点通过 `state = { ...next }` 一次性赋值，不做零散的 `state.x = ...` 修改。这让每个 continue 点的状态变更一目了然。

```typescript
// CC 的 7 个 continue 赋值点都是同一模式：
state = {
  messages: [...],                    // 总是显式
  toolUseContext,                     // 有时从 update 来
  hasAttemptedReactiveCompact,        // 有时保留有时重置
  maxOutputTokensRecoveryCount: 0,    // 大多数 continue 重置为 0
  transition: { reason: 'xxx' },      // 总是显式
  // ... 其余字段
}
continue
```

**Harness 怎么用**：

```json
// 每个阶段跳转都是完整的 state 快照写入
{
  "current_phase": "EXECUTE",
  "modules": { ... },
  "transition": { "reason": "worker_retry", "attempt": 2 },
  "recovery_flags": { ... },
  "last_phase_result": { ... }
}
```

Coordinator 在阶段跳转时写入完整 state，不做增量修改。这样 SCAN 阶段读取 state 时，总是看到一致的快照。

---

### 模式 4：分层 Hook（角色无关 + 角色相关）

**CC 怎么做**：
`stopHooks.ts` 先执行所有角色无关的 Stop hooks，再根据 `isTeammate()` 决定是否执行 TaskCompleted + TeammateIdle hooks。

```
Stop hooks → 全部角色都执行
  ↓ 通过
Teammate hooks → 仅 teammate 角色执行
  ├─ TaskCompleted hooks（对每个 in_progress 任务）
  └─ TeammateIdle hooks
```

**Harness 怎么用**：

```
REPORT 阶段的 Hook 链：

1. 通用检查 hooks（所有阶段都执行）：
   ├─ 状态文件一致性检查
   ├─ Worker 输出完整性检查
   └─ 跨 Worker 接口对齐检查

2. 阶段特定 hooks（按当前阶段决定）：
   ├─ 设计阶段 → 架构一致性检查
   ├─ 编码阶段 → 测试通过检查
   └─ 审计阶段 → 安全扫描检查

3. 项目特定 hooks（按项目类型决定）：
   └─ 如果有 harness-hooks.json → 执行自定义检查
```

---

### 模式 5：Fire-and-Forget 后台管道 + 独立门控

**CC 怎么做**：
`stopHooks.ts:136-157` 的三个后台任务各有独立门控，全部 `void`（fire-and-forget），互不影响。

```
if (!isBareMode()) {                              // 总开关
  if (!isEnvDefinedFalsy(env.PROMPT_SUGGESTION))   // 独立门控 1
    void executePromptSuggestion(ctx)
  if (feature('EXTRACT_MEMORIES') && !agentId && isExtractModeActive())  // 独立门控 2
    void executeExtractMemories(ctx)
  if (!agentId)                                    // 独立门控 3
    void executeAutoDream(ctx)
}
```

**Harness 怎么用**：

```
REPORT 阶段结束后的后台任务：

if (!是精简模式) {
  if (learnings 功能启用)        → void 提取本轮学习经验
  if (cc_adaptations 功能启用)   → void 记录 CC-bound 迁移决策
  if (denial_tracking 启用)      → void 更新拒绝追踪计数器
}
```

每个后台任务独立门控、fire-and-forget。一个任务失败不影响其他任务，也不影响 REPORT 的主流程。

---

## 二、Harness 状态机迁移方案

### CC Query Loop → Harness 编排层的映射

| CC 概念 | Harness 对应 | 说明 |
|---------|-------------|------|
| `while(true)` | 跨会话 SCAN→PLAN→EXECUTE→REPORT 循环 | CC 是单次会话内循环；harness 是跨会话循环 |
| `State` 对象 | `harness-state.json` | CC 在内存中；harness 在文件系统中 |
| `transition.reason` | `harness-state.json.transition` | 防螺旋机制相同 |
| `needsFollowUp` | `modules[].status !== 'completed'` | 还有模块未完成 → 继续 |
| `maxTurns` | 阶段最大轮次（可按 stage-roadmap 配置） | 兜底退出 |
| `handleStopHooks()` | REPORT 阶段的检查链 | 退出前的最后关卡 |
| `token budget` | 不适用 | harness 没有 token 预算概念 |
| `abortController` | 用户在确认步骤拒绝 | 不同的中断机制 |

### Harness 的 Transition 清单

**终态**（退出循环）：

| reason | 触发条件 |
|--------|---------|
| `completed` | 所有模块 status === 'designed' 或 'implemented' |
| `user_rejected` | 用户在确认步骤拒绝计划 |
| `max_rounds` | 超过阶段允许的最大轮次 |
| `all_workers_failed` | 同一批次所有 Worker 失败 + 恢复路径耗尽 |
| `scope_reduced_to_zero` | 经过多次降级后没有可执行的任务 |

**续跑**（continue 到下一轮）：

| reason | 触发条件 | 防螺旋 |
|--------|---------|--------|
| `next_stage` | 当前阶段完成，进入下一阶段 | 无需防护 |
| `worker_retry` | Worker 失败，补充上下文重试 | 计数器 ≤ 3 |
| `scope_reduction` | Worker 失败，缩小任务范围重试 | 一次性标志 |
| `plan_revision` | 多次失败，修订计划 | 一次性标志 |
| `partial_completion` | 部分 Worker 成功，重新调度失败的 | 递减检测 |

---

## 三、实施检查清单

以下改动对齐 HARNESS_EVOLUTION_PLAN.md 的 P0+P1：

### 已通过本轮验证可立即实施的

- [ ] **SKILL.md Phase 3**：在 Worker 调度前检查 `transition.reason`，防止同一恢复路径重复执行
- [ ] **state-schema.md**：加入 `transition` 和 `recovery_flags` 字段
- [ ] **execution-policy.md**：加入 Withhold-then-Recover 的恢复路径排列规则
- [ ] **SKILL.md Phase 4**：加入分层 Hook 执行顺序（通用检查 → 阶段特定检查）
- [ ] **SKILL.md Phase 4**：加入 fire-and-forget 后台学习任务（独立门控）

### 需要后续轮次（轮 2-5）验证才能实施的

- [ ] Worker 工具约束（需轮 2 fork 隔离验证）
- [ ] deny 优先不可覆盖（需轮 3 权限验证）
- [ ] 分级压缩迁移（需轮 4 压缩验证）
- [ ] 阶段跳过门控（需轮 5 门控验证）
