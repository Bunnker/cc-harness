---
name: platform-integration
description: "Agent 长时间运行时如何防止系统休眠，任务完成时如何通知用户"
user-invocable: true
argument-hint: "<目标项目路径或模块名>"
---

# 平台集成服务 (Platform Integration)

## 1. Problem — OS 默认行为干扰 Agent 长任务

Agent 执行长任务时：(1) 系统休眠中断 API 调用；(2) 任务完成时用户不在终端前，错过结果。这两个问题都需要与操作系统交互。

通用问题是：**如何让 Agent 的长任务不被系统休眠打断，且完成时能通知用户。**

## 2. In Claude Code — 源码事实

**防休眠** — `src/services/preventSleep.ts`（166 行）
- macOS：`caffeinate -di -t 300`（5 分钟超时 + 4 分钟重启间隔）
- 引用计数：`refCount` 管理多模块同时请求
- 自愈：子进程带超时启动，父进程崩溃后 caffeinate 自动退出
- `registerCleanup()` 注册正常退出清理

**通知** — `src/services/notifier.ts`（157 行）
- 多渠道 fallback：iTerm2 → Kitty → Ghostty → bell
- 自动检测 `TERM_PROGRAM` 环境变量选择渠道
- 执行用户自定义 notification hooks（settings.json 配置）
- 分析埋点追踪哪种渠道被使用

## 3. Transferable Pattern — 引用计数 + 自愈子进程 + 多渠道 fallback

从 CC 抽象出来：
1. **引用计数防休眠**：多模块可同时请求防休眠，最后一个释放时才停止。避免重复启动/提前停止
2. **自愈子进程**：子进程带超时，父进程崩溃后不留孤儿。定时重启保持连续性
3. **通知 fallback 链**：按终端类型尝试最佳渠道，不支持时降级到 bell

## 4. Minimal Portable Version

最小版：**任务完成时 `\x07`（bell 字符）通知 + 不做防休眠（大多数短任务不需要）**。

升级路径：bell 通知 → + 终端检测选渠道 → + 自定义 hook → + caffeinate 防休眠 → + 引用计数

## 5. Do Not Cargo-Cult

1. **不要照搬 `caffeinate`**。这只在 macOS 上可用。Linux 用 `systemd-inhibit`，Windows 用 `SetThreadExecutionState`
2. **不要照搬 iTerm2/Kitty 检测**。根据你的目标用户群体选择支持的终端
3. **不要照搬引用计数**。如果只有一个模块需要防休眠，直接 start/stop 更简单

## 6. Adaptation Matrix

| 项目类型 | 建议保留 | 建议删掉 | 注意事项 |
|----------|---------|---------|---------|
| CLI Agent | bell 通知 | 防休眠（短任务） | 最简单方案 |
| 长任务 Agent | 防休眠 + 通知 | 可简化终端检测 | 核心需求 |
| Web 应用 | 浏览器 Notification API | 全部 CLI 方案 | 完全不同的通知机制 |
| 服务端 | 不适用 | 全部 | 服务器不休眠 |

## 7. Implementation Steps

1. 确定是否需要防休眠——任务通常超过系统休眠时间吗？
2. 选择防休眠方案——平台检测 + 对应系统命令
3. 实现通知——bell 作为 baseline，按需添加高级渠道
4. 添加自定义 hook——让用户对接自己的通知渠道

## 8. Source Anchors

| 关注点 | 文件 | 关键符号 |
|--------|------|---------|
| 防休眠 | `src/services/preventSleep.ts` | `startPreventSleep()`, `stopPreventSleep()`, `refCount` |
| 通知 | `src/services/notifier.ts` | `sendNotification()`, `sendToChannel()` |
