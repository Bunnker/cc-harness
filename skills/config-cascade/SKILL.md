---
name: config-cascade
description: "指导如何设计 Harness 配置级联系统：5 源合并（后者覆盖前者）+ Zod 验证 + 热重载 + 源过滤"
user-invocable: true
argument-hint: "<目标项目路径或模块名>"
---

# Harness 配置级联 (Config Cascade)

> 参考实现：Claude Code `src/utils/settings/constants.ts` + `settings.ts` + `changeDetector.ts`
> — 5 源优先级合并 + Zod 按源报错 + chokidar 热重载 + 策略可锁定源

## 核心思想

**Agent 的行为由配置驱动，但配置来自 5 个互相冲突的来源。** CC 用"后者覆盖前者 + 策略层不可覆盖 + 源可被锁定"的级联规则解决冲突，而不是简单的合并。

---

## 一、5 源优先级（源码 constants.ts 原文）

```typescript
// src/utils/settings/constants.ts — 后者覆盖前者
export const SETTING_SOURCES = [
  'userSettings',      // 1. ~/.claude/settings.json（全局用户）
  'projectSettings',   // 2. .claude/settings.json（项目共享，在 git 中）
  'localSettings',     // 3. .claude/local-settings.json（项目本地，gitignored）
  'flagSettings',      // 4. --settings CLI 参数（一次性覆盖）
  'policySettings',    // 5. managed-settings.json / 远程 API（企业策略，最高）
] as const
```

**谁赢**：policySettings > flagSettings > localSettings > projectSettings > userSettings

**关键约束**：
- `policySettings` 和 `flagSettings` **始终启用**，不可被 `--setting-sources` 排除
- `projectSettings` 可以被策略禁用（防止恶意仓库注入配置）
- 可编辑的只有 user / project / local（policy 和 flag 是只读）

---

## 二、设置合并策略

```
每个源独立读取 → 按源顺序合并 → 后者覆盖前者
  ↓
对象级合并（不是深合并）：
  userSettings:    { model: "sonnet", hooks: {...} }
  projectSettings: { hooks: {...} }
  localSettings:   { model: "opus" }
  ↓
  合并结果: { model: "opus", hooks: {...} }
            ← localSettings 的 model 覆盖了 userSettings 的

权限规则合并（特殊）：
  所有源的 allow/deny/ask 规则 **累加** 而非覆盖
  每条规则带 source 标签，权限评估时按规则看到来源
```

---

## 三、Zod 按源验证

```typescript
// 每个源独立验证，报错时告诉用户是哪个文件出错
for (const source of enabledSources) {
  const raw = readSettingsFile(source)
  const result = settingsSchema.safeParse(raw)
  if (!result.success) {
    reportError(source, result.error)
    // 这个源的设置被丢弃，其他源继续
    // 不会因为一个源出错就整个设置系统崩溃
  }
}
```

**设计原则**：一个源出错不影响其他源。用户的 settings.json 格式错了 → 只丢这个源，项目级和策略级正常工作。

---

## 四、热重载 — chokidar 监控 + ConfigChange Hook

```typescript
// src/utils/settings/changeDetector.ts
// chokidar 监控所有 settings 文件路径
// 变更后 1 秒稳定期（debounce），避免保存中间态触发

fileChanged(path) {
  if (isInternalWrite(path)) return  // 自己写的不触发
  await stabilityWait(1000)          // 等 1 秒
  const source = identifySource(path)
  const oldValue = cache[source]
  const newValue = readAndValidate(source)
  if (deepEqual(oldValue, newValue)) return  // 没变

  cache[source] = newValue
  executeConfigChangeHooks(source)  // 触发 ConfigChange Hook
  // → 分析器重新初始化
  // → 事件日志重建
  // → MCP 连接重新评估
}
```

**排除 flagSettings**：CLI 参数不会在会话中变化，而且可能是临时文件（FIFO/socket），监控会挂。

