---
name: api-client-layer
description: "Agent 如何抽象多 LLM Provider，同时支持凭证刷新、重试和流式切换"
user-invocable: true
argument-hint: "<目标项目路径或模块名>"
---

# API 客户端层 (API Client Layer)

## 1. Problem — Provider 不同、凭证会过期、网络不可靠

Agent 调用 LLM API，但不同 Provider 有不同认证、SDK、端点。凭证可能请求中途过期。网络错误需要智能重试。

通用问题是：**如何用统一接口封装多 Provider，同时处理凭证刷新、重试和流式/非流式切换。**

## 2. In Claude Code — 源码事实

- 客户端创建：`src/services/api/client.ts` → `getAnthropicClient()` 启动时创建一次，非每次请求
- Provider 检测：`src/utils/model/providers.ts` → `getAPIProvider()` 支持 4 Provider（Anthropic / Bedrock / Vertex / Foundry）
- 凭证注入：OAuth 刷新在构建 headers 之前执行
- 自定义 headers：`x-app: 'cli'`、`X-Claude-Code-Session-Id`
- 双入口：`queryModelStreaming()` 和 `queryModelWithoutStreaming()` 共享同一客户端
- 双层重试：SDK 内置重试 + 应用层 `withRetry()` 指数退避

## 3. Transferable Pattern — 单例客户端 + Provider 工厂 + 凭证前置刷新

1. **单例客户端**。SDK 客户端内部维护连接池，重复创建浪费资源
2. **Provider 工厂**。检测环境 → 选 Provider → 创建对应客户端。上层不感知差异
3. **凭证前置刷新**。请求前检查过期，不是失败后才刷新
4. **双层重试**。SDK 层处理传输错误，应用层处理业务错误（429/5xx）

## 4. Minimal Portable Version

最小版：**单 Provider + 环境变量 API key + SDK 内置重试**。3 行代码。

升级路径：单 Provider → + 多 Provider 工厂 → + 凭证前置刷新 → + 应用层重试 → + 流式切换

## 5. Do Not Cargo-Cult

1. **不要照搬 4 Provider 支持**。大多数项目只需 1-2 个，按需添加
2. **不要照搬 `dangerouslyAllowBrowser: true`**。CC 第一方产品的特殊配置
3. **不要照搬自定义 headers**。`x-app` 等是 CC 分析追踪需求
4. **不要照搬双层重试**。SDK 已有重试时，应用层再加可能导致重试风暴

## 6. Adaptation Matrix

| 项目类型 | 建议保留 | 建议删掉 |
|----------|---------|---------|
| 单 Provider Agent | SDK 直接调用 | Provider 工厂、凭证刷新 |
| 多 Provider Agent | Provider 工厂 + 统一接口 | 可简化重试 |
| 高可用服务 | 双层重试 + 凭证刷新 | 可简化 Provider 检测 |
| 轻量脚本 | SDK 直接调用 | 全部抽象层 |

## 7. Implementation Steps

1. 选择 Provider——确定需要支持哪些
2. 创建客户端——单例模式，启动时创建
3. 如多 Provider：实现工厂模式
4. 如有 OAuth：请求前添加凭证刷新
5. 实现流式/非流式接口
6. 验证——模拟 token 过期、网络超时

## 8. Source Anchors

| 关注点 | 文件 | 关键符号 |
|--------|------|---------|
| 客户端创建 | `src/services/api/client.ts` | `getAnthropicClient()` |
| Provider 检测 | `src/utils/model/providers.ts` | `getAPIProvider()` |
| 流式调用 | `src/services/api/claude.ts` | `queryModelStreaming()`, `queryModelWithoutStreaming()` |
| 重试策略 | `src/services/api/withRetry.ts` | `withRetry()`, `getRetryDelay()` |
