---
name: prompt-cache-economics
description: "指导如何设计 Agent 的 Prompt Cache 成本工程：cache key 稳定性 + 选择性延迟 + 手术级变更 + 经济调度"
user-invocable: false
argument-hint: "<目标项目路径或模块名>"
---

# Prompt Cache 成本工程 (Prompt Cache Economics)

> 贯穿 Claude Code 全局的成本设计主线，涉及 context-engineering / agent-tool-budget / multi-agent-design / model-routing / feature-flag-system 等 5+ 个系统的协同

## 核心思想

**CC 的大量设计决策看似是功能设计，本质上都在解决同一个经济学问题：怎么让 system prompt（~20K token）在多轮对话中只付一次钱？**

一旦 prompt cache key 变了（工具顺序变了、feature flag 翻了、MCP 连接断了、thinking config 改了），20K token 就要重新付 cache_creation 费用。CC 的排序、锁定、CacheSafeParams、session-level latching 全部服务于同一个目标：**cache prefix 稳定性**。

---

## 一、成本模型

```
API 调用的 token 成本 = cache_creation + cache_read + output

cache_creation: 首次发送 system prompt（~20K token）→ 较贵
cache_read:     命中缓存的 system prompt → 很便宜（~10% 创建价）
output:         模型输出 → 固定价格

所以：
  10 轮对话 × cache hit = 1 × creation + 10 × read ≈ 2× 单次成本
  10 轮对话 × cache miss = 10 × creation            ≈ 10× 单次成本
                                                       ← 5 倍差距
```

**每次 cache miss 的代价**：~20K token 的 cache_creation 费用重新支付。CC 的 prompt cache break detection 估算每次 miss 约 40K token 的额外成本。

---

## 二、4 层成本优化架构

### Layer 1：Cache Key 稳定性 — "不要让 key 变"

CC 的 cache key = `hash(system_prompt + tools + model + messages_prefix + thinking_config)`

**所有可变参数在会话开始时锁定（session-level latching）：**

```typescript
// src/services/api/claude.ts:403-406 — 注释原文
// Latch eligibility in bootstrap state for session stability — prevents
// mid-session overage flips from changing the cache_control TTL, which
// would bust the server-side prompt cache (~20K tokens per flip).

let userEligible = getPromptCache1hEligible()
if (userEligible === null) {
  userEligible = isEligible()           // 首次评估
  setPromptCache1hEligible(userEligible) // 锁定！整个会话不变
}
```

**锁定的参数**：
| 参数 | 为什么锁 | 不锁的后果 |
|------|---------|-----------|
| TTL 资格 | overage 状态翻转 → TTL 从 1h 变 ephemeral | cache key 变 → ~20K token miss |
| GrowthBook allowlist | 后端更新 flag → 不同 query source 得到不同 TTL | 混合 TTL → cache 碎片化 |
| Cache editing beta | mid-session 启用 → 请求头变 | beta header 进 cache key |
| Auto-mode beta | mid-session 切换 → 请求头变 | 同上 |
| Fast-mode header | 切换 fast/normal → 请求头变 | 同上 |

**CC 还自验证锁定有效**（[promptCacheBreakDetection.ts](src/services/api/promptCacheBreakDetection.ts)）：
```typescript
// Should NOT break cache anymore (sticky-on latched in claude.ts). Tracked to verify the fix.
cachedMCEnabled: boolean
isUsingOverage: boolean
autoModeActive: boolean
```

### Layer 2：选择性延迟 — "不需要的不发"

| 手段 | 节省 | 来源 |
|------|------|------|
| 工具 schema 延迟（shouldDefer） | 首轮 ~60% 工具 token | agent-tool-budget |
| Agent 列表从工具描述移到附件消息 | **10.2% fleet cache_creation** | agent-tool-budget |
| Explore/Plan 跳过 CLAUDE.md | **5-15 Gtok/周** | multi-agent-design |
| Explore/Plan 跳过 gitStatus | **1-3 Gtok/周** | multi-agent-design |
| Skill 列表 1% 预算限制 | 防止无限增长 | agent-tool-budget |

**Agent 列表案例的成本数据**（源码注释原文）：

Agent 列表原本嵌入在 AgentTool 的 description 中。MCP 连接/断开、插件重载、权限模式切换都会改变列表 → tool schema 变化 → cache bust。

移到附件消息后，tool schema 恒定 → cache 不再因 Agent 列表变化而失效。实测节省 **10.2% 的全舰队 cache_creation token**。

### Layer 3：手术级变更 — "变了也别让 cache 知道"

**cache_edits 删除**（Cached Microcompact）：
```
旧工具结果需要清除 → 直接改内容 → cache miss
                    ↓
用 cache_edits 在服务端手术删除 → cache key 不变 → cache hit 保持
```

**tool schema 基础层缓存**：
```typescript
// 每个工具的 base schema（name + description + input_schema）会话级缓存
// 每次 API 调用只叠加 per-request 变量（defer_loading, cache_control）
// 这样即使 GrowthBook flag 翻了（改变描述文本），base schema 不变 → cache 稳定

const base = cache.get(cacheKey) ?? computeAndCache(tool)
return { ...base, ...(deferLoading && { defer_loading: true }), ...cacheControl }
```

