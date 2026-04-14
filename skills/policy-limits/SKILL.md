---
name: policy-limits
description: "企业如何远程控制 Agent 可用功能，同时不阻塞用户工作"
user-invocable: true
argument-hint: "<目标项目路径或模块名>"
---

# 组织级策略限制 (Policy Limits)

## 1. Problem — 企业需要控制 Agent 能力，但不能因此阻塞用户

企业管理员需要禁用特定 Agent 功能（如外部网络访问、代码执行），但策略服务不可用时不应该让用户无法工作。

通用问题是：**如何远程门控 Agent 功能，同时保证策略服务故障时 Agent 仍可用。**

## 2. In Claude Code — 源码事实

- 入口：`src/services/policyLimits/index.ts`（664 行）
- 资格：仅 Team/Enterprise OAuth 用户
- 查询接口：`isPolicyAllowed('feature')` → boolean，查缓存零延迟
- Fail-open：缓存为空时返回 `true`（全部允许）
- 后台轮询：固定间隔 + ETag 条件请求 + 指数退避重试
- Essential-traffic-only 模式：服务端压力大时减少轮询
- 启动时首次拉取有超时，不阻塞太久

## 3. Transferable Pattern — Fail-Open 远程门控

从 CC 抽象出来：
1. **Fail-open 而非 fail-closed**。策略服务不可用 ≠ 用户不能工作。宁可短暂放行也不阻塞
2. **缓存查询，异步刷新**。运行时查缓存零延迟，后台异步刷新缓存
3. **Essential-traffic 降级**。检测到服务端压力时主动减少请求频率

## 4. Minimal Portable Version

最小版：**本地配置文件黑名单**（`{ "disabledFeatures": ["web_search", "bash_execute"] }`）。不需要远程 API、ETag、后台轮询。

升级路径：本地黑名单 → + 远程 API 拉取 → + ETag 缓存 → + fail-open 降级 → + essential-traffic 模式

## 5. Do Not Cargo-Cult

1. **不要照搬 fail-open**。某些高安全场景（如金融合规）可能需要 fail-closed
2. **不要照搬 OAuth 资格检查**。如果你的系统有其他认证方式，适配即可
3. **不要照搬 essential-traffic 模式**。小规模部署不需要考虑服务端压力

## 6. Adaptation Matrix

| 项目类型 | 建议保留 | 建议删掉 |
|----------|---------|---------|
| 企业 Agent | 完整远程门控 | — |
| 小团队 | 本地配置黑名单 | 远程 API、ETag |
| 个人项目 | 不适用 | 全部 |

## 7. Implementation Steps

1. 定义可控功能列表（tool 名称、能力类别）
2. 实现 `isPolicyAllowed(feature)` 查询接口
3. 选择配置来源（本地文件 / 远程 API）
4. 实现 fail-open 降级逻辑
5. 在工具调用前检查策略

## 8. Source Anchors

| 关注点 | 文件 | 关键符号 |
|--------|------|---------|
| 策略查询 | `src/services/policyLimits/index.ts` | `isPolicyAllowed()`, `loadPolicyLimits()` |
| 资格检查 | `src/services/policyLimits/index.ts` | `isPolicyLimitsEligible()` |
