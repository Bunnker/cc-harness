---
name: instruction-file-system
description: "指导如何设计 Harness 指令文件系统：4 层优先级 + 向上遍历 + 条件规则 + @include + worktree 去重"
user-invocable: true
argument-hint: "<目标项目路径或模块名>"
---

# Harness 指令文件系统 (Instruction File System)

> 参考实现：Claude Code `src/utils/claudemd.ts`（1460+ 行）
> — 4 层指令优先级 + 向上目录遍历 + .claude/rules/ 条件规则 + @include 递归 + worktree 去重

## 核心思想

**Agent 的行为指令不该硬编码——应该从文件系统层级化加载。** CC 用 4 层优先级（Managed > User > Project > Local）、向上目录遍历、条件 glob 匹配，让指令可以按组织/用户/项目/个人粒度配置，同时防止恶意仓库通过指令文件注入危险行为。

---

## 一、4 层指令优先级（后加载 = 更高优先级）

```
加载顺序（低 → 高）：
  1. Managed  /etc/claude-code/CLAUDE.md + .claude/rules/*.md
             （组织策略，最高权威，不可覆盖）

  2. User     ~/.claude/CLAUDE.md + rules/*.md
             （用户全局规则，跨项目生效）

  3. Project  CLAUDE.md + .claude/CLAUDE.md + .claude/rules/*.md
             （项目共享规则，在 git 中）
             — 从 cwd 向上遍历到根目录，每层都扫描
             — 越靠近 cwd 的越后加载（优先级越高）

  4. Local    CLAUDE.local.md
             （个人私有规则，gitignored）
```

### 平台特定的 Managed 路径

```typescript
// src/utils/settings/managedPath.ts
macOS:   '/Library/Application Support/ClaudeCode'
Windows: 'C:\\Program Files\\ClaudeCode'
Linux:   '/etc/claude-code'
```

**关键安全设计**：Managed 层始终加载，不受 `--setting-sources` 限制。组织管理员可以在这里放强制性规则（如"不得修改 prod 数据库"），用户无法绕过。

---

## 二、向上目录遍历算法

```
当前目录: /home/user/projects/myapp/src/components
                                          ↓
遍历路径: /home/user/projects/myapp/src/components
          /home/user/projects/myapp/src
          /home/user/projects/myapp       ← 可能是 git root
          /home/user/projects
          /home/user
          /home
          /                               ← 文件系统根

每层扫描：
  ├─ CLAUDE.md
  ├─ .claude/CLAUDE.md
  ├─ .claude/rules/*.md（递归子目录）
  └─ CLAUDE.local.md

处理顺序：从根向 cwd 方向处理（根先加载，cwd 最后加载）
→ cwd 附近的文件有最高优先级
```

```python
# 伪代码
dirs = []
current = cwd
while current != root:
    dirs.append(current)
    current = parent(current)

for dir in reversed(dirs):  # 从根向 cwd
    load_project_files(dir)
    load_local_files(dir)
```

---

## 三、Git Worktree 去重

```
场景：
  主仓库: /home/user/repo/
  Worktree: /home/user/repo/.claude/worktrees/feature-x/

问题：向上遍历会经过主仓库的 .claude/rules/
      → 同一规则被加载两次（worktree 里一次 + 主仓库一次）

解法：
  如果 gitRoot ≠ canonicalRoot 且 gitRoot 在 canonicalRoot 内部
    → 当前在嵌套 worktree 中
    → 跳过 canonicalRoot 内但 gitRoot 外的 Project 文件
    → 只加载 worktree 自己的 Project 文件
    → Local 文件不跳过（不在 git 中，不会重复）
```

---

## 四、.claude/rules/ — 条件规则

rules 目录下的 `.md` 文件可以带 YAML frontmatter 指定生效条件：

```markdown
---
paths: |
  src/**/*.py
  tests/**/*.py
---

所有 Python 文件必须使用 type hints。
函数返回值必须有类型注解。
```

