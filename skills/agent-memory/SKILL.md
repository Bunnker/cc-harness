---
name: agent-memory
description: "指导如何设计 Agent 跨会话记忆系统：4 类型分类 + 双路径保存 + 后台提取 + 过期检测 + 索引管理"
user-invocable: false
argument-hint: "<目标项目路径或模块名>"
---

# Agent 记忆系统 (Agent Memory System)

> 参考实现：Claude Code `src/memdir/`（700+ 行）— 文件级记忆 + MEMORY.md 索引 + 后台 Fork 提取 + 过期验证

## 核心思想

**记忆不是"保存所有对话"，是"提取跨会话有价值的洞察，用文件系统组织，按过期时间验证"。** CC 的记忆系统像人脑——不记录每次对话，而是提取模式、偏好、决策，并在回忆时验证是否过期。

---

## 一、4 种记忆类型

| 类型 | 存什么 | 作用域 | 示例 |
|------|-------|--------|------|
| **user** | 用户角色、偏好、专业领域 | 永远私有 | "用户是高级后端工程师，偏好简洁代码" |
| **feedback** | 用户的纠正和确认 | 默认私有 | "不要在测试中 mock 数据库（上次因此出 bug）" |
| **project** | 进行中的工作、决策、截止日期 | 偏向团队共享 | "auth 重写是因为合规要求，非技术债" |
| **reference** | 外部系统指针 | 通常团队共享 | "pipeline bug 在 Linear 的 INGEST 项目追踪" |

### 不该存的（CC 明确排除）

- 代码模式/架构/文件路径 → 从代码直接读
- Git 历史/blame → `git log` 是权威来源
- Debug 方案 → fix 在代码里，context 在 commit message 里
- CLAUDE.md 已有的内容 → 不重复
- 临时任务状态 → 用任务系统，不用记忆

---

## 二、存储结构

```
~/.claude/projects/<sanitized-project>/memory/
├── MEMORY.md              # 索引文件（≤200 行，≤25KB）
├── user_role.md            # 独立记忆文件
├── feedback_testing.md
├── project_auth_rewrite.md
├── reference_linear.md
└── team/                   # 团队共享记忆（可选）
    ├── MEMORY.md
    └── project_team_conventions.md
```

### 记忆文件格式

```yaml
---
name: testing-approach
description: "集成测试必须用真实数据库，不要 mock"
type: feedback
---

集成测试必须用真实数据库，不要 mock。

**Why:** 上季度 mock 测试全通过，但 prod 迁移失败。mock/prod 行为差异导致。
**How to apply:** 写测试时默认用 testcontainers 或内存数据库，只在单元测试中 mock 外部服务。
```

### MEMORY.md 索引格式

```markdown
- [Testing approach](feedback_testing.md) — 集成测试用真实 DB，不 mock
- [Auth rewrite context](project_auth_rewrite.md) — 合规驱动，非技术债
- [User role](user_role.md) — 高级后端工程师，偏好简洁
```

**约束**：每条 ≤150 字符，总共 ≤200 行。索引只是指针，不包含记忆内容本身。

---

## 三、双路径保存机制

### 路径 A：主 Agent 显式保存

模型在对话中检测到值得记住的信息 → 直接调用 Write/Edit 写入记忆目录。

```
用户："不要在这些测试里 mock 数据库"
  ↓
Agent 检测到 feedback 类型信息
  ↓
1. Write("~/.claude/.../memory/feedback_testing.md", content)
2. Edit("~/.claude/.../memory/MEMORY.md", 追加索引行)
```

### 路径 B：后台 Fork 提取（用户无感）

对话结束后，系统自动 fork 一个轻量 Agent 分析对话，提取记忆：

```
query() / stopHooks 结束
  ↓
executeExtractMemories()
  ├─ 检查门控：feature flag + 非远程模式 + auto memory 开启
  ├─ 互斥检查：主 Agent 是否已经写了记忆？→ 跳过
  ├─ 节流控制：每 N 轮才提取一次（可配）
  ├─ runForkedAgent() — 继承 prompt cache，独立 token 预算
  │  ├─ 预注入已有记忆清单（省去 ls 的工具调用）
  │  ├─ 最多 5 轮（硬上限，防止验证兔子洞）
  │  ├─ 工具受限：只读 Bash + 只能写 memory 目录
  │  └─ 高效策略：Phase 1 并行读，Phase 2 并行写
  └─ 如果提取到新记忆 → 追加系统消息通知用户
```

**互斥设计**：如果主 Agent 已经显式写了记忆（`hasMemoryWritesSince()` 检查），后台提取跳过，避免重复。

**合并处理**：如果提取还在进行中又触发了新的提取 → 新的上下文被暂存，等当前提取完成后再跑一轮。

---

## 四、过期检测与验证

