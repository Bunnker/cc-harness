---
name: plan-mode
description: "指导如何设计 Agent 计划模式：思考与执行阶段分离，用户审批后才执行，支持团队审批工作流"
user-invocable: false
argument-hint: "<目标项目路径或模块名>"
---

# Agent 计划模式 (Plan Mode)

> 参考实现：Claude Code `src/commands/plan/` + `src/tools/ExitPlanModeTool/`
> — 权限模式切换 + 工具集收缩 + 审批工作流 + 模型路由联动

## 核心思想

**高风险操作不应该"想到就做"——先计划、再审批、最后执行。** Plan Mode 把 Agent 的循环分成两个阶段：计划阶段只能读和分析，执行阶段才能改代码。中间由人类审批。

---

## 一、Plan Mode 的状态切换

```
/plan 命令
  ↓
当前模式 ≠ plan？
  ├─ YES → handlePlanModeTransition(currentMode, 'plan')
  │  ├─ 记住原模式（prePlanMode = currentMode）
  │  ├─ prepareContextForPlanMode() → 收缩工具集
  │  ├─ mode = 'plan'
  │  └─ Agent 进入只读分析模式
  │
  └─ NO（已在 plan 模式）
     └─ 显示当前计划 / 打开编辑器

ExitPlanModeTool（退出计划模式）
  ├─ 检查：确认当前在 plan 模式
  ├─ 非 Teammate：询问用户确认 → 退出
  ├─ Teammate + isPlanModeRequired：
  │  ├─ 发送 plan_approval_request 到 Team Lead
  │  ├─ 等待审批（带 requestId 追踪）
  │  └─ 审批通过 → 退出 plan 模式
  └─ 恢复 prePlanMode（回到 auto/default/acceptEdits 等）
```

---

## 二、计划阶段的工具限制

Plan Mode 不是"提示 Agent 要小心"——是**硬性限制可用工具**：

```
计划阶段可用：
  ✓ Read, Glob, Grep         — 读代码、搜索
  ✓ Bash (只读命令)           — git status, ls, cat
  ✓ Agent (Explore/Plan 类型) — 只读子 Agent
  ✓ ToolSearch                — 发现工具
  ✓ ExitPlanMode              — 退出计划模式

计划阶段禁用：
  ✗ Write, Edit, NotebookEdit — 不能改文件
  ✗ Bash (写入命令)            — 不能 npm install, rm 等
  ✗ Agent (有写权限的类型)      — 不能 spawn 能改代码的子 Agent
```

**关键区别**：不是靠 prompt 指令说"请不要修改文件"（模型可能违反），而是**工具本身不可调用**（系统强制执行）。

---

## 三、计划存储与执行

```
计划阶段：
  Agent 分析代码 → 输出计划到对话流
  (可选) 持久化到 .claude/plan.md

用户审批后退出 plan 模式：
  Agent 回到正常模式
  按计划内容执行（Write/Edit/Bash 全部可用）
  每步执行后对照计划检查
```

---

## 四、团队审批工作流

对于 `isPlanModeRequired` 的 Teammate：

```
Teammate 完成计划
  ↓
ExitPlanModeTool.call()
  ├─ 生成 plan_approval_request:
  │  {
  │    from: "researcher",
  │    planContent: "1. 重构 auth 模块...",
  │    requestId: "req-abc123",
  │    planFilePath: ".claude/plan.md",
  │    timestamp: "2026-04-02T..."
  │  }
  ├─ writeToMailbox('team-lead', request, teamName)
  ├─ setAwaitingPlanApproval(true)
  └─ return { awaitingLeaderApproval: true }
  ↓
Team Lead 收到邮件
  ├─ 审核计划内容
  ├─ 批准 → SendMessage({ approve: true, requestId: "req-abc123" })
  └─ 拒绝 → SendMessage({ approve: false, feedback: "先加测试" })
  ↓
Teammate 收到审批结果
  ├─ 批准 → 退出 plan 模式 → 开始执行
  └─ 拒绝 → 修改计划 → 重新提交审批
```

---

## 五、与模型路由的联动

```
opusplan 别名：
  plan 模式 → 使用 Opus（深度思考，写出好计划）
  执行模式 → 使用 Sonnet（快速便宜，按计划执行）

Haiku 在 plan 模式：
  自动升级到 Sonnet（Haiku 写不出好计划）

bypass 模式 + plan 模式：
  如果用户之前在 bypass → isBypassPermissionsModeAvailable = true
  → plan 模式可以直接执行（不需要额外确认）
```

---

## 六、实现模板

```python
class PlanMode:
    def __init__(self, agent_loop, tool_registry):
        self.agent = agent_loop
        self.tools = tool_registry
        self.active = False
        self.pre_plan_mode = None
        self.plan_content = None

    def enter(self):
        """进入计划模式"""
        self.pre_plan_mode = self.agent.permission_mode
        self.agent.permission_mode = 'plan'
        self.active = True

        # 收缩工具集
        self.tools.restrict_to([
            'Read', 'Glob', 'Grep', 'Bash:readonly',
            'Agent:readonly', 'ToolSearch', 'ExitPlanMode'
        ])

    def exit(self, approved: bool = True):
        """退出计划模式"""
        if not approved:
            return False

        self.agent.permission_mode = self.pre_plan_mode or 'default'
        self.active = False

        # 恢复完整工具集
        self.tools.unrestrict()
        return True

    async def submit_for_approval(self, plan: str, team_lead: str):
        """团队审批工作流"""
        request = {
            "type": "plan_approval_request",
            "planContent": plan,
            "requestId": str(uuid4()),
            "timestamp": datetime.now().isoformat(),
        }
        await send_to_mailbox(team_lead, request)
        return request["requestId"]
```

---

## 七、实施步骤

请分析用户的 $ARGUMENTS 中指定的项目，然后：

1. **识别高风险操作**：哪些操作需要"先计划再执行"（数据库迁移、API 变更、大规模重构）
2. **实现工具集收缩**：plan 模式硬性禁用写操作，不靠 prompt 软约束
3. **实现状态切换**：记住原模式（prePlanMode），退出时恢复
4. **评估团队审批**：如果是多人协作，加 Team Lead 审批流程
5. **与模型路由联动**：plan 模式可以用更强的模型（计划质量 > 执行速度）
6. **持久化计划**：写入文件，方便审核和回溯

**反模式警告**：
- 不要靠 prompt 约束"请不要修改文件" — 模型会违反，用工具集收缩硬限制
- 不要 plan 模式用 Haiku — 计划质量需要更强的模型
- 不要跳过审批直接执行 — plan mode 的价值就是中间的人类检查点
- 不要忘了恢复原模式 — 退出 plan 后回到 auto/default/bypass
