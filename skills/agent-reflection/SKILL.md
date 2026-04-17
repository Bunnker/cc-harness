---
name: agent-reflection
description: "Agent 反思与进化：feedback 记忆（纠正+确认）+ extractMemories 模块（615 行）+ autoDream 模块（324 行）+ denialTracking（45 行）+ 3 组 eval 实验注释"
user-invocable: false
argument-hint: "<目标项目路径或模块名>"
---

# Agent 反思与自我进化

> 参考实现：`src/memdir/memoryTypes.ts`（记忆类型 + eval 注释）、`src/services/extractMemories/`（后台提取，615 行）、`src/services/autoDream/`（定期整理，324 行）、`src/utils/permissions/denialTracking.ts`（自适应降级，45 行）

## 源码事实

### 1. Feedback 记忆同时捕获纠正和确认——这是源码原文

```typescript
// src/memdir/memoryTypes.ts:134 — 原文
"Record from failure AND success: if you only save corrections, 
 you will avoid past mistakes but drift away from approaches the 
 user has already validated, and may grow overly cautious."
```

**检测信号**（`memoryTypes.ts:61`，原文）：
```
纠正："no not that", "don't", "stop doing X"
确认："yes exactly", "perfect, keep doing that", 接受非常规选择但没 pushback

"Corrections are easy to notice; confirmations are quieter — watch for them."
```

**结构要求**（`memoryTypes.ts:63`，原文）：
```
Lead with the rule itself, then:
  **Why:** (the reason — often a past incident or strong preference)  
  **How to apply:** (when/where this guidance kicks in)
Knowing *why* lets you judge edge cases instead of blindly following the rule.
```

### 2. extractMemories 是真实的 615 行模块，不是几个函数

`src/services/extractMemories/` 的真实结构：

```
闭包状态（initExtractMemories 内部）：
  inFlightExtractions: Set     — 追踪进行中的提取（带超时排空）
  lastMemoryMessageUuid        — 增量处理游标
  turnsSinceLastExtraction     — 节流计数器
  pendingContext               — 合并暂存

主流程（runExtraction）：
  1. 节流检查（tengu_bramble_lintel gate，默认每 1 轮）
  2. 互斥检查（hasMemoryWritesSince → 主 Agent 已写则跳过）
  3. 扫描现有记忆（formatMemoryManifest）
  4. runForkedAgent（带受限工具集）
  5. 提取写入路径 + 日志事件 + 追加系统消息

导出函数：
  executeExtractMemories()     — 公共入口，从 stopHooks 调用（fire-and-forget）
  drainPendingExtraction()     — 优雅关闭前的软超时排空
  createAutoMemCanUseTool()    — 工具权限封装（Read/Grep/Glob 只读 + Edit/Write 仅限 memdir）
```

### 3. autoDream 门控链 + consolidationLock 互斥（源码验证 `autoDream.ts:122-272` + `consolidationLock.ts`）

**前置条件**（`isGateOpen()` :95-99，每轮 zero-cost 检查）：
```
非 KAIROS 模式 && 非远程模式 && auto memory 开启 && isAutoDreamEnabled()
```

**3 道门控**（`runAutoDream` 内部，cheapest-first 顺序）：
```
门控 1 — 时间门：readLastConsolidatedAt() → hoursSince < cfg.minHours(默认24h) → return
门控 2 — 扫描节流：距上次 session scan < 10 分钟 → return（防止时间门通过但会话门不通过时反复扫描文件系统）
门控 3 — 会话门：listSessionsTouchedSince(lastAt) → 过滤当前 session → count < minSessions(默认5) → return
```

**consolidationLock 互斥**（`consolidationLock.ts`）：
```
锁设计：文件 mtime = lastConsolidatedAt，文件内容 = holder PID
  
获取锁（tryAcquireConsolidationLock :46-83）：
  1. stat + readFile 并行读取 mtime 和 PID
  2. if (mtime 在 1h 内 && PID 存活) → return null（被锁住）
  3. if (PID 死亡 || mtime > 1h) → 回收锁（PID 复用防护）
  4. writeFile(自己的 PID)
  5. readFile 验证 → 两个进程同时写，后写的 PID 赢 → 另一个 bail out
  
回滚锁（rollbackConsolidationLock :91-108）：
  fork 失败 → utimes 回退 mtime 到 priorMtime → 清空 PID body
  priorMtime = 0 → unlink（恢复"从没整理过"的状态）
```

