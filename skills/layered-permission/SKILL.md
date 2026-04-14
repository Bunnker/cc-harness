---
name: layered-permission
description: "指导如何设计分层权限系统：顺序评估 + 早期返回 + deny 不可覆盖的 fail-safe 决策模型"
user-invocable: true
argument-hint: "<目标项目路径或模块名>"
---

# 分层权限模型 (Layered Permission Model)

## 1. Problem — 工具执行需要权限控制，但不是全允许或全禁止

Agent 每轮迭代都要执行工具（文件写入、Shell 命令、外部 API 调用）。放任一切会导致安全事故；全部禁止则 Agent 无法工作。

真正的问题是：**如何在一次工具调用前，用确定性的顺序评估多层规则，快速得出 allow/deny/ask 决策，同时保证 deny 不可被后续规则覆盖。**

---

## 2. In Claude Code — permissions.ts 评估链关键决策点

> `源码事实` — 逐函数回钉到具体文件和行号。源码验证版 2026-04-03。

CC 有两条路径共享同一套核心逻辑——**顺序评估链 + 早期返回 + 旁路豁免**：

```
hasPermissionsToUseToolInner(tool, input, context)  ← permissions.ts:1158
│
├─ Step 1a: Deny 规则（:1171-1181）
│  └─ getDenyRuleForTool() → 命中 → return deny  ← 不可覆盖
│
├─ Step 1b: Ask 规则（:1184-1206）
│  └─ getAskRuleForTool() → 命中？
│     └─ Bash + 沙箱启用 + autoAllow → 跳过，落入 1c
│     └─ 否则 → return ask
│
├─ Step 1c: 工具自身 checkPermissions（:1214-1223）
│  └─ tool.checkPermissions(input, ctx) → PermissionResult
│  └─ 默认 passthrough（工具未实现时）；异常吞掉保留默认值
│
├─ Step 1d: 工具返回 deny → return deny  ← 不可覆盖
│
├─ Step 1e: 工具需要用户交互 → return ask  ← bypass-immune
│
├─ Step 1f: 内容级 ask 规则（如 "Bash(npm publish:*)"）→ ask  ← bypass-immune
│
├─ Step 1g: 安全检查（.git/ .claude/ .vscode/ shell 配置）→ ask  ← bypass-immune
│
├─ Step 2a: Bypass 模式（:1268-1281）
│  └─ 只有经过 1a~1g 全部关卡幸存的请求 → return allow
│
├─ Step 2b: Allow 规则（:1284-1297）
│  └─ toolAlwaysAllowedRule() → 命中 → return allow
│
└─ Step 3: 默认 → passthrough 转为 ask（最保守兜底）
```

### 关键决策点

**PermissionResult 四种行为**：deny / ask / allow / passthrough。其中 passthrough 是工具表达"我没意见"的方式，最终被转为 ask（兜底）。MCP 远程工具全部返回 passthrough。

**decisionReason 决定 bypass-immune**：
- `type: 'rule'` + `ruleBehavior: 'ask'` → 内容级用户规则，bypass 不可跳过
- `type: 'safetyCheck'` + `classifierApprovable: true` → 分类器可审批
- `type: 'safetyCheck'` + `classifierApprovable: false` → 必须人工审批（Windows 路径攻击）

**规则来源**（8 源，扁平化后按 deny/ask/allow 三组独立评估）：userSettings / projectSettings / localSettings / policySettings / flagSettings / cliArg / command / session。

**匹配算法**（toolMatchesRule, :238-269）：有 ruleContent 的规则跳过整工具匹配（内容级逻辑由工具自身 checkPermissions 处理）→ 精确匹配 toolName → MCP 服务器级通配。

**安全属性推断**（filesystem.ts:620）：危险文件（.gitconfig/.bashrc 等）和危险目录（.git/.vscode/.claude）硬编码不可配置。Windows 7 类路径攻击（NTFS ADS / 8.3短名 / 长路径前缀 / 尾部点空格 / DOS设备名 / 三连点 / UNC）全部 classifierApprovable=false。

**拒绝追踪**（denialTracking.ts, 45 行）：双阈值断路器——连续 ≥3 次 或 累计 ≥20 次拒绝 → 降级为人工审批。成功只重置连续计数，不重置累计——信任只增不减地消耗。

**Hook 集成**（仅 headless 模式，:930-952）：Hook 不是权限之后的"第二道关"，而是 headless 下替代用户交互的决策入口。Settings deny 早期返回在前，hook 永远不会被执行。

---

## 3. Transferable Pattern — 顺序评估链 + deny 优先早期返回

> `抽象模式` — 框架无关的可迁移设计。

### 核心模式

```
权限请求进入
  → Layer 1: Deny 规则 → 命中立即返回（不可覆盖）
  → Layer 2: Ask 规则 → 命中返回（bypass-immune 标记）
  → Layer 3: 操作自身安全评估 → deny 不可覆盖 / ask+bypass-immune 不可跳过
  → Layer 4: Bypass 模式检查 → 只有全部关卡幸存者才能被 bypass
  → Layer 5: Allow 规则
  → Layer 6: 默认 → ask（最保守兜底）
```

