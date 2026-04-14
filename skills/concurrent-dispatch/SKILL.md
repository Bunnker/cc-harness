---
name: concurrent-dispatch
description: "指导如何设计并发分区调度：只读操作并行、破坏性操作串行、Bash 错误级联取消的安全执行策略"
user-invocable: true
argument-hint: "<目标项目路径或模块名>"
---

# 并发分区调度模式 (Concurrent Partition Dispatch)

> 参考实现：Claude Code `src/services/tools/toolOrchestration.ts` + `StreamingToolExecutor.ts`
> — 双模式调度（静态分区 / 流式动态），按工具特性自动决定并行 or 串行

## 核心思想

**不是"全并行"或"全串行"的二选一，是按操作特性自动分区 + 错误选择性级联。**
读文件和搜索代码可以同时跑 5 个，但文件写入必须一个一个来；Bash 命令失败要取消兄弟 Bash，但 Read 失败不影响其他 Read。

---

## 一、CC 的双模式调度架构

CC 有两套调度器，由 feature flag 切换：

| 模式 | 触发时机 | 核心特点 |
|------|---------|---------|
| **StreamingToolExecutor**（现代） | API 响应流式到达时 | 工具边到边执行，不等 API 结束 |
| **runTools**（传统） | API 响应全部到达后 | 批量分区，按批顺序执行 |

两者共享同一套分区逻辑，但执行时机不同。

### 静态分区算法（runTools）

```typescript
// src/services/tools/toolOrchestration.ts
function partitionToolCalls(toolUseMessages): Batch[] {
  return toolUseMessages.reduce((acc, toolUse) => {
    const tool = findToolByName(tools, toolUse.name)
    const isSafe = tool?.isConcurrencySafe(input)

    if (isSafe && acc[acc.length - 1]?.isConcurrencySafe) {
      // 连续的安全工具 → 合并到同一批
      acc[acc.length - 1].blocks.push(toolUse)
    } else {
      // 不安全工具 → 独占一批
      acc.push({ isConcurrencySafe: isSafe, blocks: [toolUse] })
    }
    return acc
  }, [])
}
```

**效果**：
```
输入: [Read, Grep, Edit, Read, Glob, Write]
分批: [[Read, Grep], [Edit], [Read, Glob], [Write]]
       并行(2)     串行(1)   并行(2)      串行(1)
```

### 动态调度决策（StreamingToolExecutor）

```typescript
// 每个新工具到达时判断
canExecuteTool(isConcurrencySafe: boolean): boolean {
  const executing = this.tools.filter(t => t.status === 'executing')

  return executing.length === 0 ||  // 没有正在跑的 → 直接跑
    (isConcurrencySafe && executing.every(t => t.isConcurrencySafe))
    // 新工具安全 AND 所有正在跑的也安全 → 并行跑
}
```

**关键差异**：静态分区需要所有工具到齐才能分批；动态调度边到边执行，延迟更低。

---

## 二、并发度限制

```typescript
// src/services/tools/toolOrchestration.ts
function getMaxToolUseConcurrency(): number {
  return parseInt(process.env.CLAUDE_CODE_MAX_TOOL_USE_CONCURRENCY || '', 10) || 10
}
```

默认最多 10 个工具同时执行。通过 `all()` 生成器实现：

```typescript
// src/utils/generators.ts — 通用并发原语
async function* all<T>(generators: AsyncGenerator<T>[], cap = Infinity) {
  const waiting = [...generators]
  const active = new Set<Promise<...>>()

  // 填满初始批
  while (active.size < cap && waiting.length > 0)
    active.add(next(waiting.shift()!))

  // 竞速：谁先完成就消费谁，立刻补充新的
  while (active.size > 0) {
    const { done, value, generator, promise } = await Promise.race(active)
    active.delete(promise)
    if (!done) {
      active.add(next(generator))     // 继续消费该生成器
      if (value !== undefined) yield value
    } else if (waiting.length > 0) {
      active.add(next(waiting.shift()!))  // 补充新生成器
    }
  }
}
```

**为什么用 `Promise.race` 而不是 `Promise.all`**：
- `Promise.all` 要等所有完成才返回 → 慢的拖慢快的
- `Promise.race` + 循环 → 谁先完成谁先返回给调用者，流式输出

---

## 三、错误隔离 — 选择性级联取消

CC 的错误处理不是简单的"一个失败全部失败"，而是 **按工具类型选择性级联**：

### 只有 Bash 错误会取消兄弟任务

```typescript
// StreamingToolExecutor.ts
if (isErrorResult) {
  thisToolErrored = true

  // 关键设计：只有 Bash 错误级联
  if (tool.block.name === 'Bash') {
    this.hasErrored = true
    this.siblingAbortController.abort('sibling_error')  // 取消所有兄弟
  }
  // Read/Grep/WebFetch 错误 → 不影响其他工具
}
```

**为什么只有 Bash**：Bash 命令之间常有隐式依赖链（`mkdir` 失败 → 后续 `cd` 必然失败）。但 `Read(a.ts)` 失败和 `Read(b.ts)` 完全无关。

### AbortController 三级层次