---

## 五、源过滤 — 策略控制哪些源可用

```typescript
// 企业可以通过 --setting-sources 限制用户只能用部分源
// 例：--setting-sources user,local → 禁用 projectSettings

function getEnabledSettingSources(): SettingSource[] {
  const allowed = getAllowedSettingSources()  // 从 bootstrap state 读取
  const result = new Set(allowed)
  result.add('policySettings')   // 策略始终启用
  result.add('flagSettings')     // CLI 参数始终启用
  return Array.from(result)
}
```

**用途**：企业部署时，禁止 `projectSettings` → 恶意仓库无法通过 `.claude/settings.json` 注入配置（如放宽权限、添加 webhook 等）。

---

## 六、实现模板

```python
from pathlib import Path
from dataclasses import dataclass, field
import json

SOURCES_ORDER = ['user', 'project', 'local', 'flag', 'policy']

@dataclass
class ConfigSource:
    name: str
    path: Path | None
    data: dict = field(default_factory=dict)
    readonly: bool = False

class ConfigCascade:
    def __init__(self, sources: list[ConfigSource]):
        self.sources = sorted(sources, key=lambda s: SOURCES_ORDER.index(s.name))
        self._merged: dict = {}

    def load(self, enabled_sources: set[str] | None = None):
        """加载所有源，按优先级合并"""
        self._merged = {}
        for source in self.sources:
            if enabled_sources and source.name not in enabled_sources:
                if source.name not in ('policy', 'flag'):  # 这两个始终启用
                    continue
            if source.path and source.path.exists():
                try:
                    raw = json.loads(source.path.read_text())
                    validated = self._validate(raw, source.name)
                    source.data = validated
                    self._merged = {**self._merged, **validated}  # 后者覆盖前者
                except Exception as e:
                    print(f"Warning: {source.name} ({source.path}) invalid: {e}")
                    # 跳过此源，不影响其他

    def get(self, key: str, default=None):
        return self._merged.get(key, default)

    def get_with_source(self, key: str) -> tuple[any, str]:
        """返回 (值, 来源名称) — 调试用"""
        for source in reversed(self.sources):  # 反向（高优先级先查）
            if key in source.data:
                return source.data[key], source.name
        return None, 'default'

    def _validate(self, raw: dict, source_name: str) -> dict:
        """按源独立验证，一个源出错不影响其他"""
        # 实际项目用 Pydantic / JSON Schema 验证
        return raw

# 使用
config = ConfigCascade([
    ConfigSource('user', Path.home() / '.myagent/settings.json'),
    ConfigSource('project', Path('.myagent/settings.json')),
    ConfigSource('local', Path('.myagent/local-settings.json')),
    ConfigSource('flag', None, readonly=True),   # CLI 参数直接注入
    ConfigSource('policy', Path('/etc/myagent/managed.json'), readonly=True),
])
config.load(enabled_sources={'user', 'local', 'policy', 'flag'})
```

---

## 七、实施步骤

请分析用户的 $ARGUMENTS 中指定的项目，然后：

1. **确定配置来源**：至少 user + project 两级，有企业需求加 policy
2. **定义优先级**：后者覆盖前者，policy 最高且不可关闭
3. **按源独立验证**：一个源出错不崩溃，跳过继续
4. **权限规则累加**：deny/allow 规则不是覆盖，是合并
5. **热重载**：文件监控 + debounce + ConfigChange 通知
6. **源过滤**：允许管理员禁用 projectSettings（防恶意仓库注入）
7. **带源查询**：`get_with_source()` 方便调试"这个值从哪来的"

**反模式警告**：
- 不要深合并配置对象 — CC 用浅合并（后者完整覆盖前者的同名字段）
- 不要让 projectSettings 能覆盖 policy — 安全边界
- 不要一个源出错就全部失败 — 隔离验证错误
- 不要监控 CLI 参数文件 — 可能是 FIFO/socket，会挂
