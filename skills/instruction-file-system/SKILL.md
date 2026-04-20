---
name: instruction-file-system
description: "指导如何设计层级化指令文件系统：多层来源、向上遍历、条件规则、include 解析、缓存与信任边界"
user-invocable: true
argument-hint: "<目标项目路径或模块名>"
---

# 指令文件系统 (Instruction File System)

## 1. Problem — 指令不该硬编码在 prompt 常量里

成熟的 Agent Runtime 通常会同时拥有：

- 组织或平台级强制规则
- 用户级长期偏好
- 项目级共享规范
- 本地私有补充说明
- 按路径或模块条件激活的局部规则

如果这些内容全部写进一个大 system prompt，会立刻遇到问题：

- 无法按目录或文件类型做局部约束
- 团队共享规则和个人规则混在一起
- include / 复用机制缺失，规则只能复制粘贴
- 恶意仓库可能借规则文件注入越权行为

通用问题是：**如何把“运行时指令”做成一个可分层、可遍历、可条件激活、可缓存、可审计的文件系统。**

---

## 2. In Claude Code — 源码事实（精简版）

> `源码事实` — CC 的 `claudemd.ts` 很重，这里只保留可迁移的骨架。

### CC 有多层指令来源

按治理强度和覆盖范围，大致包括：

- managed / org 级规则
- user 全局规则
- project 共享规则
- local 私有规则

项目级规则还会沿当前工作目录向上遍历加载，越靠近当前 cwd 的规则优先级越高。

### 规则不只有“无条件文本”

CC 支持 `.claude/rules/*.md` 这类条件规则文件，规则可以带 frontmatter，例如按 `paths` / glob 激活。

因此系统需要区分：

- 启动时立即生效的无条件规则
- 运行时按目标文件路径激活的条件规则

### include 是一等机制

规则文件可以引用其他规则文件，但要处理：

- 相对路径 / 绝对路径 / home 路径
- 深度限制
- 循环 include
- 外部路径信任边界

### worktree / 嵌套项目需要去重

向上遍历时如果项目有 worktree、子仓库或嵌套 `.claude` 目录，可能会重复加载同一批规则。CC 里专门有 canonical root 与 git root 的去重逻辑。

### 缓存和 hook 是可观测性的一部分

CC 不只是“读完文件完事”，还区分：

- 正确性刷新
- compaction / session 恢复后的强制重载
- InstructionsLoaded 等加载事件

重点是：指令系统要能说明“为什么这批规则会在这一轮生效”。

---

## 3. Transferable Pattern — Layered Sources + Conditional Rules + Include Resolver

### 核心模式

把指令系统拆成五个部件：

1. `source layers`
   定义 managed / user / project / local 的顺序和作用域。
2. `directory traversal`
   决定项目级规则从哪里开始向上搜集。
3. `rule loader`
   负责把无条件规则和条件规则拆开存储。
4. `include resolver`
   负责解析 `@include`，做深度限制、循环检测和信任校验。
5. `instruction cache`
   把“当前上下文下实际生效的规则集”缓存起来，并标记失效原因。

### 推荐数据模型

```text
InstructionFile:
  path
  layer
  body
  conditions
  included_from

InstructionSnapshot:
  always_on
  conditional_rules
  activated_rules
  load_reason
```

### 关键原则

1. 规则来源顺序要显式，不能靠文件名碰巧覆盖。
2. 项目级规则的遍历方向必须稳定，否则优先级会漂移。
3. 条件规则和无条件规则要分开存，直到真正命中路径再激活。
4. include 解析必须受信任边界约束，不能默认跨仓库读任意路径。
5. 缓存失效要带 reason，方便解释“为什么这轮规则变了”。

---

## 4. Minimal Portable Version — Python 最小实现

```python
from dataclasses import dataclass
from pathlib import Path
import fnmatch


@dataclass
class Rule:
    path: Path
    layer: str
    body: str
    globs: list[str]


class InstructionLoader:
    def __init__(self, roots: list[Path]):
        self.roots = roots

    def traverse_project_dirs(self, cwd: Path) -> list[Path]:
        dirs = []
        current = cwd.resolve()
        while True:
            dirs.append(current)
            if current.parent == current:
                break
            current = current.parent
        return list(reversed(dirs))

    def collect_rules(self, cwd: Path) -> list[Rule]:
        rules: list[Rule] = []
        for directory in self.traverse_project_dirs(cwd):
            rules.extend(self._load_from_dir(directory))
        return rules

    def activate(self, rules: list[Rule], target_path: str | None) -> list[Rule]:
        active = []
        for rule in rules:
            if not rule.globs:
                active.append(rule)
                continue
            if target_path and any(fnmatch.fnmatch(target_path, pattern) for pattern in rule.globs):
                active.append(rule)
        return active

    def _load_from_dir(self, directory: Path) -> list[Rule]:
        candidates = []
        for rule_path in sorted((directory / ".agent" / "rules").glob("*.md")):
            body = rule_path.read_text(encoding="utf-8")
            candidates.append(Rule(path=rule_path, layer="project", body=body, globs=[]))
        return candidates
```

这个最小版表达的是：

- 项目级向上遍历
- 规则对象化而不是直接拼字符串
- 条件规则延迟到 target path 明确时再激活

---

## 5. Do Not Cargo-Cult

不要照抄这些 CC 细节：

- 精确的 managed 路径和目录命名
- HTML 注释剥离的细粒度规则
- 所有 Hook 名称和触发时机
- worktree / canonical root 的具体实现细节
- `claudemd.ts` 里庞大的缓存与统计代码

真正该迁移的是：

- 来源分层
- 向上遍历的稳定顺序
- 条件规则延迟激活
- include 深度/循环/信任边界
- 带 reason 的缓存失效

---

## 6. Adaptation Matrix

| 场景 | 推荐来源层 | 特别注意 |
|------|------------|----------|
| 个人本地工具 | user + project + local | 先把条件规则和 include 做对 |
| 团队仓库 / monorepo | managed + user + project + local | 目录遍历和子项目边界要稳定 |
| 企业托管 | managed 强制 + project 可选 | 必须允许平台禁用项目级规则 |
| IDE / LSP 集成 | user + workspace + per-file conditional | target file 变化应触发懒激活 |

---

## 7. Implementation Steps

请分析用户的 `$ARGUMENTS`，然后：

1. 定义规则来源层及优先级，不要先写拼接 prompt 的代码。
2. 明确项目级目录遍历起点、终点和覆盖顺序。
3. 把规则解析成结构化对象：`body / conditions / layer / provenance`。
4. 实现 include resolver，并加上深度限制、循环检测和信任边界。
5. 把无条件规则与条件规则分开存储，再根据 target path 激活。
6. 为缓存增加 `load_reason`，至少区分 session start、manual reload、path activation。
7. 补回归测试：目录优先级、条件命中、include 循环、外部路径拒绝、worktree 去重。

验收标准：

- 任一规则都能解释来源与激活原因
- target path 变化只激活相关条件规则
- include 不会无限递归或越界读取不可信路径
- 项目遍历顺序稳定且可预测
