---
name: settings-sync
description: "用户设置和记忆如何跨设备同步，而不被锁定在单台机器上"
user-invocable: true
argument-hint: "<目标项目路径或模块名>"
---

# 设置同步 (Settings Sync)

## 1. Problem — 设置和记忆锁定在单台机器上

用户在笔记本上配置的 Agent 偏好、积累的项目记忆，换到台式机后全部丢失。跨设备工作时需要重新配置。

通用问题是：**如何让用户的设置和记忆跨设备可用，同时控制同步范围和体积。**

## 2. In Claude Code — 源码事实

- 入口：`src/services/settingsSync/index.ts`（582 行）
- 方向：CLI 上传，CCR（云端）下载
- 同步内容：全局设置 + 全局记忆 + 项目设置 + 项目记忆
- 增量策略：只上传 `mtime > lastUploadedAt` 的文件
- 文件大小限制：`MAX_FILE_SIZE = 500 KB`，超过的静默跳过
- 重试：指数退避，永久错误（4xx）不重试
- 后台执行：`uploadUserSettingsInBackground()`

## 3. Transferable Pattern — 增量上传 + 按环境分方向

从 CC 抽象出来：
1. **单向分角色**：开发环境上传，云端环境下载。避免双向同步的冲突复杂度
2. **增量检测**：mtime 比对，只传变化文件。首次全量，后续增量
3. **体积控制**：文件大小上限防止异常文件（如膨胀的记忆文件）拖慢同步

## 4. Minimal Portable Version

最小版：**dotfiles git 仓库**（`~/.agent-config/` + git push/pull）。不需要服务端 API、增量检测、体积控制。

升级路径：git dotfiles → + rsync/rclone 脚本 → + 服务端 API → + 增量检测 → + 体积控制

## 5. Do Not Cargo-Cult

1. **不要照搬"CLI 上传 / CCR 下载"的单向模型**。如果你的用户在多台本地设备间切换，需要双向同步
2. **不要照搬 500KB 限制**。根据你的存储预算和网络环境调整
3. **不要照搬 mtime 增量检测**。某些文件系统的 mtime 精度不够，content hash 更可靠

## 6. Adaptation Matrix

| 项目类型 | 建议保留 | 建议删掉 |
|----------|---------|---------|
| 个人多设备 | git dotfiles 或简单同步 | 服务端 API |
| 企业多环境 | 完整 API 同步 + 增量 | 可简化体积控制 |
| 单设备 | 不适用 | 全部 |

## 7. Implementation Steps

1. 确定同步范围——哪些文件需要同步（设置/记忆/keybindings）
2. 选择同步通道——git / API / 文件同步服务
3. 实现增量检测——mtime 或 content hash
4. 添加体积控制——文件大小上限 + 敏感文件排除
5. 实现重试——指数退避 + 永久错误短路

## 8. Source Anchors

| 关注点 | 文件 | 关键符号 |
|--------|------|---------|
| 上传 | `src/services/settingsSync/index.ts` | `uploadUserSettingsInBackground()` |
| 下载 | `src/services/settingsSync/index.ts` | `downloadUserSettings()`, `redownloadUserSettings()` |
