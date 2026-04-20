---
name: speculative-execution
description: "指导如何设计 Agent 投机执行系统：用户未提交前在隔离层预执行，命中则秒出结果，未命中则静默丢弃"
user-invocable: false
argument-hint: "<目标项目路径或模块名>"
---

# Agent 投机执行 (Speculative Execution)

> 参考实现：Claude Code `src/services/PromptSuggestion/speculation.ts`（1000+ 行）
> — Copy-on-Write 文件隔离 + 边界停止 + 流水线链式预测

## 核心思想

**不要等用户提交再开始工作。** CC 在用户还在看建议的时候，就在隔离层把建议预执行了。用户按 Tab 接受 → 结果秒出（已经跑完了）。用户忽略 → 隔离层静默丢弃，零副作用。

---

## 一、端到端流程

```
模型响应完毕（无工具调用）
  ↓
Post-turn Hook: executePromptSuggestion()
  ├─ 抑制检查：权限弹窗中？计划模式？限流？
  ├─ 门控：至少 2 轮 assistant + 无 API 错误
  ├─ Fork Agent 生成 2-12 词建议文本
  ├─ 过滤：太短/太长/meta 推理泄漏/评价性语言/Claude 语气
  └─ 通过 → 显示给用户 + 立即启动 startSpeculation()
  ↓
startSpeculation()
  ├─ 创建隔离层：/tmp/.claude/speculation/{pid}/{id}/
  ├─ Fork Agent 开始在隔离层执行建议
  ├─ 工具调用通过 Copy-on-Write 重定向到隔离层
  ├─ 遇到边界操作（非只读 Bash/需要权限的 Edit）→ 停止
  └─ 同时在后台生成下一条建议（流水线）
  ↓
用户决策
  ├─ Tab 接受 → handleSpeculationAccept()
  │  ├─ 隔离层文件 → 复制到主目录
  │  ├─ 消息注入到主对话流（过滤掉失败的工具调用）
  │  ├─ 如果投机完整完成 → 跳过 API 调用（秒出结果）
  │  ├─ 如果投机到达边界 → 触发后续 API 调用继续执行
  │  └─ 提升流水线中的下一条建议
  │
  ├─ 用户输入其他内容 → abortSpeculation()
  │  └─ 清理隔离层，静默丢弃
  │
  └─ ESC → abortSpeculation()
```

---

## 二、Copy-on-Write 文件隔离

```typescript
// 隔离层路径
const overlayPath = join(getClaudeTempDir(), 'speculation', String(process.pid), id)

// 首次写入某文件时：从主目录复制到隔离层
if (!writtenPaths.has(relativePath)) {
  await copyFile(join(cwd, relativePath), join(overlayPath, relativePath))
  writtenPaths.add(relativePath)
}
// 后续写入：直接写隔离层（不再复制）
input.file_path = join(overlayPath, relativePath)  // 重定向

// 读取：如果之前写过 → 从隔离层读（看到修改后的版本）
//        否则 → 从主目录读（正常）
if (writtenPaths.has(relativePath)) {
  input.file_path = join(overlayPath, relativePath)  // 重定向
}
```

**关键**：隔离层只包含**被修改过的文件**，不是整个项目的副本。未修改的文件直接从主目录读取。

---

## 三、边界停止机制

投机不是无限制执行——遇到以下操作会自动停止：

| 边界类型 | 触发条件 | 停止后行为 |
|---------|---------|-----------|
| `bash` | 非只读 Bash 命令（写入/cd/安装等） | 记录被阻止的命令 |
| `edit` | 文件编辑不在 acceptEdits/bypass 模式下 | 记录文件路径 |
| `write_outside_root` | 写入 cwd 之外的路径 | 立即拒绝 |
| `denied_tool` | 工具不在白名单中 | 记录工具名 |
| `complete` | 模型正常结束（无更多工具调用） | 投机完整完成 |

**白名单内的安全工具**：
- 写工具：Edit、Write、NotebookEdit（通过 CoW 隔离）
- 只读工具：Read、Glob、Grep、ToolSearch、LSP
- 只读 Bash：`git status`、`cat`、`ls` 等

---

## 四、消息注入过滤

接受投机时，不是把所有消息原封不动注入——需要清理：

```typescript
prepareMessagesForInjection(speculationMessages) {
  保留：
    ✓ 有成功 tool_result 的 tool_use 块
    ✓ 有非空白内容的 text 块

  丢弃：
    ✗ thinking / redacted_thinking 块
    ✗ 没有 tool_result 的 tool_use（未完成）
    ✗ tool_result 是 error 的 tool_use（执行失败）
    ✗ 中断消息
    ✗ 过滤后变成全空白的消息
}
```

**如果投机未完整完成（到达边界）**：还要截掉尾部的 assistant 消息——因为 API 不接受以 assistant 结尾的对话，需要重新生成这一轮。

---

## 五、流水线链式预测

