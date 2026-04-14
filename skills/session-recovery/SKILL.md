---
name: session-recovery
description: "会话恢复：JSONL 追加写入 + parentUuid 链表重建 + 三个具名过滤函数 + 成本状态 sessionId 键恢复 + 文件历史快照"
user-invocable: true
argument-hint: "<目标项目路径或模块名>"
---

# 会话恢复

> 参考实现：`src/utils/sessionStorage.ts`（转录持久化）、`src/utils/conversationRecovery.ts`（恢复管道）、`src/utils/messages.ts`（三个过滤函数）、`src/cost-tracker.ts`（成本恢复）、`src/utils/fileHistory.ts`（文件快照）

## 源码事实

### 1. JSONL 是唯一的转录格式——这是 CC 的实现选择

```
存储：~/.claude/{projectId}/{sessionId}.jsonl
写入：append-only（每条消息一行 JSON）
读取：全量解析或 head/tail 快速读取元数据
```

**为什么 CC 选择 JSONL**：append-only 意味着崩溃最多丢最后一行。但这是 CC 的实现选择，不是会话恢复的唯一方案——你的项目可以用 SQLite WAL 模式达到同样的崩溃安全性。

### 2. parentUuid 是链表，不是 DAG

每条消息有 `uuid` 和 `parentUuid`（0 或 1 个父）。这构成的是**严格的链表**，不是 DAG：

```
msg[0] ← msg[1] ← msg[2] ← msg[3] ← ... ← msg[N]（叶节点）
  ^parentUuid    ^parentUuid    ^parentUuid
```

**压缩边界**打断链：
```
[...旧消息...] ← [COMPACT BOUNDARY]  ← msg[4] ← msg[5]
                   parentUuid = null     正常链接
                   logicalParentUuid = msg[3].uuid  （逻辑引用）
```

**恢复算法**：从叶节点沿 parentUuid 走到 null（链根），反转得到 root→leaf 顺序。

### 3. 三个过滤函数是真实的具名导出

全部在 `src/utils/messages.ts`，由 `conversationRecovery.ts:187-200` 按顺序调用：

**filterUnresolvedToolUses**（line 2795-2841）：
```
两遍扫描：
  Pass 1: 收集所有 tool_use ID 和 tool_result ID
  Pass 2: 移除 assistant 消息——仅当其 ALL tool_use 块都没有配对的 tool_result

场景：Agent 调用 Bash 但进程在工具执行中被杀
  → 有 tool_use(id=tu1) 但没有 tool_result(tool_use_id=tu1)
  → 移除包含 tu1 的 assistant 消息
```

**filterOrphanedThinkingOnlyMessages**（line 4991-5058）：
```
两遍扫描：
  Pass 1: 找到有非 thinking 内容的 message.id 集合
  Pass 2: 移除 thinking-only 的 assistant——仅当同 message.id 没有兄弟有实际内容

场景：流式传输中 thinking 块和 text 块分成两条消息，text 消息丢失
  → thinking-only 消息会导致 API 400
  → 如果有同 id 兄弟有内容 → 保留（后续 normalizeMessages 会合并）
  → 没有兄弟 → 移除
```

**filterWhitespaceOnlyAssistantMessages**（line 4869-4919）：
```
移除只含空白的 assistant 消息
  → 移除后可能出现连续两条 user 消息
  → API 要求角色交替 → mergeAdjacentUsers() 合并相邻 user
```

### 4. 成本恢复用 sessionId 做缓存键

```typescript
// src/cost-tracker.ts:87-123
function getStoredSessionCosts(sessionId: string) {
  const config = getCurrentProjectConfig()
  if (config.lastSessionId !== sessionId) {
    return undefined  // 不同会话 → 不恢复（防串台）
  }
  return {
    totalCostUSD: config.lastCost ?? 0,
    totalAPIDuration: config.lastAPIDuration,
    lastModelUsage: config.lastModelUsage,  // 每模型用量
    // ...12 个追踪指标
  }
}
```

存储位置：`~/.claude/{projectId}/project.json`（不是 JSONL）

### 5. 文件历史快照是核心功能，不是可选

```
每次 recordTranscript() 后触发 fileHistoryMakeSnapshot()：
  → 检查每个追踪文件的 mtime
  → 有变化 → copyFile 到 ~/.claude/file-history/{sessionId}/{hash}@v{version}
  → 无变化 → 复用上一版引用

恢复时（--continue）：
  → copyFileHistoryForResume()
  → 从旧 sessionId 复制快照到新 sessionId
  → 优先 hard link（快，CoW），fallback copyFile
```

### 6. 流式传输孤儿恢复

流式 API 为每个 content block 发一条消息（相同 message.id）：

```
[tool_use(tu1)] → msg[a] { id="m-123" }
[tool_use(tu2)] → msg[b] { id="m-123" }
[tool_result(tu1)] → msg[c] { parentUuid=msg[a].uuid }
[tool_result(tu2)] → msg[d] { parentUuid=msg[b].uuid }
```

单链遍历只走 msg[a]→msg[c]，丢掉 msg[b] 和 msg[d]。

`recoverOrphanedParallelToolResults()`：按 message.id 分组 → 找链上锚点的链外兄弟 → 在锚点后插入兄弟 + 对应 tool_result。

---

## 可迁移设计

### 会话持久化的核心需求（不绑定 JSONL）

你的项目需要保证：

```python
# 1. 崩溃安全：最多丢最后一条操作
# 2. 因果可追溯：每条消息知道它的前一条是什么
# 3. 恢复时清理中断残留：未配对的工具调用、空白消息
# 4. 成本可恢复：不因重启丢失累计成本
# 5. 文件可回滚：知道哪些文件被修改了、修改前是什么样

# 实现可以是 JSONL，也可以是 SQLite WAL，也可以是其他 append-only 格式
```

### 中断清理的三步模式

```python
def clean_interrupted_session(messages):
    """恢复时的三步清理——顺序重要"""
    # Step 1: 移除未配对的工具调用
    messages = remove_unpaired_tool_calls(messages)
    # Step 2: 移除孤儿 thinking 块
    messages = remove_orphan_thinking(messages)
    # Step 3: 移除空白 assistant + 合并相邻 user
    messages = remove_whitespace_assistant(messages)
    messages = merge_adjacent_users(messages)
    return messages
```

### 成本恢复用会话 ID 做键

```python
def restore_costs(session_id: str) -> bool:
    stored = load_project_config()
    if stored.get("last_session_id") != session_id:
        return False  # 不同会话，不恢复
    set_cost_state(stored)
    return True
```

---

## 不要照抄的实现细节

- JSONL 是 CC 的选择，不是唯一方案——SQLite WAL 模式同样是 append-only 且崩溃安全
- parentUuid 链表重建（从叶到根遍历）是 CC 特定的——你可以用自增 ID + 序号
- `recoverOrphanedParallelToolResults` 是因为 CC 的流式 API 为每个 content block 发独立消息——如果你的 API 返回完整消息则不需要
- 文件历史的 hash 命名（`{sha256_prefix}@v{version}`）是 CC 的去重策略——你可以用时间戳+文件名

---

## 反模式

- 不要跳过中断清理就恢复——未配对的 tool_use 会导致 API 400
- 不要恢复不同会话的成本——sessionId 不匹配就重新计数
- 不要忘了清理后合并相邻 user——删除空白 assistant 可能破坏角色交替
- 不要把恢复逻辑写成"一个完整的恢复系统"——CC 的实现是 sessionStorage + conversationRecovery + cost-tracker + fileHistory 四个独立模块在恢复时机被依次调用
