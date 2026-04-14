---
name: mcp-runtime
description: "Agent 如何发现、连接和管理外部工具服务器，而不是把所有工具硬编码"
user-invocable: true
argument-hint: "<目标项目路径或模块名>"
---

# MCP 运行时管理 (MCP Runtime)

## 1. Problem — 工具不能全部内置，需要动态发现和连接外部服务

Agent 的内置工具有限。用户可能需要连接数据库、调用内部 API、操作特定 SaaS。把所有工具都硬编码不可行。需要一种协议让 Agent 动态发现和调用外部工具。

通用问题是：**如何让 Agent 在运行时发现、连接、调用外部工具服务器，同时管理连接生命周期和权限。**

## 2. In Claude Code — 源码事实

- 配置级联：managed-mcp.json（策略层，只读）> ~/.claude/.mcp.json（全局）> .mcp.json（项目）> Agent frontmatter mcpServers
- 传输类型：stdio / HTTP / SSE / WebSocket
- 工具命名：`mcp__{serverName}__{toolName}` 全限定名
- 权限模型：`checkPermissions: () => ({ behavior: 'passthrough' })`——MCP 工具不做内部权限判断，由外层策略层决定
- 工具注解：继承 MCP schema 的 `readOnlyHint`、`destructiveHint`
- inputSchema 直接透传，不转换为 Zod
- 健康监控：连接断开时标记不可用，重连策略

## 3. Transferable Pattern — 配置级联 + 协议适配 + 权限透传

1. **多层配置级联**。策略层（管理员控制）> 全局 > 项目 > 运行时。高层可以禁止低层的服务器
2. **协议适配器**。不同传输协议（stdio/HTTP/WS）统一到相同的 tool 接口，上层不感知差异
3. **权限透传而非内置**。MCP 工具的权限不在 MCP 层判断，透传给 Agent 的权限系统。分离关注点
4. **全限定工具名**。`{server}__{tool}` 避免不同服务器的工具名冲突

## 4. Minimal Portable Version

最小版：**单个 stdio MCP 服务器 + 配置文件指定**。不需要多层级联、多传输、权限透传。

升级路径：单服务器 → + 多服务器 → + 配置级联 → + 多传输协议 → + 权限透传 → + 健康监控

## 5. Do Not Cargo-Cult

1. **不要照搬 `mcp__` 命名前缀**。分隔符可以是任何不冲突的字符
2. **不要照搬 passthrough 权限模型**。CC 有独立权限层才能 passthrough。如果你没有权限层，MCP 工具需要自己做权限检查
3. **不要照搬 4 层配置级联**。大多数项目只需要一个配置文件
4. **不要照搬 inputSchema 直接透传**。如果你需要类型安全，转换为你的 schema 系统更可靠

## 6. Adaptation Matrix

| 项目类型 | 建议保留 | 建议删掉 |
|----------|---------|---------|
| 单服务器集成 | stdio 连接 + 配置文件 | 级联、多传输、健康监控 |
| 多服务器平台 | 配置级联 + 全限定名 + 健康监控 | 可简化权限透传 |
| 企业部署 | 策略层（管理员控制）+ 权限透传 | 可简化传输协议 |
| 轻量脚本 | 直接 HTTP 调用 | 整个 MCP 协议 |

## 7. Implementation Steps

1. 选择 MCP SDK——`@modelcontextprotocol/sdk` 或等效库
2. 实现配置加载——从配置文件读取服务器定义
3. 实现连接管理——启动/停止服务器，处理连接错误
4. 实现工具映射——MCP tools → Agent 工具格式
5. 集成到 Agent 工具池——让 MCP 工具和内置工具一起可用
6. 验证——服务器崩溃后 Agent 是否降级？工具名冲突？

## 8. Source Anchors

| 关注点 | 文件 | 关键符号 |
|--------|------|---------|
| 配置加载 | `src/services/mcp/config.ts` | MCP 配置级联逻辑 |
| 客户端管理 | `src/services/mcp/client.ts` | 连接建立、工具发现 |
| 工具映射 | `src/services/mcp/client.ts` | MCP tool → CC Tool 转换 |
| 类型定义 | `src/services/mcp/types.ts` | `MCPServerConnection` |
