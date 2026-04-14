# 编码验证协议

> 来源：CC 的 `adjustIndexToPreserveAPIInvariants()`（编译时不变式保护）、
> `DiagnosticTrackingService`（修改后检查新增错误）、
> `runPostCompactCleanup()`（状态变更后全量清理验证）、
> `verificationAgent.ts`（独立验证层：按变更类型跑 build/test suite/linters/真实运行检查）
>
> **CC 的验证哲学**：CC 没有把验证建立在传统的单元测试目录上（__tests__/jest/vitest），但它有独立的验证层——verificationAgent 明确要求按变更类型选择验证手段（build、test suite、linters、真实运行），并强调"test suite 只是上下文，不是证据"。harness 沿用这个哲学：验证是编排流程的一部分，不是独立的测试 skill。

harness 在编码阶段完成后，REPORT 前必须执行验证。设计阶段不需要。

## 零、Pre-dispatch 基线捕获（Worker 调度前执行）

> 对齐 CC 的 `DiagnosticTrackingService.captureBaseline()` —— 修改前先记录当前状态，修改后只关注新增错误。

```
对计划中每个编码 Worker 的 target_paths：

1. 发现项目可用的 **lint/typecheck** 命令（仅静态分析，不含 test/smoke）：
   - CLAUDE.md 中声明的 lint/typecheck 命令
   - README.md 中的验证命令段落
   - package.json 的 scripts.lint / scripts.typecheck
   - pyproject.toml 的 [tool.ruff] / [tool.mypy]
   - Makefile / justfile 中的 lint / typecheck / check 目标
   - 都没有 → 跳过基线，在 Report 中标注"⚠️ 无可用 lint/typecheck 命令"

   **不纳入基线的命令**：pytest / test suite / health check / smoke_tests
   — 这些是功能验证，输出非确定性，不适合做"新增诊断 diff"。
   它们仍然在后续的运行时不变式验证（第 4 步）和 smoke test 中执行。

2. 执行发现的命令，捕获输出作为 baseline：
   baseline = {
     command: "ruff check backend/runtime/src/",
     output: "... 3 warnings ...",
     exit_code: 0,
     timestamp: "..."
   }

3. baseline 存在 Coordinator 内存中（不写 state），供 Worker 完成后的 diff 使用
```

---

## 一、单 Worker 验证（每个 Worker 完成后立即执行）

### 1. 文件存在性

Worker 声明要产出的文件必须全部存在。用 Bash `ls` 检查：

```
对 Worker 预期产出的每个文件路径：
  ls {path} → 存在则通过
  不存在 → Worker 标记为 partial，Report 中列出缺失文件
```

### 2. 语法检查（按语言）

| 语言 | 命令 | 失败处理 |
|------|------|---------|
| TypeScript | `npx tsc --noEmit --pretty {files}` | 收集错误，不中止 |
| Python | `python -m py_compile {file}` | 收集错误，不中止 |
| Go | `go build ./...` | 收集错误，不中止 |
| Rust | `cargo check` | 收集错误，不中止 |
| 其他 | 跳过语法检查 | — |

**关键**：语法错误不中止整个 Report，而是标记该 Worker 为 `⚠️ partial` 并在 Report 中列出。
原因：CC 的 DiagnosticTrackingService 也是"收集诊断 → 注入到下次调用"而非"中止当前操作"。

### 3. 路径越界检查

Worker 实际修改的文件是否在 Coordinator 计划中声明的目标路径范围内：

```
对 Worker 执行期间创建/修改的每个文件：
  如果不在计划声明的 target_paths 中 → 标记为越界
  越界文件列入 Report 的"意外修改"段落
```

### 3+. Post-worker Diff 验证（对齐 CC 的 DiagnosticTrackingService 基线比较）

> 核心思路：只追责 Worker **新增**的问题，不把项目原有的 lint 告警算到 Worker 头上。

```
如果第零步（Pre-dispatch）捕获了 baseline：

1. 用同一命令重跑 linter/typecheck：
   post_result = run(baseline.command)

2. Diff 基线和当前输出：
   new_issues = post_result.output - baseline.output

3. 判定：
   - new_issues 为空 → 通过（Worker 没引入新问题）
   - new_issues 不为空 → 标记 ⚠️，在 Report 中只列出新增的诊断
   - 命令执行失败（exit_code 非 0 且 baseline 是 0）→ Worker 引入了编译/类型错误

4. 不中止 Report（对齐 CC 的"收集诊断 → 注入到下次调用"模式）

如果没有 baseline（第零步跳过）：
  跳过 diff 验证，走原有的语法检查路径
```

---

### 4. 运行时不变式验证（按项目约束）

如果 `harness-state.json` 的 `constraints` 中包含框架运行时规则，逐条验证 Worker 产出是否违反：

