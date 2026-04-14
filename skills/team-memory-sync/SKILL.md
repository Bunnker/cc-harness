---
name: team-memory-sync
description: "团队成员如何共享项目知识，同时防止密钥泄露"
user-invocable: true
argument-hint: "<目标项目路径或模块名>"
---

# 团队记忆同步 (Team Memory Sync)

## 1. Problem — 团队知识锁定在个人记忆中

Agent 学到的项目知识（架构决策、约定、入门指南）默认只存在于个人本地。新成员加入或换设备时，Agent 从零开始学习。手动共享文件容易遗漏，且有密钥泄露风险。

通用问题是：**如何让团队成员的 Agent 共享项目级知识，同时防止敏感信息（密钥、凭证）被意外上传。**

## 2. In Claude Code — 源码事实

- 入口：`src/services/teamMemorySync/index.ts`（1257 行）
- 同步语义：Pull = server wins per-key；Push = delta upload（只上传 hash 变化的 key）
- API：`GET/PUT /api/claude_code/team_memory?repo={owner/repo}`，支持 `view=hashes` 仅拉 checksums
- 冲突处理：412 ETag 冲突 → 重新 pull → 再 push
- 密钥扫描：`secretScanner.ts`（325 行）— 30+ 高置信度 gitleaks 规则，检测到密钥的文件跳过上传
- 文件监听：`watcher.ts`（388 行）— `fs.watch` recursive + 2 秒防抖 + 自身写入抑制 + 永久失败抑制
- 大 payload 分批：`batchDeltaByBytes()` 按 `MAX_PUT_BODY_BYTES` 分批上传

## 3. Transferable Pattern — Delta 同步 + 客户端密钥防护

从 CC 抽象出来，团队知识同步的核心是：**增量同步 + 推送前密钥扫描 + 乐观并发控制**。

关键原则：
1. **Server wins on pull**。拉取时服务端覆盖本地，消除"谁的版本更新"的争论
2. **Delta on push**。只上传变化的 key，减少带宽和冲突概率
3. **密钥扫描在客户端**。不依赖服务端检测，确保密钥永远不离开本地
4. **删除不传播**。本地删除文件不会删除服务端版本。下次 pull 会恢复。这防止误删

## 4. Minimal Portable Version

最小版：**git 仓库共享目录 + .gitignore 排除敏感文件**。不需要服务端 API、ETag、文件监听。手动 git push/pull 即可。

升级路径：git 共享 → + 密钥扫描 pre-commit hook → + 服务端 API → + 实时文件监听 → + ETag 乐观锁

## 5. Do Not Cargo-Cult

1. **不要照搬服务端 API 方案**。如果团队已用 git，直接用 git 子目录共享记忆文件更简单
2. **不要照搬 30+ 条密钥规则**。根据团队实际使用的服务选择 5-10 条高置信度规则即可
3. **不要照搬 fs.watch 实时监听**。CI/CD 步骤或 git hook 触发同步更可控
4. **不要照搬"删除不传播"语义**。如果你的团队需要删除传播，用 tombstone 标记即可

## 6. Adaptation Matrix

| 项目类型 | 建议保留 | 建议删掉 | 注意事项 |
|----------|---------|---------|---------|
| 小团队开源项目 | git 共享目录 | API 同步、文件监听 | .gitignore 排除敏感文件 |
| 企业团队 | 完整 API 同步 + 密钥扫描 | 可简化文件监听 | 需要认证基础设施 |
| 个人多设备 | 用 settings-sync 替代 | 团队同步 | 不需要团队语义 |

## 7. Implementation Steps

1. 确定共享范围——哪些记忆文件该共享，哪些是私有的
2. 选择同步通道——git / 服务端 API / 文件同步服务
3. 实现密钥扫描——至少覆盖 AWS/GCP/GitHub token 和 private key
4. 实现增量同步——hash 比对，只传变化的
5. 添加冲突处理——ETag 或 last-write-wins
6. 验证——模拟多人同时修改，确认不丢数据

## 8. Source Anchors

| 关注点 | 文件 | 关键符号 |
|--------|------|---------|
| 同步主逻辑 | `src/services/teamMemorySync/index.ts` | `pullTeamMemory()`, `pushTeamMemory()`, `syncTeamMemory()` |
| 密钥扫描 | `src/services/teamMemorySync/secretScanner.ts` | `scanForSecrets()`, `redactSecrets()` |
| 文件监听 | `src/services/teamMemorySync/watcher.ts` | `startTeamMemoryWatcher()`, `notifyTeamMemoryWrite()` |
