---
name: startup-optimization
description: "指导如何优化应用启动性能：import 阶段并行预取、懒加载、编译期死代码消除、分阶段启动"
user-invocable: false
argument-hint: "<目标项目路径或模块名>"
---

# 启动性能优化模式 (Startup Optimization Patterns)

> 参考实现：Claude Code `src/entrypoints/cli.tsx` + `src/main.tsx`
> — 通过并行预取、懒加载、`feature()` 死代码消除、分阶段启动，将 CLI 冷启动控制在可感知阈值内

## 核心思想

**启动时间 = max(关键路径上最慢的操作)，不是 sum(所有操作)。** 把 I/O 并行化、非关键模块延迟到首次使用、不用的代码编译期就消除。

---

## 一、CC 的真实启动序列（源码级）

### Phase 1：CLI 入口 — 快速路径分流

```typescript
// src/entrypoints/cli.tsx — 最先执行
profileCheckpoint('cli_entry')

// 零开销快速路径（不 import main.tsx）
if (args.includes('--version')) { print(VERSION); exit(0) }
if (args.includes('--dump-system-prompt')) { /* minimal imports */ }
if (args.includes('--daemon-worker')) { /* lean worker spawn */ }

// 早期输入捕获 — 在 import 阶段就开始记录键盘输入
startCapturingEarlyInput()  // 不丢失用户在加载期间的击键

profileCheckpoint('cli_before_main_import')
const { main } = await import('./main.tsx')  // ~135ms 的 import 解析
profileCheckpoint('cli_after_main_import')
```

**洞察**：`--version` 不需要加载任何业务模块。CC 把快速路径检查放在所有 import 之前，`--version` 几乎 0ms 返回。

### Phase 2：main.tsx 模块评估 — import 期间并行预取

```typescript
// src/main.tsx — 模块顶层（import 时立即执行）
profileCheckpoint('main_tsx_entry')

// ★ 核心技巧：在 import 解析的 135ms 里"免费"做 I/O
startMdmRawRead()         // 异步：读取 MDM 策略设置（plutil/reg query 子进程）
startKeychainPrefetch()   // 异步：并行读取两个 keychain 条目

// --- 下面是 200+ 行的 import 语句 ---
import { QueryEngine } from './QueryEngine.js'
import { BashTool } from './tools/BashTool/BashTool.tsx'
import { /* ...40+ 更多 imports */ }

// import 解析完成时（~135ms 后），上面的 I/O 大概率已经完成
profileCheckpoint('main_tsx_imports_loaded')
```

**为什么这有效**：
- JS 的 `import` 是同步的（模块解析阻塞主线程）
- 但 I/O 是异步的（OS 在后台执行）
- 在 import 阻塞的 135ms 里，keychain 读取（~65ms）已经在后台完成了
- `await` 时几乎立即返回 → 净节省 ~65ms

### Phase 3：preAction Hook — 等待预取完成

```typescript
// main.tsx — Commander.js 的 preAction hook
program.hook('preAction', async () => {
  profileCheckpoint('preAction_start')

  // 等待 Phase 2 发射的异步任务
  await Promise.all([
    ensureMdmSettingsLoaded(),        // MDM 子进程结果
    ensureKeychainPrefetchCompleted()  // keychain 结果
  ])
  profileCheckpoint('preAction_after_mdm')

  await init()                // 核心初始化
  profileCheckpoint('preAction_after_init')

  initSinks()                 // 分析/日志 sink
  runMigrations()             // 数据迁移

  // Fire & forget — 不阻塞启动
  void loadRemoteManagedSettings()  // 远程策略
  void loadPolicyLimits()           // 策略限制
  profileCheckpoint('preAction_after_remote_settings')
})
```

### Phase 4：首次渲染后 — 延迟预取（非关键）

```typescript
// 首次 UI 渲染完成后才执行（用户已经看到界面）
function startDeferredPrefetches() {
  // 全部 fire & forget，不阻塞用户交互
  void initUser()                      // 用户信息
  void getUserContext()                // 用户上下文
  void prefetchSystemContextIfSafe()   // git status（如果安全）
  void countFilesRoundedRg()           // 文件计数（3s 超时）
  void refreshModelCapabilities()      // 模型能力表
  void initializeAnalyticsGates()      // AB 测试
  void settingsChangeDetector.initialize()
  void skillChangeDetector.initialize()
}
```