```typescript
// src/memdir/memoryAge.ts
memoryAgeDays(mtimeMs: number): number    // 0=今天, 1=昨天, ...
memoryFreshnessNote(mtimeMs: number): string
// > 1 天的记忆会附加警告：
// "此记忆写于 X 天前。验证后再使用。"
```

### 回忆前验证规则（注入到 system prompt）

1. **记忆提到文件路径** → 先检查文件是否存在
2. **记忆提到函数/flag** → 先 grep 确认还在
3. **记忆与当前代码冲突** → 信任当前代码，更新或删除过期记忆
4. **记忆是活动摘要** → 用 `git log` 获取最新状态

**原则**："记忆说 X 存在" ≠ "X 现在存在"。

---

## 五、路径安全验证 — 核心是信任边界，不是复杂 traversal 花活

CC 这里最重要的安全点其实是两层：

1. **只信任特定来源的 `autoMemoryDirectory`**
2. **对最终路径做基础根路径验证**

`src/memdir/paths.ts` 的真实边界是：

```typescript
function getAutoMemPathSetting() {
  return (
    policySettings.autoMemoryDirectory ??
    flagSettings.autoMemoryDirectory ??
    localSettings.autoMemoryDirectory ??
    userSettings.autoMemoryDirectory
    // projectSettings 被明确排除
  )
}

function validateMemoryPath(path) {
  requireAbsolutePath()
  rejectNearRoot()
  rejectDriveRoot()
  rejectUNCPath()
  rejectNullByte()
  optionallyExpandSafeTilde()
  normalizeToNFC()
}
```

**真正关键的地方**：`projectSettings`（仓库里的 `.claude/settings.json`）被明确排除。否则恶意仓库可以把 `autoMemoryDirectory` 指到 `~/.ssh` 之类的敏感目录。

**你的项目应该**：可写目录的安全重点先放在“谁有权声明这条路径”，再做最小但可靠的绝对路径/近根/null-byte 校验。

---

## 六、文件状态缓存 — 长会话的 I/O 优化

```typescript
// src/utils/fileStateCache.ts
type FileStateCache = {
  content: string      // 文件内容
  timestamp: number    // mtime（上次读取时）
  isPartialView?: boolean  // 是否被自动注入修改过
}

// 配置
MAX_ENTRIES = 100     // LRU，最多 100 个文件
MAX_TOTAL_SIZE = 25MB // 总大小限制
```

**作用**：
- 长会话中模型反复读同一个文件 → 缓存命中，不重新读磁盘
- 追踪文件是否被修改（`getChangedFiles()` 对比 mtime）
- 检测自动注入的内容是否与磁盘不同（`contentDiffersFromDisk`）

**设计原则**：缓存按 LRU 淘汰，优先保留最近操作的文件。

---

## 七、团队记忆 — 共享 + 安全

```
~/.claude/projects/<project>/memory/team/
├── MEMORY.md                    ← 共享索引
└── project_team_conventions.md  ← 团队约定
```

**作用域规则**：
| 记忆类型 | 默认作用域 |
|---------|-----------|
| user | 永远私有 |
| feedback | 默认私有，项目级约定放团队 |
| project | 偏向团队共享 |
| reference | 通常团队共享 |

**安全边界**：团队目录的路径验证更严格——防止 `team-evil/` 前缀攻击（`team` 的子目录不能逃逸到 `team-evil`）。用 `realpath()` 解析最深存在祖先目录，验证前缀匹配。

---

## 八、记忆加载到上下文

### 三个注入点

```
1. System Prompt → loadMemoryPrompt()
   ├─ typed-memory 使用指南（什么该存、怎么存、怎么用）
   ├─ 默认情况下：把 MEMORY.md 作为索引入口
   └─ `tengu_moth_copse` 开启时：保留规则，但跳过 auto/team MEMORY.md 索引

2. CLAUDE.md 系列 → getMemoryFiles()
   ├─ 按优先级加载：策略级 > 用户级 > 项目级 > 本地级
   └─ “当前实际被注入了什么” 还会再经过 filterInjectedMemoryFiles() 过滤

3. 相关记忆预取 → startRelevantMemoryPrefetch() / findRelevantMemories()
   ├─ 异步 side query：用 Sonnet 从 header 里选最相关的 ≤5 个记忆文件
   ├─ 明确排除 MEMORY.md
   ├─ 过滤已展示过的记忆 + readFileState 里已读过的记忆
   ├─ 每文件 ≤200 行、≤4KB；会话累计 ≤60KB
   └─ 作为 `<system-reminder>` attachment 注入（不走 MEMORY.md 索引）
```

**设计含义**：

- `MEMORY.md` 更像长期索引
- `relevant_memories` attachment 更像当前 turn 的按需回忆
- compact 后旧 attachment 消失，相关记忆 surfacing 预算也会自然重置