### 关键设计原则

1. **顺序评估 + 早期返回，不是投票合并**。deny 命中后 allow 规则根本不被评估。这消除了规则冲突问题。

2. **deny 不可覆盖**。无论后续规则、bypass 模式、用户确认——deny 就是 deny。这是安全的硬性保证。

3. **bypass-immune 屏障**。某些 ask 决策标记为不可被 bypass 跳过。用户说"允许一切"，写 .git/ 还是要确认。

4. **passthrough 让工具说"我没意见"**。外部工具不知道宿主安全策略，只能说 passthrough 交给全局规则层决定。比强制外部工具实现 allow/deny 好得多。

5. **规则按类型分组，不按插入顺序**。deny/ask/allow 三组独立评估，deny 组永远先于 allow 组。消除顺序依赖 bug。

6. **双阈值断路器**。连续阈值检测短期攻击模式，累计阈值检测长期饱和。成功只重置连续计数——信任单调消耗。

7. **每个决策带 reason + source**。"为什么这个操作被拒绝了"是最常见的调试问题，从第一天就记录。

---

## 4. Minimal Portable Version — Python ~60 行

> `最小版` — 不依赖框架，接口对齐共享契约。

```python
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Any

class Behavior(Enum):
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"

@dataclass
class PermissionResult:
    behavior: Behavior
    reason: str
    source: str = ""
    bypass_immune: bool = False

@dataclass
class DenialState:
    consecutive: int = 0
    total: int = 0

    def record_denial(self) -> "DenialState":
        return DenialState(self.consecutive + 1, self.total + 1)

    def record_success(self) -> "DenialState":
        return DenialState(0, self.total) if self.consecutive > 0 else self

    def should_fallback(self, max_consecutive=3, max_total=20) -> bool:
        return self.consecutive >= max_consecutive or self.total >= max_total

class PermissionChecker:
    def __init__(self, deny_rules=None, ask_rules=None, allow_rules=None):
        self.deny_rules = deny_rules or []
        self.ask_rules = ask_rules or []
        self.allow_rules = allow_rules or []
        self.denial_state = DenialState()

    def check(self, tool: str, input: Any, context: dict) -> PermissionResult:
        """permission.check(tool, input, context) -> PermissionResult"""
        # Layer 1: Deny rules — 命中立即返回，不可覆盖
        for rule in self.deny_rules:
            if rule.matches(tool, input):
                self.denial_state = self.denial_state.record_denial()
                return PermissionResult(Behavior.DENY, rule.reason, "deny-rule")

        # Layer 2: Ask rules — bypass-immune
        for rule in self.ask_rules:
            if rule.matches(tool, input):
                return PermissionResult(Behavior.ASK, rule.reason, "ask-rule",
                                        bypass_immune=True)

        # Layer 3: 操作自身安全评估（工具可返回 deny/ask/allow/None）
        tool_result = self._check_tool_permissions(tool, input, context)
        if tool_result:
            if tool_result.behavior == Behavior.DENY:
                return tool_result
            if tool_result.behavior == Behavior.ASK and tool_result.bypass_immune:
                return tool_result

        # Layer 4: Bypass 模式 — 只有经过以上关卡幸存的请求
        if context.get("bypass_mode"):
            return PermissionResult(Behavior.ALLOW, "bypass", "bypass")

        # Layer 5: Allow rules
        for rule in self.allow_rules:
            if rule.matches(tool, input):
                self.denial_state = self.denial_state.record_success()
                return PermissionResult(Behavior.ALLOW, rule.reason, "allow-rule")

        # Layer 6: 默认 ask（最保守兜底）
        return PermissionResult(Behavior.ASK, "no matching rule", "default")

    def _check_tool_permissions(self, tool, input, context) -> Optional[PermissionResult]:
        """扩展点：各工具实现自己的安全检查"""
        return None
```

不需要：分类器 API、macOS Keychain、MCP 服务器级通配、Windows 路径攻击检测、Hook 集成。

---

## 5. Do Not Cargo-Cult

> `不要照抄` — 以下是 CC 特有实现选择，照搬会增加复杂度但未必带来收益。

1. **不要照搬 CC 的分类器 API 审批路径**。CC 在 auto mode 下用 Anthropic 分类器 API 自动判断 ask 请求是否安全。这依赖 Anthropic 的在线服务。你的项目用简单的规则匹配 + 人工确认即可。

2. **不要照搬 CC 的 macOS Keychain 凭证存储**。CC 用 Keychain 存 OAuth token，这是平台特有的。你的项目用环境变量或加密配置文件即可。

3. **不要照搬 CC 的 Windows 7 类路径攻击检测**。NTFS ADS、8.3 短名称、DOS 设备名等攻击面是 Windows 文件系统特有的。除非你的 Agent 在 Windows 上直接操作文件系统，否则不需要。