**关键设计**：mtime 做双重用途（时间门 + 锁标记），一个 stat 调用覆盖两个功能。per-turn cost = 1 stat。

**fork 执行**（`autoDream.ts:210-271`）：
```
注册 DreamTask（UI 进度）→ 构建 prompt → runForkedAgent({
  canUseTool: createAutoMemCanUseTool(memoryRoot),  // Bash 只读 + Edit/Write 仅 memdir
  skipTranscript: true,
  onMessage: makeDreamProgressWatcher(taskId)  // 提取 text + 统计 tool_use + 收集 file_path
})
→ completeDreamTask / failDreamTask
→ 失败时 rollbackConsolidationLock(priorMtime) + 扫描节流做退避
→ 被 abort 时：DreamTask.kill 已经回滚和设 killed，不重复处理
```

### 3a. backgroundHousekeeping 注册入口（源码验证 `utils/backgroundHousekeeping.ts:31-93`）

```
startBackgroundHousekeeping() 注册顺序（启动时立即执行）：
  1. initMagicDocs()              — 文档自动演进
  2. initSkillImprovement()       — skill 改进钩子
  3. initExtractMemories()        — 后台记忆提取（feature-gated: EXTRACT_MEMORIES）
  4. initAutoDream()              — 后台记忆整理（always on，内部有 isGateOpen 门控）
  5. autoUpdateMarketplacesAndPluginsInBackground()  — 插件自动更新
  6. ensureDeepLinkProtocolRegistered()  — 深度链接协议（feature-gated: LODESTONE, interactive only）

延迟 10 分钟后执行的慢操作（让出用户交互优先）：
  7. cleanupOldMessageFilesInBackground()
  8. cleanupOldVersions()
  如果用户在最近 1 分钟内有交互 → 再延迟 10 分钟
```

**可迁移模式**：后台任务分"立即初始化"和"延迟执行"两档。立即初始化的任务注册 hook 但不消耗资源；延迟执行的慢任务在用户空闲时才运行。

### 4. denialTracking 是真实的 45 行模块

```typescript
// src/utils/permissions/denialTracking.ts — 完整源码
export const DENIAL_LIMITS = {
  maxConsecutive: 3,   // 连续 3 次被拒 → 降级
  maxTotal: 20,        // 累计 20 次被拒 → 降级
}

export function shouldFallbackToPrompting(state: DenialTrackingState): boolean {
  return (
    state.consecutiveDenials >= DENIAL_LIMITS.maxConsecutive ||
    state.totalDenials >= DENIAL_LIMITS.maxTotal
  )
}
```

**使用位置**：`src/utils/permissions/permissions.ts:490` — auto mode 在评估权限前检查 denialTracking 状态。

### 5. 源码中有 3 组 eval 实验注释——不是"每条 prompt 都验证"

| 实验 | 文件/行号 | 结果 | 改变了什么 |
|------|----------|------|-----------|
| **H2: 显式保存门** | `memoryTypes.ts:192-194` | 0/2 → 3/3 | 加了"即使用户要求也不存噪音数据" |
| **H1/H5: 回忆前验证 + 快照漂移** | `memoryTypes.ts:228-256` | H1: 0/2→3/3, H5: 0/2→3/3 (appendSP) | 验证规则从子弹点升级为独立 section |
| **H6: 分支污染防护** | `memoryTypes.ts:207-222` | 1/3 on capy | 加了"ignore=不引用"而非"acknowledge+override" |

**额外的 MODEL LAUNCH 注释**（`prompts.ts:210-237`）：
- Capybara v8 thoroughness/assertiveness counterweight → pending A/B
- False-claims mitigation: v4 16.7% → v8 29-30% → 需要 prompt 缓解

