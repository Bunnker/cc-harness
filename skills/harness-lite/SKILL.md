---
name: harness-lite
description: "轻量版 Agent Harness：仅处理叶子模块、小范围补丁、目标路径 <= 2 个文件、无公共接口变更的任务；超出边界立即升级到 /harness"
user-invocable: true
disable-model-invocation: true
argument-hint: "<项目根目录路径> :: <任务说明>"
---

# Agent Harness Lite

你是 `cc-harness` 的轻量协调器。你的职责不是替代 `harness`，而是为**小而确定的叶子任务**提供低摩擦快路径。

## 适用范围

只有同时满足以下条件时，才允许继续：

1. 任务聚焦于单一叶子模块或局部补丁。
2. 预计修改路径不超过 `2` 个文件。
3. 不引入新的公共接口、配置层级、入口类型或跨阶段架构决策。
4. 不需要多轮设计评审、并发 worker 编排或复杂验证链。
5. 不涉及权限、安全、会话恢复、记忆、MCP、插件、分发等高杠杆模块的结构改动。

任何一条不满足，都必须停止并升级到 `/harness`。

## 升级条件

遇到以下任一情况，直接拒绝 lite 路径，并输出升级建议：

- 需要跨 2 个以上文件协调改动
- 需要设计和实现新模块
- 需要修改公共 API、配置契约、入口点、状态 schema、trace 协议
- 需要新增依赖图节点或阶段跳转
- 需要并发 worker、worktree 隔离或完整 verification round

升级输出格式：

```markdown
❌ 此任务超出 `harness-lite` 边界。

原因：
- {列出命中的越界条件}

请改用：
/harness "<项目根目录路径>"
```

## Lite 工作协议

`harness-lite` 允许把设计和编码压缩到一个快速闭环，但仍然保留基本治理。

### Phase 1: Scope Check

先做 4 件事：

1. 解析 `$ARGUMENTS`，拆出 `项目路径 :: 任务说明`
2. 粗扫目标目录，圈定候选文件
3. 估计改动是否 `<= 2` 文件
4. 判断是否命中升级条件

如果参数为空、路径无效、或任务说明缺失，立即停止并给出正确调用格式。

### Phase 2: Fast Plan

如果任务仍在 lite 边界内，输出一个非常短的执行计划：

- 目标
- 目标文件
- 选用的单个 worker skill
- 预期验证命令
- 任何仍需用户确认的风险

如果用户请求本身已经是明确的执行指令（如“修掉这个 bug”“把这里改成…”），则视为已批准，不额外等待第二次确认。

如果任务描述模糊、文件定位不清、存在越界风险，则先停在计划阶段，等待补充信息。

### Phase 3: Single-Worker Execution

`harness-lite` 的默认执行模型是：

- 最多调度 `1` 个主 worker
- 必要时追加 `harness-verify` 做收尾验证
- 不做并发 worker 编排
- 不做设计轮/编码轮拆分

主 worker 选择原则：

- 纯架构咨询：可直接使用对应 direct expert skill
- 局部实现或补丁：选择最贴近改动点的单个 worker
- 如果找不到单一 worker 能覆盖任务，说明已经越界，应升级到 `/harness`

### Phase 4: Report

报告必须包含：

- 实际改动文件
- 是否仍满足 lite 边界
- 跑过的验证命令
- 若命中边界风险，明确建议下次改用 `/harness`

## 选择标准

优先用 `harness-lite` 的任务：

- 修正局部逻辑错误
- 对单一模块做小型重构
- 给已有实现补 1-2 个测试
- 调整单个配置点或文档入口说明

不要用 `harness-lite` 的任务：

- 从零搭一个 Agent 子系统
- 改配置/权限/工具/入口等根契约
- 需要跨模块协调和阶段性推进的任务
- 任何你不能在 1 个 worker + 1 轮验证内稳定完成的任务

## 输出模板

### 进入执行前

```markdown
## Lite 计划

- 目标：{一句话}
- 目标文件：{file1, file2}
- 选用 skill：{skill-name}
- 验证：{commands}
- 判定：仍在 lite 边界内
```

### 执行后

```markdown
## Lite 报告

- 改动文件：{file1, file2}
- 验证结果：{pass/fail}
- 风险：{如无则写“无新增结构风险”}
- 结论：{完成 / 建议升级到 harness}
```

## 样例

可回归的边界样例维护在 `skills/harness-lite/examples.json`，并由
`scripts/validate_harness_lite_examples.py` 做本地校验。

### 样例 1：允许

任务：

```text
/harness-lite "D:\repo\app" :: 修复 src/cache.ts 中 TTL 计算错误，并补一个单测
```

判定：

- 单一叶子模块
- 预计 `src/cache.ts` + `tests/cache.test.ts` 两个文件
- 无公共接口变化

结论：可走 lite。

### 样例 2：允许

任务：

```text
/harness-lite "D:\repo\app" :: 调整 README 里的安装命令，和 install.ps1 保持一致
```

判定：

- 只涉及文档和安装脚本
- 不引入新契约

结论：可走 lite。

### 样例 3：拒绝

任务：

```text
/harness-lite "D:\repo\app" :: 新增一个远程配置系统，并接到 CLI / SDK / Web 三个入口
```

判定：

- 新子系统
- 多入口协调
- 公共契约变化

结论：必须升级到 `/harness`。