**时间线总结**：
```
0ms    → CLI 入口，快速路径检查
1ms    → 发射 MDM + keychain 预取（异步）
2ms    → 开始 import 解析（同步阻塞 ~135ms）
         ↕ 期间 MDM/keychain I/O 在后台完成
137ms  → import 完成，await 预取结果（几乎 0ms）
140ms  → init + migrations
200ms  → 首次 UI 渲染
200ms+ → 延迟预取（不阻塞用户）
```

---

## 二、懒加载模式

### 模式 A：`lazy require()` 打破循环依赖

```typescript
// src/main.tsx — 模块顶层
const getTeammateUtils = () =>
  require('./utils/teammate.js') as typeof import('./utils/teammate.js')

// 使用时才触发模块加载
function someFunction() {
  const { doSomething } = getTeammateUtils()
  doSomething()
}
```

**为什么**：`teammate.js` 引用了 `main.tsx` 的导出，直接 import 会循环依赖。lazy require 延迟到调用时，那时两个模块都已完成初始化。

### 模式 B：延迟 Schema 评估

```typescript
// ✗ 模块加载时立即评估 → 可能触发循环依赖
const schema = z.object({
  tool: otherModule.toolSchema  // otherModule 可能还没加载完
})

// ✓ 首次使用时才评估
const schema = lazySchema(() => z.object({
  tool: otherModule.toolSchema  // 此时 otherModule 已完成初始化
}))

function lazySchema<T>(factory: () => ZodSchema<T>): ZodSchema<T> {
  let cached: ZodSchema<T> | null = null
  return new Proxy({} as ZodSchema<T>, {
    get(_, prop) {
      if (!cached) cached = factory()
      return (cached as any)[prop]
    }
  })
}
```

### 模式 C：工具延迟加载（shouldDefer）

```typescript
// 50 个工具不需要首轮全加载 schema
// 标记 shouldDefer: true → API 只发 { name: "SQLTool", defer_loading: true }
// 模型需要时调用 ToolSearch → 才返回完整 schema
// 效果：首轮 API 请求 token 降低 ~60%
```

---

## 三、编译期死代码消除

```typescript
import { feature } from 'bun:bundle'

// ★ feature() 在构建时被评估为 true/false
// Bun bundler 的 tree-shaker 把 false 分支整个删除
const coordinatorModule = feature('COORDINATOR_MODE')
  ? require('./coordinator/coordinatorMode.js')  // 构建时消除
  : null

// 20+ 个 feature flag 控制不同构建变体：
// COORDINATOR_MODE, KAIROS, TRANSCRIPT_CLASSIFIER,
// BRIDGE_MODE, DAEMON, TEMPLATES, PROACTIVE, ...
```

**不用 Bun 的替代方案**：
```typescript
// webpack DefinePlugin
if (__FEATURE_COORDINATOR__) {  // 构建时替换为 false
  // tree-shaking 删除整个分支
}

// esbuild define
esbuild.build({
  define: { 'process.env.FEATURE_COORDINATOR': 'false' }
})
```

---

## 四、性能测量 — 不测量就不优化

### CC 的 Checkpoint 系统

```typescript
// src/utils/startupProfiler.ts
const SHOULD_PROFILE =
  isEnvTruthy(process.env.CLAUDE_CODE_PROFILE_STARTUP) ||  // 手动开启
  (isAnt || Math.random() < 0.005)                          // 0.5% 采样

export function profileCheckpoint(name: string) {
  if (!SHOULD_PROFILE) return  // 零成本（未采样时）
  perf.mark(name)
  if (DETAILED) memorySnapshots.push(process.memoryUsage())
}
```

### 上报的关键指标

```
import_time:    cli_entry → main_tsx_imports_loaded      // 模块加载耗时
init_time:      init_function_start → init_function_end  // 初始化耗时
settings_time:  eagerLoadSettings_start → end            // 配置加载耗时
total_time:     cli_entry → main_after_run               // 总启动耗时
```

