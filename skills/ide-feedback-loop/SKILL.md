---
name: ide-feedback-loop
description: "Agent 修改代码后如何自动感知引入的错误，而不是等用户报告"
user-invocable: true
argument-hint: "<目标项目路径或模块名>"
---

# IDE 反馈闭环 (IDE Feedback Loop)

## 1. Problem — Agent 在真空中写代码，不知道自己引入了错误

Agent 修改代码后，类型错误、lint 警告等诊断信息只在 IDE 中可见。Agent 看不到这些反馈，继续基于错误代码工作，直到用户手动指出。

通用问题是：**如何让 Agent 感知 IDE 级别的代码质量反馈，形成 修改 → 诊断 → 修正 的闭环。**

## 2. In Claude Code — 源码事实

- 诊断追踪：`src/services/diagnosticTracking.ts` — `DiagnosticTrackingService` 单例，维护基线 `Map<string, Diagnostic[]>`
- LSP 客户端：`src/services/lsp/LSPClient.ts` — vscode-jsonrpc 封装，stdio 通信
- LSP 管理器：`src/services/lsp/LSPServerManager.ts` — 按文件扩展名路由到对应语言服务器
- 被动反馈：`src/services/lsp/passiveFeedback.ts` — 监听 `textDocument/publishDiagnostics`，转换格式后注册为异步附件
- MCP 桥接：通过 `callIdeRpc('getDiagnostics', { uri })` 从 IDE 获取诊断
- 诊断摘要上限：`MAX_DIAGNOSTICS_SUMMARY_CHARS = 4000`

## 3. Transferable Pattern — 诊断基线 + 被动注入

从 CC 抽象出来，闭环的核心不是"运行 linter"，而是：**修改前捕获基线 → 修改后比较差异 → 新增错误自动注入到下次 API 调用**。

关键原则：
1. **基线比较而非绝对值**。项目本身可能有 100 个警告。Agent 只关心"我引入了几个新的"
2. **被动注入而非主动中断**。诊断信息作为附件注入下次调用，不打断当前工具链
3. **多源适配**。LSP、IDE RPC、CLI linter 都是诊断源。模式不绑定特定协议

## 4. Minimal Portable Version

最小版：**Agent 修改文件后运行 `eslint`/`tsc --noEmit`，把新增错误插到下次 prompt 里**。不需要 LSP、MCP 桥接、诊断追踪服务。

升级路径：CLI linter → + 基线比较 → + LSP 实时诊断 → + MCP IDE 桥接 → + 异步附件注入

## 5. Do Not Cargo-Cult

1. **不要照搬 LSP 多服务器架构**。如果项目只有一种语言，一个 linter 命令就够了
2. **不要照搬 MCP 桥接**。直接运行 CLI linter 更简单、更可靠、无需 IDE 依赖
3. **不要照搬 `MAX_DIAGNOSTICS_SUMMARY_CHARS = 4000`**。根据你的上下文窗口大小和诊断密度调整
4. **不要照搬连续失败计数器**。小项目的 linter 不太可能连续崩溃

## 6. Adaptation Matrix

| 项目类型 | 建议保留 | 建议删掉 | 注意事项 |
|----------|---------|---------|---------|
| CLI Agent | CLI linter + 基线比较 | LSP、MCP 桥接 | 最简单有效 |
| IDE 插件 Agent | 完整 LSP + MCP | CLI linter（IDE 已有） | 直接用 IDE 的诊断 API |
| CI/CD Agent | CLI linter | 所有实时机制 | batch 模式，不需要实时 |
| Web Agent | 不适用 | 全部 | 通常不修改本地文件 |

## 7. Implementation Steps

1. 选择诊断源——CLI linter / LSP / IDE API
2. 实现基线捕获——修改前记录当前诊断
3. 实现差异比较——修改后对比，提取新增错误
4. 实现注入——新增错误作为系统消息/附件注入下次调用
5. 验证——故意引入类型错误，检查 Agent 是否自动修正

## 8. Source Anchors

| 关注点 | 文件 | 关键符号 |
|--------|------|---------|
| 诊断追踪 | `src/services/diagnosticTracking.ts` | `DiagnosticTrackingService`, `captureBaseline()` |
| LSP 客户端 | `src/services/lsp/LSPClient.ts` | `LSPClient` class |
| 服务器管理 | `src/services/lsp/LSPServerManager.ts` | `openFile()`, `changeFile()` |
| 被动反馈 | `src/services/lsp/passiveFeedback.ts` | `registerPassiveFeedback()` |
| 配置加载 | `src/services/lsp/config.ts` | `loadLspConfig()` |