### 两阶段加载

```
会话启动：
  ├─ 无 frontmatter 的规则 → 立即加载（无条件生效）
  └─ 有 paths: 的规则 → 暂存为条件规则

运行时触发：
  Agent 编辑 src/utils/helper.py
    → 检查条件规则的 glob 匹配
    → "src/**/*.py" 匹配 → 激活该规则
    → 注入到下一轮 context
```

**Glob 匹配基准目录**：
- Project 规则：相对于包含 `.claude` 目录的那个目录
- Managed/User 规则：相对于 originalCwd

---

## 五、@include 递归指令

```markdown
# CLAUDE.md
请遵循以下规范：
@./coding-standards.md
@~/.claude/shared-rules.md
@/absolute/path/security-rules.md
```

### 解析规则

```
语法：@path（行首或空格后）
支持：./relative  ~/home  /absolute  bare-path
      @./path\ with\ spaces.md（转义空格）
      @./file.md#section（片段标识符被剥离）

排除：代码块和行内代码中的 @ 不解析

限制：
  MAX_INCLUDE_DEPTH = 5          ← 防无限递归
  循环检测 via processedPaths Set
  二进制文件排除（.png/.pdf/.exe 等 → 跳过）
  外部文件（cwd 之外）需要信任批准
```

---

## 六、HTML 注释剥离

```markdown
<!-- 这是给维护者看的注释，Agent 不应该看到 -->

这是给 Agent 看的指令。

<!-- TODO: 下个版本加上安全检查 -->
```

CC 会剥离块级 HTML 注释但保留内容，让指令文件的维护者可以留注释而不影响 Agent 行为。

---

## 七、缓存管理 — 两种失效方式

```
方式 1: clearMemoryFileCaches()
  ├─ 触发场景：worktree 进入/退出、设置同步
  ├─ 行为：清除缓存，不触发 InstructionsLoaded Hook
  └─ 目的：正确性刷新

方式 2: resetGetMemoryFilesCache(reason)
  ├─ 触发场景：compaction 后重载、会话恢复
  ├─ 行为：清除缓存 + 标记"下次加载时触发 Hook"
  ├─ reason: 'session_start' | 'compact' | 'nested_traversal'
  └─ 目的：正确性 + 可观测性（Hook 通知）
```

---

## 八、InstructionsLoaded Hook — 指令加载的扩展点

```typescript
// 每个指令文件加载时触发
executeInstructionsLoadedHooks(filePath, memoryType, loadReason, {
  globs?,               // 条件规则的 glob 模式
  triggerFilePath?,      // 触发懒加载的文件
  parentFilePath?,       // @include 来源文件
})

// loadReason 类型：
'session_start'          // 会话启动时的全量加载
'compact'                // compaction 后重载
'nested_traversal'       // Agent 编辑文件触发的目录扫描
'path_glob_match'        // 条件规则匹配
'include'                // @include 加载
```

**用途**：企业可以用 Hook 审计"哪些指令文件被加载了"，或在指令加载时注入额外上下文。

---

## 九、实现模板

