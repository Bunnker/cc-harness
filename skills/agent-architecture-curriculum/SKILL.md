---
name: agent-architecture-curriculum
description: "把 Agent/LLM runtime 源码理解重构成一套可学习的课程化文档: 用 Diataxis 拆成 tutorial/how-to/reference/explanation, 从入门到维护者视角讲清启动、query loop、tool execution、permission、memory、MCP、subagent、recovery 与 provider 差异"
user-invocable: true
argument-hint: "<目标项目路径、模块名或文档目录>"
---

# Agent Architecture Curriculum

> 目标不是再写一篇“大而全总览”，而是把源码级理解整理成一套真正能学会、能排障、能做改动的课程化文档体系。

## 适用场景

在这些情况下使用这个 skill：

- 你已经读过一批 Agent/LLM runtime 源码，想把理解沉淀成系统文档
- 你要给团队做 onboarding，希望新人能从入门走到可维护
- 你要把“源码笔记”升级成“可学习的架构教材”
- 你要审查现有文档，判断它们是不是只会讲概念，不会带人进 runtime
- 你要把某个模块写到 Harness 工程师可用的粒度

## 核心原则

### 1. 先教会，再总结

不要先写总览再往下展开。先确定读者读完后能做什么：

- 能追一次用户输入进入 `query()`
- 能解释一次 tool use 如何执行和回流
- 能定位权限拒绝、ToolSearch 失效、compact 触发、subagent 回流失败
- 能在不破坏主链的前提下改一个中等复杂功能

### 2. 文档必须按 Diataxis 拆开

不要把 tutorial、reference、explanation 混在同一篇里。

- `Tutorial`: 带读者跑通一条完整路径
- `How-to`: 解决一个真实工程问题
- `Reference`: 精确事实、字段、状态、接口、顺序
- `Explanation`: 为什么系统这样设计，权衡是什么

如果一段内容同时在“教做事”和“解释原理”，拆开写并相互链接。

### 3. 一切结论都要能回钉源码

每篇都必须给出源码锚点：

- 关键入口文件
- 核心函数
- 关键状态字段
- 异常 / fallback / cleanup 分支

如果只是推断，要显式写明“这是 inference，不是直接源码语句”。

### 4. 用运行时主链组织，不用目录树组织

优先写：

- 从哪里进入
- 状态如何流动
- 什么时候分叉
- 失败如何恢复
- 结果如何回流

不要按“这个目录下有 14 个文件”来铺文档。

### 5. 目标是培养维护者，不是培养读后感作者

每篇都要回答：

- 这个模块的职责边界是什么
- 它依赖上游什么输入
- 它向下游保证什么输出
- 常见误解是什么
- 调试时第一眼看哪里
- 改动它最容易破坏什么 invariant

## 输出契约

当你用这个 skill 写文档时，输出至少要包含这 5 层信息：

1. **心智模型**
   这模块在整个系统里到底干什么。

2. **真实执行链**
   从入口到退出的 runtime 顺序。

3. **关键状态与边界**
   哪些字段、缓存、attachments、signals、metadata 真正决定行为。

4. **失败与恢复路径**
   abort、fallback、retry、cleanup、resume、compact、notification。

5. **工程实践视角**
   如何 debug、如何验证、改动时会踩什么坑。

## 推荐课程地图

如果没有用户指定结构，优先按下面的顺序组织课程：

1. `startup and session assembly`
2. `processUserInput -> queue -> QueryEngine`
3. `query() state machine`
4. `tool execution and orchestration`
5. `permission and hook system`
6. `context compaction and memory`
7. `skills and command expansion`
8. `MCP runtime and ToolSearch`
9. `subagent, task, and notification model`
10. `conversation recovery and resume`
11. `API/provider behavior and fallback`
12. `architecture invariants and evolution`

## 每个模块都要产出的文档类型

不是每个模块都必须四篇都写，但你必须先判断应该写哪几类：

### Tutorial

适合这些主题：

- 跑通一次完整请求生命周期
- 跑通一次 async agent / background task
- 跑通一次 ToolSearch discover -> load -> call

写法要求：

- 一条路径走到底
- 不给过多分支
- 让读者在每一步都知道“此时应该看到什么”

### How-to

适合这些主题：

- 如何定位 `prompt_too_long`
- 如何判断一个 tool 为什么没执行
- 如何调试 `PermissionRequest` / `PermissionDenied`
- 如何排查 subagent 没有回通知
- 如何确认 compact 后 discovered tools 没丢

写法要求：

- 先说目标，再说观察点
- 按排障顺序组织
- 包含“如果 X，则继续查 Y”

### Reference

适合这些主题：

- 状态字段表
- 消息类型表
- attachment / tool_result / compact metadata 结构
- provider 差异矩阵
- permission 决策矩阵

写法要求：

- 只给精确信息
- 用表格或清单
- 不掺杂长篇解释

### Explanation

适合这些主题：

- 为什么 query loop 要做多层 compact
- 为什么 ToolSearch 要分 optimistic / definitive gate
- 为什么子 Agent 只能单向回流
- 为什么 remote / async / fork 不是一回事

写法要求：

- 讲 trade-off
- 讲历史演化
- 讲为什么没选别的方案

## 推荐单篇结构

如果你在写 explanation 或架构文档，优先采用这个骨架：

```markdown
# <Module Name>

## Why it exists
这个模块解决什么问题。

## Runtime path
真实执行顺序，按函数/状态展开。

## Boundaries
输入、输出、依赖、不变量。

## Failure modes
常见失败、恢复和清理路径。

## Debugging entry points
排障时先看哪些文件、哪些日志、哪些状态。

## Common misconceptions
最容易被说错的点。

## Source anchors
- path/to/fileA
- path/to/fileB
```

## Harness 工程师标准

如果目标是“写到具有 Harness 工程师能力”，每个模块都必须补 3 类内容：

### 1. 改动视角

写清：

- 改这个模块最容易破坏什么
- 上下游谁会受影响
- 应该补什么测试或验证

### 2. 排障视角

写清：

- 哪些现象对应哪条运行时分支
- 哪些日志 / telemetry / attachments 最关键
- 哪些错误其实是上游导致的假象

### 3. 演化视角

写清：

- 这是稳定主链还是实验分支
- 哪些 feature gate / provider 分支会改变行为
- 哪些 workaround 属于历史包袱

## 反模式

避免这些输出：

- 只给目录树，不给运行链
- 只给概念图，不给源码入口
- 只讲 happy path，不讲恢复路径
- 把一堆 reference 信息塞进 tutorial
- 把文档写成 changelog 式文件巡礼
- 给“看起来完整”的总结，但读者读完还是不会 debug

## 执行步骤

当用户要求你为某个项目或模块写课程化文档时：

1. 先识别读者阶段：入门、进阶、维护者。
2. 画出该模块的 runtime 主链，而不是目录树。
3. 用 Diataxis 判断该内容应拆成哪些文档类型。
4. 先产出 tutorial / explanation / reference 的最小闭环。
5. 再补 how-to，优先覆盖真实排障任务。
6. 每篇都补“common misconceptions”和“debugging entry points”。
7. 每个关键结论都给源码锚点。

## 成功标准

这个 skill 产出的文档，读完后应该让一个强工程师具备这些能力：

- 能讲清整条 agent runtime 的主链
- 能独立追一个复杂 bug 到具体模块
- 能判断一个设计是主链 invariant 还是实验分支
- 能在改代码前预判会破坏哪些边界
- 能从“会读文档”进化到“会维护系统”
