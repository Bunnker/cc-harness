---
name: config-cascade
description: "指导如何设计多源配置级联系统：有序来源、按源校验、浅合并与规则特例、可选热重载、策略级不可被覆盖"
user-invocable: true
argument-hint: "<目标项目路径或模块名>"
---

# 配置级联 (Config Cascade)

## 1. Problem — 多源配置不是简单 merge

Agent Runtime 的配置通常同时来自：

- 用户全局配置
- 项目共享配置
- 本地私有配置
- CLI / API 临时覆盖
- 企业或平台策略

常见错误是把这些来源当成一个 JSON 做深合并。这样会导致：

- 优先级不明确
- 某个源校验失败时整套系统崩溃
- 策略层被低优先级配置绕过
- 热重载和溯源调试都做不清楚

通用问题是：**如何设计一个多源配置系统，让来源顺序、合并规则、校验边界和策略优先级都可解释、可恢复、可审计。**

---

## 2. In Claude Code — 源码事实（精简版）

> `源码事实` — CC 的具体实现是一个参考，不是唯一答案。

### CC 有 5 个配置来源

优先级从低到高大致是：

1. user settings
2. project settings
3. local settings
4. flag settings
5. policy / managed settings

高优先级覆盖低优先级，其中：

- `policy` 和 `flag` 不能被普通来源禁用
- `project` 可以被策略层禁止
- 真正可编辑的通常只有 user / project / local

### 合并不是一刀切

CC 的大原则是：

- 普通对象字段：浅合并，后者覆盖前者
- 权限规则类字段：按规则累加，而不是整个覆盖

这背后的原因是：

- 普通对象深合并容易制造不可预测行为
- 安全规则经常需要多来源叠加

### 校验是按源执行的

每个来源分别读取、分别验证、分别报错。一个源坏掉时：

- 丢弃这个源
- 保留其他已通过校验的来源
- 向用户指出是哪个文件/来源有问题

### 热重载不是“文件一变就全重启”

CC 里有稳定期、防内部写回触发、source-level change detection 等机制。重点不是具体 watcher 库，而是：

- 只重载变更来源
- 只有值真的变化才触发后续动作
- 配置变化以事件形式通知下游

### 来源过滤是安全边界的一部分

企业/平台可以决定某些来源是否启用，例如禁用项目级配置，避免恶意仓库注入权限或 hook。

---

## 3. Transferable Pattern — Source Registry + Merge Policy + Source Validation

### 核心模式

把配置系统拆成三层：

1. `source registry`
   定义有哪些来源、顺序、是否只读、是否必须启用。
2. `validation per source`
   每个来源单独解析和校验，失败时只污染自己。
3. `merge policy`
   对不同字段族使用不同合并规则，而不是全局深合并。

### 推荐数据模型

```text
ConfigSource:
  id
  loader()
  validator()
  readonly
  mandatory

ConfigSnapshot:
  merged
  by_source
  errors
  provenance
```

### 关键原则

1. 先保留 `by_source`，再生成 `merged`，否则调试“这个值从哪来”会很痛苦。
2. 普通配置默认浅合并，只有明确声明的字段走累加或自定义策略。
3. 策略级来源要么强制启用，要么拥有最终裁决权，不能被低优先级覆盖。
4. 校验失败应该局部隔离，而不是让整个 runtime 起不来。
5. 热重载应该围绕“来源变化事件”设计，而不是 watcher 细节。

---

## 4. Minimal Portable Version — Python 最小实现

```python
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
import json


@dataclass
class ConfigSource:
    name: str
    loader: Callable[[], dict[str, Any]]
    validator: Callable[[dict[str, Any]], dict[str, Any]]
    readonly: bool = False
    mandatory: bool = False


class ConfigCascade:
    def __init__(self, sources: list[ConfigSource], merge_policies: dict[str, str] | None = None):
        self.sources = sources
        self.merge_policies = merge_policies or {}
        self.by_source: dict[str, dict[str, Any]] = {}
        self.errors: dict[str, str] = {}
        self.merged: dict[str, Any] = {}

    def reload(self, enabled_sources: set[str] | None = None) -> None:
        self.by_source = {}
        self.errors = {}
        self.merged = {}

        for source in self.sources:
            if enabled_sources is not None and source.name not in enabled_sources and not source.mandatory:
                continue

            try:
                raw = source.loader()
                validated = source.validator(raw)
                self.by_source[source.name] = validated
                self.merged = self._merge(self.merged, validated)
            except Exception as exc:
                self.errors[source.name] = str(exc)

    def _merge(self, base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
        merged = dict(base)
        for key, value in incoming.items():
            policy = self.merge_policies.get(key, "replace")
            if policy == "append_rules":
                merged[key] = [*(merged.get(key, [])), *value]
            else:
                merged[key] = value
        return merged

    def get_with_source(self, key: str) -> tuple[Any, str | None]:
        for source in reversed(self.sources):
            data = self.by_source.get(source.name, {})
            if key in data:
                return data[key], source.name
        return None, None


def json_loader(path: Path) -> Callable[[], dict[str, Any]]:
    def _load() -> dict[str, Any]:
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))
    return _load
```

这个最小版表达的是：

- 来源顺序显式
- 校验按源进行
- 合并策略按字段族定制
- 可追踪值来源

---

## 5. Do Not Cargo-Cult

不要照抄这些 CC 细节：

- 精确的 5 个来源命名
- `chokidar`、`Zod`、`changeDetector.ts` 的具体实现
- 平台特定的 managed 路径
- CC 专用的 hook 名称和初始化时机

真正该迁移的是：

- 来源顺序是显式数据，而不是散落在代码里的 if/else
- 校验错误局部隔离
- 合并策略是字段族驱动，而不是全局深合并
- 策略级来源有真正的优先权

---

## 6. Adaptation Matrix

| 场景 | 来源建议 | 特别注意 |
|------|----------|----------|
| 个人 CLI 工具 | user + project + flag | 先把溯源和局部报错做清楚 |
| 团队仓库 | user + project + local + flag | local 不应污染共享配置 |
| 企业托管 | user + project + local + flag + policy | `policy` 必须可强制启用或禁用下游来源 |
| SaaS 多租户 | org + workspace + user + request override | 合并规则和审计日志必须可追踪 |

---

## 7. Implementation Steps

请分析用户的 `$ARGUMENTS`，然后：

1. 枚举配置来源并定义优先级，不要先写 merge 函数。
2. 为每个来源定义独立 loader 和 validator。
3. 定义字段族合并策略：默认替换，规则列表等少数字段走累加。
4. 实现 `by_source`、`merged`、`errors`、`provenance` 四类输出。
5. 明确哪些来源是 mandatory，哪些来源可以被策略禁用。
6. 如果要做热重载，先产出 source change event，再决定下游谁订阅。
7. 用回归测试覆盖“单源报错不拖垮整体”“policy 覆盖 project”“规则字段累加”。

验收标准：

- 任意配置值都能解释来源
- 一个来源损坏不会拖垮整个配置系统
- 低优先级来源无法绕过策略级配置
- 字段合并规则对调用方是可预测的