**这些是设计决策的实验证据，不是运行时代码。** 没有 eval 结果存储在数据结构中，没有"每条 prompt 都验证"的机制。

### 6. 回忆前验证是 prompt 指令，不是代码逻辑

```typescript
// src/memdir/memoryTypes.ts:240-256 — TRUSTING_RECALL_SECTION
// 注入到 system prompt 中的文本指令

"## Before recommending from memory

A memory that names a specific function, file, or flag is a claim 
that it existed *when the memory was written*. It may have been 
renamed, removed, or never merged. Before recommending it:

- If the memory names a file path: check the file exists.
- If the memory names a function or flag: grep for it.
- If the user is about to act on your recommendation: verify first.

'The memory says X exists' is not the same as 'X exists now.'"
```

**这是 prompt engineering 指令，不是代码级验证。** 模型收到这条指令后自行决定是否 grep/check。没有硬编码的"回忆前自动验证"逻辑。

---

## 7. Self-Evaluation Blind Spot：自评盲点与外部校验

> 来源：Anthropic "Effective harnesses for long-running agents" + "Demystifying evals for AI agents" 显式命名的失败模式：
> 
> *When asked to evaluate the work they produced, agents tended to confidently praise their work — even when the quality was obviously mediocre to a human observer.*

**定义**：让 Agent 评估自己刚产出的工作，它会倾向于认为"一切良好"——这是系统性偏差，不是个别模型的问题。**和 context anxiety 并列为当前最重要的两个 harness 设计驱动力**。

**成因**（Anthropic 原文）：
> Calibrating an independent evaluator to be skeptical proved easier than getting generators to critique their own work.

→ 直白说：让一个 fresh-context 的评估 agent 怀疑，比让产出 agent 自我怀疑**容易得多**。设计上应该接受这个不对称，而不是试图修好"自我批评"。

### 三种外部校验信号（按成本递增）

| 信号源 | 实现 | 可靠性 | 局限 |
|--------|------|--------|------|
| **1. 确定性 Oracle** | 测试、linter、schema 校验、类型检查、编译 | 最高（0/1 二值） | 只覆盖能被自动判断的维度 |
| **2. 独立 Evaluator Agent** | 新 context、新 session 的 Agent 读 diff + 运行验收脚本 | 高（可校准） | 成本比自评高 2-3×，但远低于人工 |
| **3. 人类反馈循环** | 用户纠正/确认，进入 feedback 记忆（本 skill 开头已覆盖） | 最高但最慢 | 延迟大、样本稀疏 |

**组合规则**：
- 有 Oracle 可用 → 永远先跑 Oracle（`harness-verify` 已落实）
- Oracle 无法覆盖的质量维度（设计合理性、用户体验、代码可读性）→ 独立 Evaluator
- Evaluator 不确定的边界 → 用户反馈

**不应做**：跳过 Oracle 直接让 Agent 自评"代码是否合理"——这是把 self-eval blind spot 当成唯一信号源。

### 独立 Evaluator 的校准提示模板

直接问"这个对吗？" → Evaluator 倾向说对。改问法：

```
你在审查一段代码 / 一份设计。假设它 **有问题**。请列出：
1. 最可能出错的 3 个地方（不是"可能优化的地方"）
2. 每个地方的失败场景（具体输入 → 具体错误输出）
3. 如果只能修一个，修哪个？为什么？

规则：
- 不要说"看起来不错" / "总体合理"——这不是评估，是投票
- 如果找不到真实问题，明确输出 "NO_ISSUES_FOUND"
- NO_ISSUES_FOUND 会被记录并用于后续校准
```

**为什么管用**：问"假设有问题"激活了怀疑先验；要求具体失败场景过滤掉空泛夸奖；允许 NO_ISSUES_FOUND 避免"为挑刺而挑刺"的噪音。

### 盲点识别的自我提示（降级方案，只在没有独立 Evaluator 时用）

当确实没有独立 Evaluator（如单 Agent 场景），可以用以下结构化提示降低自评 bias——**但这只是降级，不是替代**：

