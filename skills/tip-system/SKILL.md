---
name: tip-system
description: "用户等待时如何展示相关提示，而不是随机轮播或完全空白"
user-invocable: true
argument-hint: "<目标项目路径或模块名>"
---

# 上下文感知提示系统 (Tip System)

## 1. Problem — 用户等待时间被浪费，随机提示信噪比低

Agent 调用 API 时用户在等待。这段时间要么完全空白（浪费教育机会），要么随机展示提示（信噪比低，用户很快学会忽略）。

通用问题是：**如何在用户等待时展示与当前上下文相关的提示，且避免重复展示已知信息。**

---

## 2. In Claude Code — 源码事实

> `源码事实` — 以下内容可回钉到具体文件。

**三文件架构**

| 文件 | 职责 |
|------|------|
| `src/services/tips/tipRegistry.ts` | 提示注册中心：`externalTips` 数组 + `getRelevantTips()` 过滤函数 |
| `src/services/tips/tipScheduler.ts` | 调度器：`selectTipWithLongestTimeSinceShown()` + `getTipToShowOnSpinner()` |
| `src/services/tips/tipHistory.ts` | 历史追踪：`recordTipShown()` + `getSessionsSinceLastShown()` |

**提示数据结构**

- 每个 Tip 有 `id`、`text`、可选的 `relevance` 条件函数（接收 `TipContext`）、可选的 `cooldownSessions`
- `TipContext` 包含：platform、isVSCode、hasGitRepo、settings、featureFlags

**调度流程**

1. `getTipToShowOnSpinner(context)` — 检查 `spinnerTipsEnabled` 设置
2. `getRelevantTips(context)` — 遍历所有提示，执行 `relevance` 条件过滤 + `cooldownSessions` 冷却期检查
3. `selectTipWithLongestTimeSinceShown(tips)` — 按"距上次展示的会话数"降序排列，取最久未展示的
4. 展示后 `recordTipShown(tip.id)` — 写入 `globalConfig.tipHistory[tipId] = numStartups`

**LRU 核心**

```
getSessionsSinceLastShown(tipId):
  lastShown = globalConfig.tipHistory[tipId]
  if undefined → return Infinity  // 从未展示 → 最高优先
  return numStartups - lastShown
```

---

## 3. Transferable Pattern — 条件过滤 + LRU 调度的三阶段管道

> `抽象模式` — 从 CC 抽象出来，提示调度的核心是一个三阶段过滤管道。

```
全量提示池
  → Stage 1: 条件过滤（当前上下文是否相关）
  → Stage 2: 冷却期过滤（距上次展示是否够久）
  → Stage 3: LRU 选择（最久未展示的优先）
  → 展示 + 记录历史
```

### 关键设计原则

1. **相关性优先于新鲜度**。先过滤不相关的，再在相关的里选最久未展示的。反过来（先选最久的再检查相关性）会导致展示无关但"攒了很久"的提示。

2. **从未展示 = 最高优先**。`Infinity` 作为默认值确保新增提示总能被看到。

3. **冷却期用会话数而非时间**。用户一天开 10 次 CC 和一周开 1 次 CC 应该有不同的冷却效果。基于会话数（而非秒数）更贴合使用频率。

4. **持久化历史，不持久化状态**。只记录"什么时候展示过"，不记录"下次该展示什么"。调度逻辑无状态，每次从历史推导。

### 关键 Tradeoff

| 选择 | 好处 | 代价 |
|------|------|------|
| 条件函数做过滤 | 精准相关性 | 条件逻辑分散在各提示中 |
| 会话数做冷却 | 适配不同使用频率 | 需要全局启动计数器 |
| LRU 选择 | 均匀覆盖所有提示 | 可能展示用户已掌握的功能 |
| 全局配置持久化 | 跨会话记忆 | 依赖持久化层 |

---

## 4. Minimal Portable Version — 最小版：静态提示随机轮播

> `最小版` — 三步即可运行。

### 最小实现