```
toolUseContext.abortController    ← 查询级（用户取消整个查询）
  └─ siblingAbortController      ← 批次级（Bash 错误级联）
      └─ toolAbortController     ← 工具级（单个工具超时/取消）
```

### 被取消的工具收到合成错误

```typescript
// 排队中还没开始的工具
"Cancelled: parallel tool call {description} errored"

// 正在执行的工具（如果还没有自己的错误）
"Cancelled: parallel tool call {description} errored"
```

---

## 四、Progress 流式输出 — 绕过结果队列

工具执行中的进度消息（如 Bash 的 stdout 流）不等工具完成就立即输出：

```typescript
if (update.message.type === 'progress') {
  tool.pendingProgress.push(update.message)
  // 立即通知外层有新进度可消费
  if (this.progressAvailableResolve) {
    this.progressAvailableResolve()
    this.progressAvailableResolve = undefined
  }
} else {
  messages.push(update.message)  // 正常结果等工具完成
}
```

**效果**：慢工具（如 `npm install`）的 stdout 实时显示在 UI 上，不用等它跑完。

---

## 五、上下文修改器 — 并发工具不能改全局状态

```typescript
// 注意：并发工具的上下文修改被缓冲，批次完成后才应用
if (!tool.isConcurrencySafe && contextModifiers.length > 0) {
  for (const modifier of contextModifiers) {
    this.toolUseContext = modifier(this.toolUseContext)  // 串行工具可以立即改
  }
}
// 并发工具的 contextModifier → 排队等批次结束
```

**为什么**：如果两个并发的 Bash 同时 `cd` 到不同目录，结果不确定。所以 CC 限制只有串行工具才能修改全局上下文。

---

## 六、中断行为 — interruptBehavior

用户在工具执行中按 ESC 时：

```typescript
type InterruptBehavior = 'cancel' | 'block'
// cancel: 停止工具，丢弃结果
// block:  工具继续跑，新输入排队等待（默认）
```

CC 所有工具目前都默认 `block`（不中断）。只有当**所有**正在执行的工具都是 `cancel` 时，UI 才显示"可中断"提示。

---

## 七、实现模板

### 最小版本（适合大多数项目）

```typescript
interface Task<T> {
  id: string
  execute(signal: AbortSignal): Promise<T>
  isConcurrencySafe(): boolean
}

async function dispatch<T>(tasks: Task<T>[], maxConcurrency = 10): Promise<Map<string, T>> {
  const results = new Map<string, T>()
  const batches = partition(tasks)

  for (const batch of batches) {
    if (batch.parallel) {
      // 并行执行，用 Promise.allSettled 隔离失败
      const settled = await Promise.allSettled(
        batch.tasks.map(t => t.execute(new AbortController().signal))
      )
      for (let i = 0; i < settled.length; i++) {
        if (settled[i].status === 'fulfilled')
          results.set(batch.tasks[i].id, settled[i].value)
      }
    } else {
      // 串行执行
      for (const task of batch.tasks) {
        results.set(task.id, await task.execute(new AbortController().signal))
      }
    }
  }
  return results
}

function partition<T>(tasks: Task<T>[]): Batch<T>[] {
  const batches: Batch<T>[] = []
  let currentParallel: Task<T>[] = []

  for (const task of tasks) {
    if (task.isConcurrencySafe()) {
      currentParallel.push(task)
    } else {
      if (currentParallel.length > 0) {
        batches.push({ parallel: true, tasks: currentParallel })
        currentParallel = []
      }
      batches.push({ parallel: false, tasks: [task] })
    }
  }
  if (currentParallel.length > 0)
    batches.push({ parallel: true, tasks: currentParallel })

  return batches
}
```

### 进阶：加入选择性错误级联

```typescript
// 只有特定类型的任务错误才取消兄弟
const CASCADE_ERROR_TYPES = new Set(['shell', 'process'])

if (taskErrored && CASCADE_ERROR_TYPES.has(task.type)) {
  siblingAbortController.abort('sibling_error')
}
```

---

## 八、实施步骤

请分析用户的 $ARGUMENTS 中指定的项目，然后：

1. **识别可并行的操作**：查询、读取、搜索 → `isConcurrencySafe() { return true }`
2. **识别必须串行的操作**：写入、删除、状态变更 → `isConcurrencySafe() { return false }`
3. **识别有依赖链的操作**：如 shell 命令 → 错误时级联取消兄弟
4. **实现分区逻辑**：连续安全操作合并一批，不安全操作独占一批
5. **选 `Promise.allSettled`，不选 `Promise.all`**：隔离独立任务的失败
6. **加并发度上限**：根据资源类型设置（文件 I/O ~10，网络 ~5，CPU ~核心数）
7. **串行任务才能改全局状态**：并发任务的状态修改缓冲到批次结束

**反模式警告**：
- 不要用 `Promise.all` — 一个失败拖垮全部
- 不要一刀切"Bash 全串行" — `ls` 可以并发，`rm` 才需要串行（用方法不用属性）
- 不要所有错误都级联 — 只有有依赖关系的操作类型才需要
- 不要并发任务修改全局状态 — 缓冲到批次结束再应用
