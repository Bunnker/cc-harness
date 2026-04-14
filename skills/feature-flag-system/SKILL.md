---
name: feature-flag-system
description: "指导如何设计 Harness 特性门控：构建期 DCE + 运行期缓存评估 + 渐进发布 + 属性定向"
user-invocable: true
argument-hint: "<目标项目路径或模块名>"
---

# Harness 特性门控 (Feature Flag System)

> 参考实现：Claude Code `src/services/analytics/growthbook.ts` + `bun:bundle` feature()
> — 构建时死代码消除 + 运行时 GrowthBook 评估 + 会话级缓存 + 属性定向

## 核心思想

**不重新部署就能调整 Agent 行为。** CC 用两层特性门控：构建期 `feature()` 让 bundler 消除整个模块（零运行时成本），运行期 GrowthBook 让后端按百分比/属性渐进开放功能。

---

## 一、构建期 — 死代码消除

```typescript
import { feature } from 'bun:bundle'

// 构建时 feature('COORDINATOR_MODE') 被替换为 true/false
// Bun bundler 的 tree-shaker 把 false 分支整个删除
const coordinatorModule = feature('COORDINATOR_MODE')
  ? require('./coordinator/coordinatorMode.js')  // 保留
  : null                                          // 消除

// 20+ 个构建期 flag：
// COORDINATOR_MODE, KAIROS, BRIDGE_MODE, DAEMON,
// TRANSCRIPT_CLASSIFIER, TEMPLATES, PROACTIVE, ...
```

**效果**：外部构建不包含内部功能（KAIROS、COORDINATOR）的任何代码——不是"关了但代码还在"，是"代码物理删除"。

---

## 二、运行期 — GrowthBook 缓存评估

```typescript
// 运行时 flag 评估
getFeatureValue_CACHED_MAY_BE_STALE('tengu_streaming_tool_execution2')
  → 返回会话启动时缓存的值
  → 不会 mid-session 变化（防止 cache 失效）

checkGate_CACHED_OR_BLOCKING('tengu_passport_quail')
  → 缓存有值 → 返回缓存
  → 缓存无值 → 阻塞等待 GrowthBook 远程获取
```

### 为什么用缓存而非实时评估

- 实时评估 → mid-session feature flip → prompt cache key 变化 → 50-70K token 重新计费
- 会话级缓存 → 整个会话行为一致 → cache 命中率最高

### 定向属性（发给 GrowthBook 的上下文）

```typescript
attributes = {
  sessionId,               // 会话级随机化
  deviceID,                // 设备级持久化
  platform,                // win32/darwin/linux
  organizationUUID,        // 组织
  accountUUID,             // 账号
  subscriptionType,        // free/pro/max/team/enterprise
  rateLimitTier,           // 限流层级
  appVersion,              // 应用版本
  // GitHub Actions 元数据（CI 场景）
}
```

---

## 三、使用场景分类

| 场景 | 用构建期 flag | 用运行期 flag |
|------|-------------|-------------|
| 子系统开关（KAIROS、DAEMON） | ✓ | |
| A/B 测试（压缩策略对比） | | ✓ |
| 渐进发布（10% → 50% → 100%） | | ✓ |
| 内部 vs 外部构建差异 | ✓ | |
| 按订阅层级开放功能 | | ✓ |
| 按组织/账号定向 | | ✓ |

---

## 四、实现模板

```python
import os, json, hashlib

class FeatureFlagSystem:
    def __init__(self, remote_url: str = None):
        self._cache: dict[str, any] = {}
        self._remote_url = remote_url
        self._attributes: dict = {}

    def set_attributes(self, **kwargs):
        """设置定向属性（会话开始时）"""
        self._attributes = kwargs

    async def initialize(self):
        """从远程加载 flag 定义，缓存到会话级"""
        if self._remote_url:
            flags = await fetch_flags(self._remote_url, self._attributes)
            self._cache = flags

    def is_enabled(self, flag_name: str, default: bool = False) -> bool:
        """会话级缓存评估"""
        return self._cache.get(flag_name, default)

    def get_value(self, flag_name: str, default=None):
        """获取 flag 的值（不只是 bool）"""
        return self._cache.get(flag_name, default)

# 构建期 flag（Python 没有 bun:bundle，用环境变量 + 条件 import）
def build_feature(name: str) -> bool:
    """构建期 flag — 在 CI/CD 中设置环境变量"""
    return os.environ.get(f'FEATURE_{name}', '').lower() == 'true'

# 使用
if build_feature('COORDINATOR_MODE'):
    from .coordinator import CoordinatorMode  # 只在启用时 import
```

---

## 五、实施步骤

1. **区分构建期 vs 运行期**：子系统开关用构建期（零运行时成本），渐进发布用运行期
2. **会话级缓存**：flag 值在会话开始时锁定，避免 mid-session 行为漂移
3. **定向属性**：至少支持按用户/组织/版本定向
4. **默认值**：flag 获取失败时有安全的默认值
5. **曝光日志**：记录哪些 flag 被评估了（A/B 测试分析用）