```
常见不变式及验证方式：

| 不变式 | 验证命令 | 失败处理 |
|--------|---------|---------|
| "state 字段必须可序列化" | grep Worker 产出中新增的 state 字段，检查类型是否为基础类型/dict/list | 标记 ⚠️，列出不可序列化字段 |
| "图节点接口不可变" | diff Worker 产出中函数签名与修改前的签名 | 标记 INTERFACE_CHANGE，检查下游节点 |
| "不引入新的全局状态" | grep Worker 产出中的全局变量/单例 | 标记 ⚠️ |
| 项目自定义规则 | 按 constraints 描述构造检查命令 | 标记 ⚠️ |

验证分两级：

**静态检查（Coordinator 执行）：**
  读 Worker 产出代码 + 对照 constraints 逐条 grep/diff。
  能发现直接违反（如 state 字段类型明显不可序列化）。
  局限：抓不住通过 helper/wrapper 间接注入的不可序列化对象。

**必跑 smoke test（Bash 执行，不可跳过）：**
  对 constraints 中标注为"运行时不变式"的规则，必须跑最小验证脚本：

  | 不变式 | smoke test 命令 | 超时 |
  |--------|----------------|------|
  | state 可序列化 | `python -c "from {module} import {StateClass}; import msgpack; s = {StateClass}({最小必填字段}); packed = msgpack.packb(s.__dict__); assert msgpack.unpackb(packed)"` 或项目自定义的 `pytest tests/test_state_serialization.py`（构造真实 state 做 round-trip，不是只检查注解） | 30s |
  | 图节点接口兼容 | `python -c "from {graph_module} import build_graph; g = build_graph(); g.get_graph()"` | 30s |
  | 进程启动 | 项目自定义的 hello test（如 `curl localhost:8001/health`） | 60s |

  smoke test 失败 → Worker 状态标记为 ⚠️ partial，modules status 不升级为 implemented。
  smoke test 命令来源：constraints 中的规则描述，或 harness-state.json 的 `smoke_tests` 字段（如果有）。
  如果项目没有 smoke test → 在 Report 中标注"⚠️ 缺少运行时验证，建议手动测试"。
```

> **与语法检查的区别**：语法检查验证"代码能不能跑"，不变式验证验证"代码跑起来会不会破坏系统"。两者都不中止 Report，都是标记问题让 Coordinator 决策。

### 5. 结构保真检查

```
对每个修改了现有文件的 Worker：
  1. 检查 diff 行数占文件总行数的比例
     - > 50% → 标注"⚠️ 大范围重写"，在 Report 中说明
  2. 检查是否有 INTERFACE_CHANGE 声明
     - 有 → 检查下游模块是否需要同步修改
     - 改了接口但没声明 → 标注"❌ 未声明的接口变更"
  3. 检查是否引入了不属于目标模块职责的功能
     - Coordinator 读同目录其他文件，判断职责是否越界
```

---

## 二、跨 Worker 兼容性检查（所有 Worker 完成后、Report 前执行）

### 1. 接口签名对齐

如果两个 Worker 的产出之间存在 import/依赖关系（在 dependency-graph 中有箭头）：

```
Worker A 产出 module_a.py，export 了 class ToolRegistry
Worker B 产出 module_b.py，import 了 from module_a import ToolRegistry

检查：
  1. Worker A 的 export 名称是否和 Worker B 的 import 名称一致
  2. 如果 Worker A 定义了类型签名，Worker B 的调用是否匹配

检查方式：Coordinator 自己阅读两个 Worker 的产出代码，
对比 export/import 名称和参数签名。不依赖 IDE 工具。
```

**CC 对齐**：CC 的 `ensureToolResultPairing()` 保证 tool_use/tool_result 配对完整——同理，harness 保证 export/import 配对完整。

### 2. 命名冲突检测

同一并行组的 Worker 产出是否有同名文件/函数/类：

```
收集所有 Worker 产出的文件路径 → 检查是否有重复
收集所有 Worker 产出的顶层 export 名称 → 检查是否有冲突
```

### 3. 约定一致性

检查所有 Worker 产出是否遵循相同的编码约定：

```
在目标项目中 grep 已有代码的命名风格：
  snake_case vs camelCase
  tab vs space
  单引号 vs 双引号

如果 Worker 产出的风格和项目已有代码不一致 → 在 Report 中标注
```

## 三、Coordinator 判断规则

```
所有 6 项验证通过：
  → 正常 Report，更新 modules status 为 implemented

语法错误但可修复：
  → Report 中标注，建议下一轮"审计 + 修复"
  → modules status 保持 designed

Lint/typecheck diff 发现新增诊断：
  → Report 中只列出新增的诊断（不含项目原有告警）
  → modules status 保持 designed（Worker 引入了新的静态分析问题）

新行为分支无验证覆盖：
  → Worker 引入了行为分支（权限/fallback/状态机/Hook）但未附带测试
  → 且未在输出中说明原因和替代验证方式
  → modules status 不升级为 implemented，标注"⚠️ 缺少验证"
  → Coordinator 可记录豁免理由（如项目测试基础差、纯配置改动）后放行

运行时不变式违反（静态检查或 smoke test 失败）：
  → Report 中标注违反的 constraint + 失败的 smoke test 输出
  → modules status 保持 designed（不可升级 — 运行时可能崩溃）
  → 写入 learnings：记录哪条不变式被违反、Worker 做了什么导致违反

结构保真失败（大范围重写 / 未声明接口变更 / 职责越界）：
  → 大范围重写 → 标注 ⚠️，让用户判断是否接受
  → 未声明的接口变更 → modules status 保持 designed，检查下游影响
  → 职责越界 → 标注 ⚠️，建议拆分到正确的模块

跨 Worker 接口不对齐：
  → Report 中标注冲突点
  → 建议 Coordinator 在下一轮给出具体的接口约束再重新编码
  → modules status 保持 designed

路径越界：
  → Report 中列出越界文件
  → 建议 Coordinator 在下一轮缩小 Worker 的 target_paths
  → 不自动 revert（可能是有意为之，让用户判断）
```
