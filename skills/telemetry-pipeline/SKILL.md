---
name: telemetry-pipeline
description: "Agent 如何收集运行数据用于改进，同时不泄露用户代码和隐私"
user-invocable: false
argument-hint: "<目标项目路径或模块名>"
---

# 遥测管道 (Telemetry Pipeline)

## 1. Problem — 需要运行数据改进产品，但不能泄露用户隐私

Agent 需要遥测数据（使用频率、错误率、工具调用模式）来改进产品。但遥测不能包含用户代码、文件路径、凭证等 PII。泄露一次就是信任危机。

通用问题是：**如何收集有价值的运行数据，同时确保 PII 永远不离开用户设备。**

## 2. In Claude Code — 源码事实

- 入口：`src/services/analytics/index.ts` — 延迟 sink 绑定，事件队列到 `attachAnalyticsSink()` 调用时才 drain
- 队列 drain：`queueMicrotask()` 避免启动延迟
- PII 标记类型：`AnalyticsMetadata_I_VERIFIED_THIS_IS_NOT_CODE_OR_FILEPATHS` 和 `_PII_TAGGED`——类型名本身就是代码审查提醒
- `stripProtoFields()`：移除 `_PROTO_*` 键再发 Datadog（内部 BQ 导出保留）
- Check ID 系统：数字 ID 替换命令内容（如 `checkId: 8` = COMMAND_SUBSTITUTION），防止 shell 命令泄露
- 采样：启动事件 0.5%（外部）/ 100%（内部），工具使用 10%
- 隐私控制：用户可通过设置完全禁用遥测

## 3. Transferable Pattern — 延迟绑定 + PII 标记 + 内容替换

1. **延迟 sink 绑定**。事件先入队列，sink 在初始化完成后才绑定。避免启动时的循环依赖和延迟
2. **PII 标记在类型系统中**。字段类型名就是"我确认这不是 PII"的声明。代码审查时一目了然
3. **内容替换而非过滤**。不是"检测到敏感内容就丢弃事件"，而是"用 ID 替换内容"。保留了事件的统计价值
4. **采样分级**。高频低价值事件（工具调用）低采样率，低频高价值事件（启动/错误）高采样率

## 4. Minimal Portable Version

最小版：**console.log + 本地文件**。不需要 Datadog、采样、PII 标记。

升级路径：console.log → + 结构化日志文件 → + 远程 sink → + PII 过滤 → + 采样策略 → + 多 sink 分发

## 5. Do Not Cargo-Cult

1. **不要照搬采样率**。0.5%/100%/10% 是 CC 基于用户规模和 Datadog 成本调的
2. **不要照搬 `stripProtoFields()`**。这是 CC 内部 BQ 和 Datadog schema 差异的产物
3. **不要照搬 Check ID 系统**。如果你的事件不包含 shell 命令，不需要内容替换
4. **不要照搬类型名长度**。`AnalyticsMetadata_I_VERIFIED_THIS_IS_NOT_CODE_OR_FILEPATHS` 是有效的代码审查技巧，但你可以用更短的标记加注释

## 6. Adaptation Matrix

| 项目类型 | 建议保留 | 建议删掉 |
|----------|---------|---------|
| 个人项目 | 本地日志 | 远程 sink、采样、PII 标记 |
| SaaS 产品 | 完整管道 + PII 过滤 | 可简化 Check ID |
| 企业内部 | 结构化日志 + 审计追踪 | Datadog（用 ELK 替代） |
| 开源项目 | opt-in 遥测 + 隐私设置 | 默认开启的任何遥测 |

## 7. Implementation Steps

1. 定义事件 schema——哪些事件值得收集
2. 实现事件队列——延迟 sink 绑定
3. 实现 PII 过滤——标记所有字段，审查非标记字段
4. 选择 sink——console / 文件 / 远程服务
5. 实现采样——按事件类型设置不同采样率
6. 添加隐私控制——用户可禁用
7. 验证——检查发出的事件是否包含任何 PII

## 8. Source Anchors

| 关注点 | 文件 | 关键符号 |
|--------|------|---------|
| 事件队列 | `src/services/analytics/index.ts` | `logEvent()`, `attachAnalyticsSink()` |
| PII 标记 | `src/services/analytics/index.ts` | `AnalyticsMetadata_I_VERIFIED_*` types |
| GrowthBook | `src/services/analytics/growthbook.ts` | `getFeatureValue_CACHED_MAY_BE_STALE()` |