**查询级指标**（第一轮对话）：
```
query_context_loading           // 上下文组装
query_tool_schema_build         // 工具 schema 构建
query_api_request_sent          // API 请求发出
query_first_chunk_received      // TTFT（首 token 时间）
query_first_token_received      // 首个可见 token
```

---

## 五、优化技术 ROI 排序

| 技术 | 典型节省 | 实现复杂度 | 风险 | 建议顺序 |
|------|---------|-----------|------|---------|
| **并行预取** | 50-100ms | 低 | 低 | ★ 第一个做 |
| **快速路径分流** | 100-300ms | 低 | 低 | ★ 第一个做 |
| **延迟预取** | 感知延迟降低 | 低 | 低 | ★ 第一个做 |
| **懒 require** | 10-50ms/模块 | 中 | 需处理时序 | 第二批 |
| **工具/Schema 延迟加载** | token 成本 | 中 | 需搜索机制 | 第二批 |
| **编译期死代码消除** | 包体积减小 | 中 | 需构建工具支持 | 第三批 |
| **早期输入捕获** | UX 改善 | 低 | 低 | 按需 |

---

## 六、实现模板

### 最小版本：并行预取 + 快速路径

```typescript
// ── 1. 快速路径（最先执行，零 import） ──
if (process.argv.includes('--version')) {
  console.log(VERSION)
  process.exit(0)
}

// ── 2. 并行预取（在 import 之前发射） ──
const configPromise = loadConfig()      // 异步，立即发射
const authPromise = checkAuth()         // 异步，立即发射

// ── 3. import（同步阻塞，期间预取在后台完成） ──
import { App } from './app.js'
import { Database } from './database.js'

// ── 4. 等待预取（此时大概率已完成） ──
const [config, auth] = await Promise.all([configPromise, authPromise])

// ── 5. 初始化 ──
const app = new App(config, auth)

// ── 6. 首次渲染后延迟预取 ──
app.onReady(() => {
  void prefetchAnalytics()     // fire & forget
  void prefetchUserPrefs()     // fire & forget
  void warmUpCache()           // fire & forget
})
```

### 进阶：性能 Checkpoint

```typescript
const marks = new Map<string, number>()

function checkpoint(name: string) {
  if (!process.env.PROFILE_STARTUP) return
  marks.set(name, performance.now())
}

function report() {
  if (!process.env.PROFILE_STARTUP) return
  const entries = [...marks.entries()].sort((a, b) => a[1] - b[1])
  const base = entries[0]?.[1] ?? 0
  for (const [name, time] of entries) {
    console.log(`${name}: +${(time - base).toFixed(1)}ms`)
  }
}

// 使用
checkpoint('entry')
// ... imports ...
checkpoint('imports_done')
// ... init ...
checkpoint('init_done')
report()
```

---

## 七、实施步骤

请分析用户的 $ARGUMENTS 中指定的项目，然后：

1. **测量当前启动时间**：在关键步骤间加 checkpoint，找到瓶颈（不测量就不优化）
2. **识别快速路径**：`--version`、`--help` 等不需要完整初始化的命令 → 提前退出
3. **识别可并行的 I/O**：配置读取、认证检查、远程请求 → `Promise.all` 或 import 前发射
4. **识别可延迟的模块**：启动时不需要的模块 → lazy require / dynamic import
5. **识别可消除的死代码**：feature flag 关闭的功能 → 构建时消除
6. **分阶段启动**：首次渲染/首次响应前只做必要工作，非关键预取延迟到之后
7. **设置性能基线**：CI 中跑启动 benchmark，防止回退

**反模式警告**：
- 不要串行执行独立的 I/O — `await loadConfig(); await checkAuth();` → 用 `Promise.all`
- 不要在模块顶层做重 I/O — 放到函数里懒执行
- 不要运行时判断 feature flag — 用编译期消除
- 不要优化不是瓶颈的地方 — 先测量，再优化
- 不要在首次渲染前做非关键工作 — fire & forget 延迟到之后