```python
from pathlib import Path
from dataclasses import dataclass
import re, yaml

@dataclass
class InstructionFile:
    path: str
    layer: str           # 'managed' | 'user' | 'project' | 'local'
    content: str
    globs: list[str] | None = None  # 条件规则
    parent: str | None = None       # @include 来源

class InstructionFileSystem:
    MANAGED_PATH = Path('/etc/myagent')
    MAX_INCLUDE_DEPTH = 5

    def __init__(self, cwd: str, home: str):
        self.cwd = Path(cwd)
        self.home = Path(home)
        self._cache: list[InstructionFile] | None = None
        self._processed: set[str] = set()

    def load_all(self) -> list[InstructionFile]:
        """4 层优先级加载"""
        if self._cache: return self._cache
        files = []

        # Layer 1: Managed
        files.extend(self._load_layer(self.MANAGED_PATH, 'managed'))

        # Layer 2: User
        files.extend(self._load_layer(self.home / '.myagent', 'user'))

        # Layer 3: Project (向上遍历，根先处理)
        dirs = []
        current = self.cwd
        while current != current.parent:
            dirs.append(current)
            current = current.parent
        for d in reversed(dirs):  # 根 → cwd
            files.extend(self._load_layer(d, 'project'))

        # Layer 4: Local
        for d in reversed(dirs):
            local = d / 'AGENT.local.md'
            if local.exists():
                files.append(self._load_file(local, 'local'))

        self._cache = files
        return files

    def _load_layer(self, base: Path, layer: str) -> list[InstructionFile]:
        files = []
        # 主文件
        for name in ['AGENT.md', '.agent/AGENT.md']:
            path = base / name
            if path.exists():
                files.append(self._load_file(path, layer))
        # Rules 目录
        rules_dir = base / '.agent' / 'rules'
        if rules_dir.is_dir():
            for md in sorted(rules_dir.rglob('*.md')):
                files.append(self._load_file(md, layer))
        return files

    def _load_file(self, path: Path, layer: str, depth=0) -> InstructionFile:
        if str(path) in self._processed:
            return InstructionFile(str(path), layer, '[circular reference]')
        self._processed.add(str(path))

        content = path.read_text(encoding='utf-8')
        content = self._strip_html_comments(content)
        globs = self._extract_frontmatter_globs(content)
        if depth < self.MAX_INCLUDE_DEPTH:
            content = self._resolve_includes(content, path.parent, layer, depth)
        return InstructionFile(str(path), layer, content, globs)

    def _resolve_includes(self, content: str, base_dir: Path, layer: str, depth: int) -> str:
        def replace(match):
            ref = match.group(1).replace('\\ ', ' ')
            ref = ref.split('#')[0]  # 剥离片段标识符
            target = (base_dir / ref).resolve()
            if target.exists() and target.suffix in ('.md', '.txt'):
                included = self._load_file(target, layer, depth + 1)
                return included.content
            return match.group(0)
        return re.sub(r'(?:^|\s)@((?:[^\s\\]|\\ )+)', replace, content)

    def _extract_frontmatter_globs(self, content: str) -> list[str] | None:
        match = re.match(r'^---\s*\n(.*?)---\s*\n', content, re.DOTALL)
        if not match: return None
        try:
            fm = yaml.safe_load(match.group(1))
            paths = fm.get('paths', '')
            if not paths: return None
            return [p.strip() for p in paths.strip().split('\n') if p.strip()]
        except: return None

    def _strip_html_comments(self, content: str) -> str:
        return re.sub(r'<!--[\s\S]*?-->', '', content)

    def invalidate(self):
        self._cache = None
        self._processed.clear()
```

---

## 十、实施步骤

请分析用户的 $ARGUMENTS 中指定的项目，然后：

1. **定义层级**：至少 user + project 两层，有企业需求加 managed
2. **实现向上遍历**：从 cwd 到根，每层扫描指令文件
3. **实现 rules 目录**：条件规则用 frontmatter globs，两阶段加载
4. **实现 @include**：递归加载，MAX_DEPTH=5，循环检测
5. **HTML 注释剥离**：让维护者可以在指令文件里留注释
6. **缓存 + 两种失效**：正确性刷新（无 hook）vs 可观测性刷新（有 hook）
7. **worktree 去重**：嵌套工作树不重复加载主仓库规则

**反模式警告**：
- 不要让 Managed 层可被用户覆盖 — 组织策略是最高权威
- 不要让仓库内的指令文件不受限制 — 恶意仓库可能注入危险规则
- 不要忘了向上遍历 — monorepo 里子目录需要继承父目录的规则
- 不要无限递归 @include — 深度限制 + 循环检测
- 不要在代码块里解析 @include — 只在文本节点中解析