```
完成工作后，不要直接说"done"。回答：
1. 刚才最有可能出错的地方是什么？（一句话）
2. 如果用户来验，他们最可能在哪里发现问题？（一句话）
3. 我有没有跳过任何 exit_criteria？（列出原文 vs 我做的）
4. 基于 1-3，我的置信度是 [HIGH / MEDIUM / LOW]
```

**关键**：要求模型输出 MEDIUM/LOW 的具体条件，否则一律输出 HIGH。Anthropic 的文章点明了这一点——自评的默认结论就是"一切良好"，必须显式创造"不良好"的可观测证据。

### 何时接受"无法消除盲点"

- 探索性调研（没有 exit_criteria，Evaluator 无从校准）
- 开放创意任务（"设计一个有趣的 UI"——没有客观失败定义）
- 成本敏感的高频小任务（每次都请 Evaluator 经济上不成立）

**这些场景下承认盲点存在，不要假装做了 self-eval 就等于通过了**——把"未经外部校验"作为状态诚实返回给用户，让用户决定是否信任。

---

## 可迁移设计

### feedback 双信号捕获

你的项目应该做的：

```python
def detect_feedback(user_message, context):
    """同时捕获纠正和确认——只记纠正会让 Agent 越来越保守"""
    
    correction_signals = ["不要", "别", "stop", "don't", "wrong"]
    confirmation_signals = ["exactly", "perfect", "好的就这样"]
    
    for kw in correction_signals:
        if kw in user_message.lower():
            return {"type": "correction", "signal": user_message}
    
    for kw in confirmation_signals:
        if kw in user_message.lower():
            return {"type": "confirmation", "signal": user_message}
    
    # 沉默确认：非常规选择没被反对
    if context.get("last_action_unusual") and not is_rejection(user_message):
        return {"type": "silent_confirmation"}
    
    return None
```

### 后台提取 + 互斥 + 合并

```python
class BackgroundExtractor:
    def __init__(self):
        self._running = False
        self._pending = None
    
    async def maybe_extract(self, messages, main_wrote_memory: bool):
        if main_wrote_memory: return    # 互斥：主 Agent 已写
        if self._running:
            self._pending = messages     # 合并：暂存
            return
        
        self._running = True
        try:
            await self._run(messages)
            while self._pending:         # trailing run
                msgs = self._pending
                self._pending = None
                await self._run(msgs)
        finally:
            self._running = False
```

### denial tracking

```python
LIMITS = {"max_consecutive": 3, "max_total": 20}

class DenialTracker:
    def __init__(self):
        self.consecutive = 0
        self.total = 0
    
    def record_denial(self):
        self.consecutive += 1
        self.total += 1
    
    def record_success(self):
        self.consecutive = 0
    
    def should_downgrade(self) -> bool:
        return (self.consecutive >= LIMITS["max_consecutive"] or
                self.total >= LIMITS["max_total"])
```

---

## 不要照抄的实现细节

- extractMemories 的闭包状态模式（`initExtractMemories` 返回函数）是 CC 的模块组织方式——你可以用类
- autoDream 的四重门控很多是 CC 特有的（KAIROS 模式、tengu feature flag）——你只需要时间门控 + 会话计数
- eval 注释（H1-H6）的具体分数是在 CC 的 eval 框架上跑的——你的项目需要自己建 eval 基准
- TRUSTING_RECALL_SECTION 的标题措辞实验（"Before recommending" 3/3 vs "Trusting what you recall" 0/3）是 prompt engineering 经验——标题用行动提示而非抽象描述

---

## 反模式

- 不要只记纠正——同时记确认，否则 Agent 越来越保守
- 不要把 eval 注释的结论写成"源码验证的不变式"——它们是设计决策的实验证据
- 不要把 prompt 指令（"回忆前验证"）写成代码级机制——它是注入到 system prompt 的文本
- 不要让后台提取和主 Agent 同时写记忆——CC 用 `hasMemoryWritesSince()` 做互斥
- 不要假设"6 个分布式机制"是源码中的命名构造——这是从多处代码推导出的设计模式描述
