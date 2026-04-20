---
name: process-lifecycle
description: "Agent 进程如何优雅关闭，不丢数据不留孤儿不坏终端"
user-invocable: false
argument-hint: "<目标项目路径或模块名>"
---

# 进程生命周期 (Process Lifecycle)

## 1. Problem — 进程被杀时数据丢失、子进程变孤儿、终端状态损坏

Agent 进程可能被 SIGTERM、SIGINT、或 SIGKILL 中断。如果没有清理逻辑：对话记录可能丢失、子进程变孤儿、终端留在 alt screen 或隐藏光标状态。

通用问题是：**如何在进程退出时按正确顺序清理资源，同时处理同步和异步清理的差异。**

## 2. In Claude Code — 源码事实

- 清理注册：`src/utils/cleanupRegistry.ts` — `registerCleanup()` 注册清理函数，返回 unregister。LIFO 顺序执行
- 终端恢复：`src/utils/gracefulShutdown.ts` — 用 `writeSync()`（不是 write）因为崩溃时事件循环已死。恢复序列：禁用鼠标追踪 → 退出 alt screen → 禁用 Kitty keyboard → 禁用 ModifyOtherKeys → 禁用 focus reporting → 禁用 bracket paste → 显示光标 → 清除标题
- 多会话：Bridge/daemon 模式最多 32 个并发子进程。SIGTERM 给 30 秒宽限期，超时 SIGKILL。子进程退出不影响其他子进程
- 信号处理：SIGINT/SIGTERM → 清理 + 退出；SIGKILL → 无法捕获，靠 caffeinate 超时自愈

## 3. Transferable Pattern — LIFO 清理 + 同步终端恢复 + 宽限期

1. **LIFO 清理注册**。后注册的先清理——确保依赖关系正确（先关连接，再释放连接池）
2. **同步 I/O 恢复终端**。崩溃时事件循环死了，只有同步 I/O 能执行。终端恢复必须用 writeSync
3. **宽限期 + 强制杀**。给清理逻辑一个时间窗口，超时后强制退出。防止清理代码本身挂住
4. **子进程隔离**。一个子进程崩溃不应影响其他子进程或主进程

## 4. Minimal Portable Version

最小版：**`process.on('SIGINT', cleanup)` + 同步文件写入保存状态**。

升级路径：单个 SIGINT handler → + LIFO 注册表 → + 终端恢复 → + 宽限期 → + 多会话管理

## 5. Do Not Cargo-Cult

1. **不要照搬 ANSI escape 序列**。`\x1b[?1003l` 等是特定终端的恢复码。你的项目可能不用 alt screen
2. **不要照搬 30 秒宽限期**。这是 CC 基于平均清理时间调的。你的项目可能 5 秒就够
3. **不要照搬 32 并发会话限制**。这是 CC daemon 模式的容量规划数字
4. **不要照搬 writeSync**。如果你的项目不修改终端状态，不需要同步恢复

## 6. Adaptation Matrix

| 项目类型 | 建议保留 | 建议删掉 |
|----------|---------|---------|
| CLI Agent | SIGINT handler + LIFO 清理 | 多会话、终端恢复（如不用 alt screen） |
| 守护进程 | 完整：LIFO + 宽限期 + 子进程管理 | 终端恢复 |
| Web 服务 | LIFO 清理 + 宽限期 | 终端恢复、子进程 |
| 轻量脚本 | 单个 SIGINT handler | 全部高级机制 |

## 7. Implementation Steps

1. 实现清理注册表——registerCleanup(fn) 返回 unregister
2. 实现信号处理——SIGINT/SIGTERM → 调用清理链
3. 如果用终端：添加终端状态恢复（同步 I/O）
4. 如果有子进程：添加宽限期 + 强制杀
5. 在关键资源获取处注册清理——文件锁、数据库连接、临时文件
6. 验证——Ctrl+C 后终端是否恢复？临时文件是否清理？

## 8. Source Anchors

| 关注点 | 文件 | 关键符号 |
|--------|------|---------|
| 清理注册表 | `src/utils/cleanupRegistry.ts` | `registerCleanup()` |
| 终端恢复 | `src/utils/gracefulShutdown.ts` | `writeSync()` 恢复序列 |
| 信号处理 | `src/entrypoints/cli.tsx` | SIGINT/SIGTERM handlers |