```
1. 静态提示数组（硬编码 10-20 条）
2. 随机选取（或轮询）
3. 内存去重（Set 记录已展示的 ID，展示完一轮后重置）
```

不需要：条件过滤、持久化历史、冷却期、上下文对象

### 升级路径

```
Level 0: 静态数组 + 随机
Level 1: + 内存去重（展示过的不再展示，直到轮完）
Level 2: + 持久化历史（跨会话不重复）
Level 3: + 条件过滤（按上下文选择相关提示）
Level 4: + 冷却期（高频用户不会被同一条轰炸）
```

---

## 5. Do Not Cargo-Cult

> `不要照抄` — 以下是 CC 的具体实现选择，不是通用最佳实践。

1. **不要因为 CC 用 `numStartups` 计数会话，就照搬全局启动计数器**。如果你的项目有数据库，直接用时间戳记录上次展示时间更简单。CC 用启动计数是因为它没有数据库。

2. **不要因为 CC 每个提示都有条件函数，就给 5 条提示的小项目也上条件过滤**。提示少于 20 条时，随机选取 + 去重就够了，条件过滤的收益不值得复杂度。

3. **不要因为 CC 在 spinner 等待时展示提示，就认为只能在等待时展示**。启动时、任务完成时、错误恢复后都是展示提示的好时机。

4. **不要因为 CC 用全局配置持久化历史，就用配置文件存展示记录**。数据库、localStorage、甚至 cookie 都是有效的持久化方案。

5. **不要因为 CC 的提示内容是静态字符串，就认为提示不能是动态生成的**。基于用户行为模式动态生成的提示（如"你经常手动运行 tests，试试 /test 命令"）可能更有价值。

---

## 6. Adaptation Matrix

> `迁移建议` — 不同项目形态下的裁剪方案。

| 项目类型 | 建议保留 | 建议简化或删掉 | 注意事项 |
|----------|---------|---------------|---------|
| **CLI Agent** | LRU 调度 + spinner 集成 | 条件过滤（提示少时不需要） | 终端宽度有限，提示要短 |
| **Web 应用** | 条件过滤 + 持久化历史 | spinner 集成（用 toast/banner 替代） | 可用更丰富的 UI（链接、图片） |
| **IDE 插件** | 上下文感知（当前语言/文件类型） | 冷却期（IDE 会话概念不同） | 用 IDE 的通知机制 |
| **轻量脚本** | 静态数组 + 随机 | 所有高级特性 | 5 行代码解决 |
| **企业级平台** | 完整管道 + 自定义提示源 + A/B 测试 | — | 需要分析提示点击率/有效性 |

---

## 7. Implementation Steps

1. **识别展示时机** — Agent 有哪些等待点？启动、API 调用、长任务执行
2. **收集提示内容** — 列出 10-20 条最有价值的功能/快捷键/最佳实践
3. **实现最小版** — 静态数组 + 随机选取 + 内存去重
4. **添加持久化** — 记录展示历史，跨会话不重复
5. **添加上下文** — 定义 TipContext，为提示添加 relevance 条件
6. **添加冷却期** — 高频用户不被同一条反复展示
7. **添加自定义** — 允许用户/管理员添加自定义提示或禁用内置提示
8. **验证效果** — 追踪提示展示率和（如果可能的话）功能采用率

---

## 8. Source Anchors

> CC 源码锚点，用于追溯和深入阅读。

| 关注点 | 文件 | 关键符号 |
|--------|------|---------|
| 提示注册与过滤 | `src/services/tips/tipRegistry.ts` | `externalTips[]`, `getRelevantTips()` |
| 调度算法 | `src/services/tips/tipScheduler.ts` | `selectTipWithLongestTimeSinceShown()`, `getTipToShowOnSpinner()` |
| 展示历史持久化 | `src/services/tips/tipHistory.ts` | `recordTipShown()`, `getSessionsSinceLastShown()` |
| 设置禁用开关 | `src/utils/settings/settings.ts` | `spinnerTipsEnabled` |