4. **不要照搬 CC 的 8 种规则来源合并**。CC 有 userSettings / projectSettings / localSettings / policySettings / flagSettings / cliArg / command / session 八种来源。你的项目可能只需要 2-3 种（如项目配置 + 运行时动态规则）。

5. **不要照搬 CC 的 bypass-immune 四层细分**。CC 区分工具 deny(1d)、用户交互(1e)、内容级 ask(1f)、安全检查(1g) 四种 bypass-immune。你的项目一个 `bypass_immune: bool` 标记足够。

---

## 6. Adaptation Matrix

> `迁移建议` — 不同项目形态下的裁剪方案。

| 项目类型 | 建议保留 | 建议简化或删掉 | 注意事项 |
|----------|---------|---------------|---------|
| **单进程 CLI Agent** | deny/allow 两层 + 默认 ask | bypass 模式、拒绝追踪、内容级匹配 | 工具少，规则简单 |
| **对话式 Agent（类 CC）** | 完整 6 层 + 拒绝追踪 | 可简化规则来源数量 | 最接近 CC 原始设计 |
| **API 服务** | deny/allow 两层 | ask（无人交互）、bypass、passthrough | 用 HTTP 403/200 替代 deny/allow |
| **多 Agent 编排** | 每个子 Agent 独立评估链 | 跨 Agent 共享规则 | 子 Agent 权限应 ≤ 父 Agent |
| **企业部署** | 完整 + 策略来源 + 审计日志 | — | deny 规则应支持远程推送 |

### Zero Magic 实战案例

**CC 原始设计**：9 步工具级权限评估链，单进程内顺序评估。

**Zero Magic 适配**：三层架构下权限分属两个服务——
- **Gateway 层**：RBAC 角色权限（哪些用户可以调用哪些 Agent），对应 CC 的 deny/allow 规则层
- **Runtime 层**：工具白名单（每个 Agent 实例只能使用哪些工具），对应 CC 的工具 checkPermissions 层
- Gateway RBAC 和 Runtime 工具白名单**分别评估、分别 deny**——不合并为单一评估链，因为它们跑在不同进程
- deny 优先 + 早期返回的原则不变，只是执行位置从"单进程 9 步"变为"Gateway 3 步 + Runtime 3 步"

---

## 7. Implementation Steps

请分析用户的 $ARGUMENTS 中指定的项目，然后：

1. **盘点操作类型** — 找出所有需要权限控制的操作（写入、删除、外部调用、敏感路径等）
2. **定义决策类型** — 至少 deny/allow 两种；有人工审批流程加 ask；有外部工具加 passthrough
3. **设计规则格式** — 支持整个操作匹配 + 内容级匹配（如 `Bash(rm:*)`）；按 deny/ask/allow 三组分类
4. **实现顺序评估链** — deny → ask(bypass-immune) → 工具自身检查 → bypass → allow → 默认 ask
5. **加入安全属性推断** — 硬编码保护敏感路径/资源，不依赖用户配置规则
6. **加入拒绝追踪** — 双阈值断路器（连续 N 次 + 累计 M 次），超限后降级为人工审批
7. **每个决策带 reason + source** — 从第一天就做，否则事后补成本极高

**反模式警告**：
- 不要用"并发评估 + 合并"——用顺序评估 + 早期返回
- 不要让 bypass 模式覆盖一切——敏感操作标记 bypass_immune
- 不要把安全路径保护放在可配置规则里——硬编码
- 不要忘了 passthrough——外部工具不该被强制做安全决策

---

## 8. Source Anchors

> CC 源码锚点，用于追溯和深入阅读。

| 关注点 | 文件 | 关键符号 | 行号参考 |
|--------|------|---------|---------|
| 完整评估链 | `permissions.ts` | `hasPermissionsToUseToolInner()` | :1158 |
| 规则评估子集 | `permissions.ts` | `checkRuleBasedPermissions()` | :1071 |
| 规则匹配算法 | `permissions.ts` | `toolMatchesRule()` | :238 |
| Deny 规则查找 | `permissions.ts` | `getDenyRuleForTool()` | :1171 |
| Bypass 模式检查 | `permissions.ts` | bypass mode block | :1268 |
| Allow 规则查找 | `permissions.ts` | `toolAlwaysAllowedRule()` | :1284 |
| 拒绝追踪 | `denialTracking.ts` | `DenialTrackingState`, `DENIAL_LIMITS` | 全文 45 行 |
| 降级处理 | `permissions.ts` | `handleDenialLimitExceeded()` | :995 |
| 安全属性推断 | `filesystem.ts` | `checkPathSafetyForAutoEdit()` | :620 |
| 危险文件列表 | `filesystem.ts` | `DANGEROUS_FILES` | :57 |
| 危险目录列表 | `filesystem.ts` | `DANGEROUS_DIRECTORIES` | :74 |
| Windows 路径攻击 | `filesystem.ts` | Windows-specific checks | :537 |
| Hook 集成 | `permissions.ts` | PreToolUse hooks (headless) | :930 |
| 完整路径入口 | `permissions.ts` | `hasPermissionsToUseTool()` | :473 |
