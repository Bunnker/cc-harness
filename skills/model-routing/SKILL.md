---
name: model-routing
description: "Agent 如何在运行时动态选择模型，而不是硬编码一个模型 ID"
user-invocable: false
argument-hint: "<目标项目路径或模块名>"
---

# 模型路由系统 (Model Routing)

## 1. Problem — 不同场景需要不同模型，硬编码不灵活

不同操作适合不同模型：主循环用大模型，摘要用小模型，plan 模式用最强模型。用户可能临时切换。订阅层级限制可用模型。

通用问题是：**如何根据运行时上下文动态选择模型。**

## 2. In Claude Code — 源码事实

- 主入口：`src/utils/model/model.ts` → `getMainLoopModel()` 和 `getRuntimeMainLoopModel()`
- 5 级优先级：session override > `--model` flag > `ANTHROPIC_MODEL` env > settings.model > 订阅默认值
- 运行时别名：`opusplan` = plan 模式用 Opus，其他用 Sonnet；超过 200K tokens 降级到 Sonnet
- Haiku 自动升级：plan 模式中 Haiku → Sonnet
- 子 Agent 继承：默认继承父 Agent 模型，可通过 Agent 定义覆盖
- 1M 窗口门控：4 条件（设置未禁用 + 非 Pro + 第一方 API + OAuth 有效）
- 小快模型：`getSmallFastModel()` 返回 Haiku，用于低价值高频操作

## 3. Transferable Pattern — 优先级链 + 上下文路由

1. **优先级链选模型**。临时覆盖 > CLI 参数 > 环境变量 > 配置 > 默认值
2. **上下文驱动路由**。根据当前操作动态选择：思考密集用大模型，机械性用小模型
3. **资源感知降级**。接近窗口极限时降级或触发压缩
4. **子 Agent 继承但可覆盖**。默认继承避免配置扩散，允许特定声明

## 4. Minimal Portable Version

最小版：**配置文件指定默认模型 + 环境变量覆盖**。

升级路径：单模型 → + 环境变量覆盖 → + 按任务选模型 → + 运行时降级 → + 订阅映射

## 5. Do Not Cargo-Cult

1. **不要照搬 `opusplan` 别名**。CC 特有 UX，把两个模型绑到一个名字
2. **不要照搬 200K token 降级阈值**。这是 Opus/Sonnet 窗口差异的结果
3. **不要照搬订阅 → 默认模型映射**。Max=Opus/Pro=Sonnet 是商业决策
4. **不要照搬 1M 窗口 4 条件门控**。CC 特有的产品限制
5. **不要照搬 Haiku 自动升级**。你的场景可能正好需要小模型

## 6. Adaptation Matrix

| 项目类型 | 建议保留 | 建议删掉 |
|----------|---------|---------|
| 单模型 Agent | 环境变量覆盖 | 全部路由逻辑 |
| 多模型 Agent | 优先级链 + 按任务选模型 | 订阅层级、别名 |
| 成本敏感 | 按任务选模型 + 降级 | 别名、自动升级 |
| 多 Agent | 子 Agent 继承 + 覆盖 | 可简化优先级链 |

## 7. Implementation Steps

1. 定义模型选择优先级
2. 实现 `getModel(context)` 函数
3. 按需：按任务类型添加路由规则
4. 按需：资源感知降级
5. 子 Agent 继承——默认继承 + 允许覆盖
6. 验证——切换后行为一致？降级平滑？

## 8. Source Anchors

| 关注点 | 文件 | 关键符号 |
|--------|------|---------|
| 优先级链 | `src/utils/model/model.ts` | `getMainLoopModel()` |
| 运行时路由 | `src/utils/model/model.ts` | `getRuntimeMainLoopModel()` |
| 小快模型 | `src/utils/model/model.ts` | `getSmallFastModel()` |
| Provider | `src/utils/model/providers.ts` | `getAPIProvider()` |
| 上下文窗口 | `src/utils/context.ts` | `getContextWindowForModel()` |
