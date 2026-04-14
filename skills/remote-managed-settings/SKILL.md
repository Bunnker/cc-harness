---
name: remote-managed-settings
description: "管理员如何远程覆盖 Agent 配置，同时不因网络故障阻塞用户"
user-invocable: true
argument-hint: "<目标项目路径或模块名>"
---

# 企业远程配置管理 (Remote Managed Settings)

## 1. Problem — 配置分散在各设备，管理员无法统一控制

企业部署 Agent 后，需要统一控制行为（如禁用某些工具、限制模型选择）。但配置分散在每台设备的本地文件中，远程推送配置又不能因网络问题阻塞用户。

通用问题是：**如何远程覆盖 Agent 配置，同时保证远程服务不可用时 Agent 仍能使用本地配置工作。**

## 2. In Claude Code — 源码事实

- 入口：`src/services/remoteManagedSettings/index.ts`（639 行）
- 资格：Console API key 全部有资格；OAuth 仅 Enterprise/C4E + Team
- Checksum 增量：`computeChecksumFromSettings()` SHA-256，ETag 条件请求
- 文件缓存：`~/.claude/.remote-managed-settings-cache`（settings + checksum + etag + fetchedAt）
- 安全审查：`securityCheck.tsx` — 危险设置显示阻塞对话框让用户确认
- Fail-open：超时/网络错误 → 使用文件缓存；缓存也没有 → 空配置（不阻塞）
- 后台轮询：1 小时间隔 + 指数退避重试
- Schema 验证：Zod，单字段验证失败忽略该字段不整体拒绝

## 3. Transferable Pattern — Checksum 增量 + Fail-Open + 安全审查

从 CC 抽象出来：
1. **Checksum 增量拉取**。SHA-256 + ETag 双重校验，304 时零传输
2. **三级降级**：远程成功 → 使用远程 / 远程失败 → 使用文件缓存 / 缓存也没有 → 使用空配置
3. **危险设置审查**。远程配置可能修改权限模型等敏感项，需要用户确认

## 4. Minimal Portable Version

最小版：**环境变量覆盖本地配置**（如 `AGENT_MODEL=haiku AGENT_DISABLE_TOOLS=bash`）。不需要远程 API、缓存、安全审查。

升级路径：环境变量 → + 远程 API 拉取 → + 文件缓存 → + Checksum 增量 → + 安全审查

## 5. Do Not Cargo-Cult

1. **不要照搬 Zod schema 验证**。根据你的配置复杂度选择验证方案
2. **不要照搬 React 阻塞对话框做安全审查**。CLI 环境用 stdin 确认即可
3. **不要照搬 1 小时轮询间隔**。根据配置变更频率调整

## 6. Adaptation Matrix

| 项目类型 | 建议保留 | 建议删掉 |
|----------|---------|---------|
| 企业 Agent | 完整远程配置 + 安全审查 | — |
| 小团队 | 环境变量 + 简单远程 API | Checksum、安全审查 |
| 个人项目 | 本地配置文件 | 全部远程机制 |

## 7. Implementation Steps

1. 确定哪些配置项需要远程可控
2. 实现配置合并逻辑（远程覆盖本地）
3. 选择远程配置通道（API / 配置中心 / 环境变量）
4. 实现 fail-open 降级
5. 对危险配置项添加确认机制

## 8. Source Anchors

| 关注点 | 文件 | 关键符号 |
|--------|------|---------|
| 加载主逻辑 | `src/services/remoteManagedSettings/index.ts` | `loadRemoteManagedSettings()`, `refreshRemoteManagedSettings()` |
| 安全审查 | `src/services/remoteManagedSettings/securityCheck.tsx` | `checkManagedSettingsSecurity()` |
| 缓存状态 | `src/services/remoteManagedSettings/syncCacheState.ts` | `getRemoteManagedSettingsSyncFromCache()` |