```
投机 A 执行中...
  ├─ 投机 A 完成（或到达边界）
  ├─ 立即在后台生成下一条建议 B（generatePipelinedSuggestion）
  │  └─ 基于"如果用户接受 A 后的上下文"生成
  └─ 建议 B 存为 pipelinedSuggestion

用户接受 A
  ├─ 投机 A 的结果注入主对话
  ├─ 如果 A 完整完成：
  │  ├─ 提升 pipelinedSuggestion → 活跃建议
  │  └─ 立即启动 startSpeculation(B)
  └─ 用户看到建议 B 时，B 的投机可能已经在跑了
```

**效果**：连续接受 3 条建议 → 每条都是"秒出"，因为下一条的投机在你接受上一条时就开始了。

---

## 六、限制与安全

```typescript
MAX_SPECULATION_TURNS = 20      // 最多 20 轮 API 调用
MAX_SPECULATION_MESSAGES = 100  // 最多 100 条消息
```

**建议文本过滤**（防止低质量投机浪费资源）：
- 长度：2-12 词，< 100 字符
- 拒绝 meta 推理泄漏：`"nothing found"`、`"[no suggestion]"`
- 拒绝评价性语言：`"thanks"`、`"looks good"`
- 拒绝 Claude 语气：`"let me"`、`"i'll"`、`"here's"`
- 拒绝多句话、含换行/星号

---

## 七、实现模板

```python
class SpeculativeExecutor:
    def __init__(self, agent_loop, overlay_dir: str):
        self.agent = agent_loop
        self.overlay_dir = overlay_dir
        self._active = None
        self._written_paths: set[str] = set()

    async def start(self, suggestion: str, context):
        """在隔离层预执行建议"""
        spec_id = uuid4().hex[:8]
        overlay = Path(self.overlay_dir) / spec_id
        overlay.mkdir(parents=True, exist_ok=True)
        self._written_paths = set()

        abort = asyncio.Event()
        self._active = {
            "id": spec_id, "overlay": overlay, "abort": abort,
            "messages": [], "boundary": None,
        }

        try:
            async for msg in self.agent.run_isolated(
                prompt=suggestion, context=context,
                tool_interceptor=self._intercept_tool,
                abort_signal=abort,
                max_turns=20,
            ):
                self._active["messages"].append(msg)
        except BoundaryReached as e:
            self._active["boundary"] = e.boundary

    def _intercept_tool(self, tool_name: str, input: dict) -> dict | None:
        """Copy-on-Write 拦截 + 边界检测"""
        if tool_name in ("Edit", "Write"):
            path = input.get("file_path", "")
            rel = os.path.relpath(path, os.getcwd())
            if rel.startswith("..") or os.path.isabs(rel):
                raise BoundaryReached({"type": "write_outside_root"})

            # CoW：首次写入时复制原文件到隔离层
            overlay_path = self._active["overlay"] / rel
            if rel not in self._written_paths:
                overlay_path.parent.mkdir(parents=True, exist_ok=True)
                if Path(path).exists():
                    shutil.copy2(path, overlay_path)
                self._written_paths.add(rel)
            return {**input, "file_path": str(overlay_path)}

        if tool_name == "Bash" and not is_read_only(input.get("command", "")):
            raise BoundaryReached({"type": "bash", "command": input["command"]})

        if tool_name == "Read" and input.get("file_path"):
            rel = os.path.relpath(input["file_path"], os.getcwd())
            if rel in self._written_paths:
                return {**input, "file_path": str(self._active["overlay"] / rel)}

        return input  # 不修改

    async def accept(self) -> bool:
        """接受投机结果，合并到主目录"""
        if not self._active: return False

        # 复制隔离层文件到主目录
        for rel in self._written_paths:
            src = self._active["overlay"] / rel
            dst = Path(os.getcwd()) / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

        # 清理隔离层
        shutil.rmtree(self._active["overlay"], ignore_errors=True)

        is_complete = self._active["boundary"] is None or \
                      self._active["boundary"]["type"] == "complete"
        self._active = None
        return is_complete  # True = 无需后续 API 调用

    def abort(self):
        """丢弃投机结果"""
        if self._active:
            self._active["abort"].set()
            shutil.rmtree(self._active["overlay"], ignore_errors=True)
            self._active = None
```

---

## 八、实施步骤

请分析用户的 $ARGUMENTS 中指定的项目，然后：

1. **识别可预测的用户意图**：哪些场景下 Agent 能猜到用户下一步要做什么
2. **实现文件隔离层**：Copy-on-Write overlay，只复制被修改的文件
3. **定义边界操作**：哪些操作太危险不能投机（写入外部路径、非只读 shell 等）
4. **实现消息过滤**：接受时清理未完成/失败的工具调用
5. **评估流水线**：如果用户接受频率高，加链式预测
6. **加限制**：最大轮次 + 最大消息数 + 建议质量过滤

**反模式警告**：
- 不要在没有隔离的情况下投机 — 必须 CoW
- 不要投机需要权限的操作 — 到达边界就停
- 不要把失败的工具调用注入主对话 — 先过滤
- 不要无限制投机 — 20 轮 / 100 消息是合理上限