### Layer 4：经济调度 — "花在刀刃上"

**CacheSafeParams 共享**（Fork 不重复付费）：
```
主 Agent 首轮：支付 ~20K cache_creation
  ↓
Fork 子 Agent：复用主 Agent 的 cache → 只付 cache_read
  条件：systemPrompt + tools + model + thinking_config 字节级相同
  ↓
Post-turn Fork（记忆提取、prompt suggestion）：
  复用 stopHooks 保存的 CacheSafeParams → cache_read
```

**成本意识的模型路由**：
```
只读搜索 → Haiku（最便宜）
计划阶段 → Opus（最强，但值得——计划质量决定执行效率）
执行阶段 → Sonnet（平衡）
工具摘要 → Haiku（1 秒内完成的轻量总结）
```

---

## 三、Cache Break 检测 — 自监控

CC 会主动检测 cache 是否被意外打破：

```typescript
// 两阶段检测
Phase 1（API 调用前）: 快照当前 system/tools/model/cacheControl 的 hash
Phase 2（API 响应后）: 对比 hash → 变了？→ 记录 cache break 事件

// 检测维度
├─ system prompt 内容变化
├─ 工具 schema 变化（逐工具 hash）
├─ model 切换
├─ cache_control scope/TTL 翻转
├─ beta header 变化
└─ 最低阈值：2K token drop（忽略正常波动）
```

---

## 四、System Prompt 三段式分割

```
策略 A（有 MCP 工具时）：
  Block 1: Attribution header    → cacheScope: null（不缓存）
  Block 2: System prompt prefix  → cacheScope: 'org'（组织级缓存）
  Block 3: 其余内容             → cacheScope: 'org'

策略 B（1P + 有 dynamic boundary 时）：
  Block 1: Attribution header    → null
  Block 2: Prefix                → null
  Block 3: 静态内容（boundary 前）→ cacheScope: 'global'（跨组织，24h）
  Block 4: 动态内容（boundary 后）→ null

策略 C（默认）：
  Block 1: Attribution header    → null
  Block 2: Prefix + 其余        → cacheScope: 'org'
```

**为什么 MCP 工具时不用 global cache**：MCP 工具频繁连接/断开 → 工具列表变 → 如果 system prompt 用 global cache → 工具变化导致 global cache 失效 → 影响其他组织的 cache hit。降级到 org-level 避免级联影响。

---

## 五、实现模板

```python
class CacheEconomics:
    """贯穿性成本优化管理器"""

    def __init__(self):
        self._session_params = {}  # 会话级锁定
        self._schema_cache = {}    # 工具 schema 缓存
        self._last_hash = None     # cache break 检测

    # ─── Layer 1: Session Latching ───
    def latch(self, key: str, compute_fn):
        """首次计算后锁定，整个会话不变"""
        if key not in self._session_params:
            self._session_params[key] = compute_fn()
        return self._session_params[key]

    # ─── Layer 2: Selective Deferral ───
    def should_include_tool_schema(self, tool, is_first_turn: bool) -> bool:
        if tool.always_load: return True
        if tool.is_remote: return False  # 远程工具默认延迟
        if not is_first_turn: return True  # 后续轮次已发现的工具发送完整 schema
        return not tool.should_defer

    # ─── Layer 3: Schema Stability ───
    def get_stable_schema(self, tool) -> dict:
        """基础 schema 会话级缓存，per-request 变量单独叠加"""
        key = f"{tool.name}:{hash(tool.input_schema)}" if tool.is_remote else tool.name
        if key not in self._schema_cache:
            self._schema_cache[key] = {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
            }
        return self._schema_cache[key]

    # ─── Layer 4: Break Detection ───
    def check_cache_break(self, current_system, current_tools, current_model):
        current_hash = hash(f"{current_system}|{sorted(t.name for t in current_tools)}|{current_model}")
        if self._last_hash and current_hash != self._last_hash:
            log_event("cache_break_detected", {
                "system_changed": hash(current_system) != self._last_system_hash,
                "tools_changed": True,  # 逐工具对比
            })
        self._last_hash = current_hash
```

---

## 六、实施步骤

1. **测量当前 cache hit rate**：如果不知道有多少 miss，就不知道优化价值
2. **锁定可变参数**：feature flag、认证状态、beta header 在会话开始时锁定
3. **工具 schema 会话级缓存**：base schema 不变，per-request 叠加
4. **排序保证确定性**：工具列表、Agent 列表按名字排序
5. **动态内容移到附件**：不要把会变的东西放在工具描述里
6. **实现 cache break 检测**：每次 API 调用后对比 hash
7. **Fork 共享 CacheSafeParams**：子 Agent 复用父的 cache

**反模式警告**：
- 不要 mid-session 切换 feature flag — 锁定到会话级
- 不要把动态列表嵌入工具描述 — 移到附件消息
- 不要忽略工具排序 — MCP 工具异步加载，顺序不确定
- 不要让 Fork 改 thinking config — 破坏 cache prefix