---

## 六、实现模板

### 最小版本（Python）

```python
import json
from pathlib import Path
from datetime import datetime, timedelta

class MemorySystem:
    def __init__(self, memory_dir: str):
        self.dir = Path(memory_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.dir / "MEMORY.md"

    # ─── 保存 ───
    def save(self, name: str, type: str, description: str, content: str):
        """两步保存：写文件 + 更新索引"""
        filename = f"{type}_{name}.md"
        filepath = self.dir / filename

        # Step 1: 写记忆文件
        frontmatter = f"---\nname: {name}\ndescription: {description}\ntype: {type}\n---\n\n"
        filepath.write_text(frontmatter + content, encoding='utf-8')

        # Step 2: 更新索引（去重）
        index = self.index_path.read_text(encoding='utf-8') if self.index_path.exists() else ""
        entry = f"- [{name}]({filename}) — {description}"
        if filename not in index:
            index += f"\n{entry}"
            self.index_path.write_text(index.strip() + "\n", encoding='utf-8')

    # ─── 加载 ───
    def load_index(self) -> str:
        """返回索引内容（注入到 system prompt）"""
        if not self.index_path.exists():
            return ""
        content = self.index_path.read_text(encoding='utf-8')
        lines = content.strip().split('\n')
        if len(lines) > 200:  # 硬限制
            lines = lines[:200]
            lines.append(f"> WARNING: MEMORY.md truncated at 200 lines")
        return '\n'.join(lines)

    # ─── 过期检测 ───
    def get_with_freshness(self, filename: str) -> tuple[str, str]:
        """返回 (内容, 过期警告)"""
        filepath = self.dir / filename
        content = filepath.read_text(encoding='utf-8')
        mtime = datetime.fromtimestamp(filepath.stat().st_mtime)
        age = (datetime.now() - mtime).days

        warning = ""
        if age > 0:
            warning = f"此记忆写于 {age} 天前。使用前请验证其准确性。"
        return content, warning

    # ─── 查找相关记忆 ───
    def find_relevant(self, query: str, max_results: int = 5) -> list[dict]:
        """扫描所有记忆文件的 frontmatter，返回最相关的"""
        results = []
        for f in self.dir.glob("*.md"):
            if f.name == "MEMORY.md":
                continue
            text = f.read_text(encoding='utf-8')
            # 简单实现：关键词匹配。进阶：用 embedding 或 LLM 选择
            if any(kw in text.lower() for kw in query.lower().split()):
                content, warning = self.get_with_freshness(f.name)
                results.append({"file": f.name, "content": content, "warning": warning})
        return results[:max_results]
```

### 进阶：后台提取 Agent

```python
class BackgroundMemoryExtractor:
    """对话结束后自动提取记忆"""

    def __init__(self, memory: MemorySystem, model):
        self.memory = memory
        self.model = model
        self._running = False

    async def maybe_extract(self, messages: list, main_agent_wrote: bool):
        """互斥 + 节流"""
        if self._running:
            return  # 合并：等当前完成
        if main_agent_wrote:
            return  # 主 Agent 已写，跳过

        self._running = True
        try:
            # 预注入已有记忆清单
            existing = self.memory.load_index()
            prompt = f"""分析以下对话，提取值得跨会话记忆的信息。
已有记忆：
{existing}

规则：
- 只提取 user/feedback/project/reference 四种类型
- 不要重复已有记忆
- 每条记忆包含 Why 和 How to apply
- 不要保存代码模式、git 历史、临时任务状态"""

            response = await self.model.call(prompt + format_messages(messages))
            new_memories = parse_memories(response)

            for mem in new_memories:
                self.memory.save(mem.name, mem.type, mem.description, mem.content)
        finally:
            self._running = False
```

---

## 七、实施步骤

请分析用户的 $ARGUMENTS 中指定的项目，然后：

1. **确定记忆存储位置**：项目级 vs 用户级 vs 两者都有
2. **定义记忆类型**：至少 user + feedback 两种，按需加 project + reference
3. **实现两步保存**：写文件 + 更新索引（保证可发现性）
4. **实现过期检测**：基于文件 mtime，回忆时附加过期警告
5. **实现回忆前验证规则**：文件路径/函数名/flag 在使用前 grep 确认
6. **评估后台提取**：如果对话频繁，加 Fork Agent 自动提取
7. **设置索引限制**：MEMORY.md ≤200 行，每条 ≤150 字符

**反模式警告**：
- 不要把对话全文存为记忆 — 提取洞察，不是存日志
- 不要忘了去重 — 保存前检查是否已有相同记忆
- 不要信任过期记忆 — 回忆时必须验证
- 不要让后台提取和主 Agent 同时写 — 互斥机制
- 不要存代码模式 — 代码本身就是最好的文档
