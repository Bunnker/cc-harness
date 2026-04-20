---
name: eval-driven-design
description: "指导如何用实验驱动 Agent 设计：假设命名 + 前后对比评分 + 位置/措辞 A/B 测试 + 模型发布验证门"
user-invocable: true
argument-hint: "<目标项目路径或模块名>"
---

# 实验驱动设计方法论 (Eval-Driven Design)

> 从 Claude Code 源码注释中提取的设计方法论 — 每条 prompt 指令都用假设 → 实验 → 评分 → 迭代的流程验证

## 核心思想

**不要拍脑袋写 prompt——跑 eval。** CC 团队对每条记忆指令都用编号假设（H1-H6）、前后对比评分（0/3 → 3/3）、多变体测试（标题措辞、位置、强度）来验证效果。源码注释里记录了完整的实验轨迹。

---

## 一、CC 源码中的 Eval 实验记录（原文）

### 实验 1：标题措辞影响行为触发

```typescript
// src/memdir/memoryTypes.ts:241-244 — 原文
// Header wording matters: 
//   "Before recommending" (action cue at the decision point) → 3/3
//   "Trusting what you recall" (abstract) → 0/3
// Same body text — only the header differed.
```

**教训**：行动导向（"做 X 之前"）比抽象概念（"关于 X 的态度"）有效得多。模型需要在决策点被触发，不是在读概念时。

### 实验 2：指令位置比内容更重要

```typescript
// src/memdir/memoryTypes.ts:229-232 — 原文
// H1 (verify function/file claims): 0/2 → 3/3 via appendSystemPrompt. 
// When buried as a bullet under "When to access", dropped to 0/3 — 
// position matters. The H1 cue is about what to DO with a memory, 
// not when to look, so it needs its own section-level trigger context.
```

**教训**：同样的验证规则，作为子弹点藏在其他 section 下 → 0/3；给独立 H2 标题 → 3/3。**位置是独立变量**，和内容同样重要。

### 实验 3："即使用户要求也不做"需要显式声明

```typescript
// src/memdir/memoryTypes.ts:192-194 — 原文
// H2: explicit-save gate. 
// Eval-validated (memory-prompt-iteration case 3, 0/2 → 3/3): 
// prevents "save this week's PR list" → activity-log noise.

"These exclusions apply even when the user explicitly asks you to save."
```

**教训**：排除规则如果不显式覆盖"用户主动要求"的场景，模型会"听话地犯错"。

### 实验 4：沉默确认需要提醒模型主动捕捉

```typescript
// src/memdir/memoryTypes.ts:60-61 — 原文
"Corrections are easy to notice; confirmations are quieter — watch for them."
```

**教训**：不提醒 → 模型只存纠正。加了"confirmations are quieter — watch for them" → 开始同时存纠正和确认。

### 实验 5：模型换代时的回归检测

```typescript
// src/constants/prompts.ts:237 — 原文
// False-claims mitigation for Capybara v8 (29-30% FC rate vs v4's 16.7%)
// @[MODEL LAUNCH]: un-gate once validated on external via A/B
```

**教训**：新模型版本可能在某些维度回归。v4 → v8 false-claim rate 从 16.7% 涨到 29-30%，需要专门的 prompt 缓解措施 + A/B 验证门。

### 实验 6：部分成功也有价值

```typescript
// src/memdir/memoryTypes.ts:233-235 — 原文
// H5 (read-side noise rejection): 0/2 → 3/3 via appendSystemPrompt, 
// 2/3 in-place as a bullet. Partial because "snapshot" is intuitively 
// closer to "when to access" than H1 is.
```

**教训**：appendSystemPrompt 变体 3/3，in-place 变体 2/3。不是非黑即白——部分成功说明概念和位置有亲和性差异。

---

## 二、CC 的 Eval 方法论提取

### Step 1：命名假设

```
H1: 回忆前验证文件/函数声明
H2: 显式保存门（即使用户要求也拒绝噪音）
H5: 读取侧噪音过滤（快照 ≠ 当前状态）
H6: 分支污染防护（"忽略记忆" ≠ "承认后覆盖"）
```

**规则**：每个假设有唯一编号，方便在代码注释中引用（`// H1 went 3/3`）。

### Step 2：定义评分标准

```
CC 用的是 pass/fail 式评分：
  3/3 = 3 个 eval case 全部通过
  0/3 = 全部失败
  2/3 = 部分通过

每个 eval case 是一个具体场景：
  case 3: 用户要求保存 PR 列表 → Agent 应该拒绝并反问
  case 5: 用户说"忽略记忆" → Agent 不应该再提及记忆内容
```

### Step 3：控制变量测试

CC 测试的变量类型：

| 变量 | 测试方式 | 发现 |
|------|---------|------|
| **标题措辞** | 行动提示 vs 抽象描述 | 行动提示 3/3，抽象 0/3 |
| **位置** | 独立 section vs 子弹点 | 独立 3/3，子弹点 0/3 |
| **注入方式** | appendSystemPrompt vs in-place | append 3/3，in-place 2/3 |
| **覆盖强度** | 有/无"即使用户要求" | 有 3/3，无 0/2 |
| **模型版本** | v4 vs v8 | v8 false-claim 29% vs v4 17% |

### Step 4：记录到代码注释

```typescript
// 格式：
// {假设名} ({eval 文件名}, {日期}): {before} → {after} {via 变体}
// 解释为什么这个分数

// 示例：
// H1 (memory-prompt-iteration.eval.ts, 2026-03-17): 0/2 → 3/3 via appendSystemPrompt
// When buried as bullet: 0/3 — position matters
```

### Step 5：已知缺口标注

```typescript
// Known gap: H1 doesn't cover slash-command claims (0/3 on the /fork case —
// slash commands aren't files or functions in the model's ontology).
```

**不假装 100% 解决了**——记录已知缺口，让后续迭代知道哪里还需要改进。

### Step 6：区分轨迹评估与端态评估

**同一个任务可以从两个正交维度评估**，两者回答不同问题：

| 维度 | 看什么 | 回答的问题 | 典型失败 |
|------|--------|----------|---------|
| **轨迹评估（trajectory）** | 工具调用序列、子 Agent 分派、中间消息 | "它怎么做到的？" | 最终结果对了，但绕了一大圈 / 调用了危险工具 / 反复试错 |
| **端态评估（end-state）** | 数据库行、文件内容、API 响应 | "它做到了吗？" | 看起来步骤合理，但最终状态错误 / 写错文件 / 漏了一步 |

**一条规则**：只看端态会纵容 agent 走捷径（如直接 rm -rf 后重建）；只看轨迹会奖励"看起来像在工作"但啥也没改。**生产环境两者都要**。

CC 源码的体现：`harness-verify` skill 同时产出 `verification.md`（端态）和 `commands.log`（轨迹）。

### Step 7：pass@k vs pass^k 选择

k 次独立运行同一任务，两种聚合方式：

```
pass@k  = k 次里至少 1 次成功 (P(任意成功))
pass^k  = k 次全部成功         (P(每次成功))
```

**决策规则**：
- 产品是"**一次就行**"（生成代码片段，用户可以重跑）→ 用 `pass@k`，k=3-5
- 产品是"**每次都要对**"（定时任务、CI 自动化、写生产数据）→ 用 `pass^k`，k≥3
- `pass@1 = pass^1`，单次评估两者等价——多次才出现分化

**一个常见误判**：报告 `pass@5 = 90%` 听起来很好，但如果实际产品是每天跑 100 次的自动化，`pass^100 ≈ (0.59)^100 ≈ 10^-22`——完全不可用。**聚合方式必须匹配使用场景**。

### Step 8：online eval vs offline eval 分叉

两种采样源，工程落地时必须选一个主线：

| 类型 | 样本来源 | 触发时机 | 适用阶段 |
|------|---------|---------|---------|
| **Offline eval** | 固定基准集（20-50 个手工 case） | PR 提交 / 模型升级前 | 回归防护、模型换代 |
| **Online eval** | 生产轨迹抽样（随机或按规则采样） | 持续运行 | 发现 OOD 失败、长尾边界 |

**分叉决策树**：
```
有固定正确答案？ → offline（能算准确率）
只有人工判断？ → online 采样 + LLM-judge 或人工标注
行为随时间漂移？ → online（offline 基准会过期）
成本敏感？ → offline 少样本起步，online 按采样率控制
```

**反模式**：只有 offline 会让你在生产上瞎；只有 online 会让你无法横向比较模型版本。CC 的做法是 offline 做模型发布门（`@[MODEL LAUNCH]`），online 做持续监控。

### Step 9：Transcript Shape Analysis（中间过程的脆弱点）

> Anthropic 原话：
> 
> *Read transcripts for the shape of failure, not just the outcome. Watch for: redundant tool calls, tool-call oscillation, eager self-summary before task completion, silent capability drop.*

scorecard 只告诉你"最终结果对不对"，transcript 才告诉你"它是怎么到那里的"。同样的 0.99 composite 可以来自两种完全不同的轨迹：一次性走对，或者绕了 5 个来回试错然后刚好蒙对。**后者就是脆弱点**——环境稍微扰动就会翻车。只看 scorecard 会奖励这种脆弱的成功。

#### 4 种 Anthropic 命名的 shape 脆弱模式

| 模式 | 看什么信号 | 怎么数 | 根因指向 |
|------|----------|--------|---------|
| **冗余工具调用** | 同一个 Read/Grep 重复调用同一文件/模式 ≥ 3 次 | transcript 里 `tool_use.input.file_path` 按值分组计数 | 模型忘了上次读过，或在 context 压力下重新拉回记忆。常伴随接近 context 上限 |
| **工具调用震荡** | 短窗口内工具序列出现 A→B→A→B、Edit→Bash→Edit→Bash 这种循环且状态没推进 | 滑动窗口 n=4，看 `tool_name` 序列是否周期 2 且结果 hash 不变 | 模型在两种假设间摇摆，没拿到决定性信号就在"猜"。continue 下去分数会骤降 |
| **过早自我总结** | 任务未完成就出现 "I've successfully..."、"完成了 X"、"全部通过" 的 assistant text | regex 扫 `successfully\|complete\|全部\|已完成` + 对比 feature_list.json 是否真 done | Context anxiety（见 `agent-resilience` §7）。**最隐蔽**——模型声音自信但工作未完 |
| **沉默能力下降** | 以前能做的操作现在说 "I'm unable to..."、"cannot directly..." | 把"能力声明"token 作为**回归指标**跨轮跟踪（新模型比旧模型这个指标应该更低，反转说明回归） | 模型换代后行为漂移（见本 skill §三 MODEL LAUNCH Gate） |

#### 用新合入的 artifact 做 shape 分析

M1 Python hooks 和 audit 升级后，**transcript shape 不再要靠 raw JSONL 手读**，已经有结构化的 artifact 可以直接喂：

| Artifact | 能揭示哪种 shape | 怎么用 |
|----------|----------------|--------|
| `commands.log`（M1 command-facade 产出） | 冗余调用、震荡 | `grep -c` 数同命令出现次数；观察命令交错模式 |
| `worker-N-result.md` | 过早自我总结 | 搜索结尾的胜利宣言 token，对照 `feature_list.json` 真实状态 |
| `audit-findings.md`（harness-verify §6.5 产出） | 过早自我总结的**证实信号** | 如果 Worker 声称 done 但 audit 找出 critical issue → 命中 "premature self-summary" |
| `scorecard.json` 的 `code_quality` 维度（新 6 维）| 沉默能力下降的横截面 | 同一 Worker 多轮的 code_quality 趋势；下降而其他维度不变 → 模型/prompt 有回归 |

#### 决策规则

```
轨迹评估（Step 6）+ shape 分析（本步）的组合规则：

端态通过（Step 6 end-state ✓）
  + 轨迹无脆弱 shape  → 真实通过，记入 pass^k 分子
  + 轨迹有脆弱 shape → 标注"fragile pass"，pass@k 算通过但 pass^k 不算
端态失败（Step 6 end-state ✗）
  → 失败。但看 shape 决定根因：
     redundant/oscillation → prompt/工具设计问题
     premature summary → context 管理问题
     capability drop → 模型换代问题
```

**fragile pass 这个概念比简单的 pass/fail 多带一维信息**——它让你在模型升级时能看到"表面分数没降，但脆弱性上升"的趋势，不然就只能等事故发生才知道退化了。

#### 反模式

- 不要只在失败时读 transcript——成功轨迹里的 shape 脆弱同样重要，是下次失败的先行指标
- 不要把 4 种 shape 各自做阈值硬编码触发（如 "冗余 ≥ 3 就告警"）——应该**累加权重**，单维度小幅度不报，多维同时出现才升级
- 不要在 transcript 上跑自动"修复"（让 LLM 看 transcript 建议改 prompt）——先人工建立至少 20 个标注样本，否则 shape 分析本身会被 LLM 的自评盲点污染（见 `agent-reflection` §7）

#### 关联 skill

- [agent-resilience](../agent-resilience/SKILL.md) §7 Context Anxiety — 过早自我总结的机制解释
- [agent-reflection](../agent-reflection/SKILL.md) §7 Self-Eval Blind Spot — 为什么不能让同一个 agent 分析自己的 shape
- [harness-verify](../harness-verify/SKILL.md) §6.5 代码审计 — 把 shape 信号结构化为 audit-findings.md
- [telemetry-pipeline](../telemetry-pipeline/SKILL.md) — transcript 采集与隐私保护的源头

---

## 三、模型发布验证门（MODEL LAUNCH Gate）

CC 用 `@[MODEL LAUNCH]` 注释标记需要在新模型上线前验证的 prompt 调整：

```typescript
// @[MODEL LAUNCH]: capy v8 thoroughness counterweight (PR #24302) 
//   — un-gate once validated on external via A/B

// @[MODEL LAUNCH]: capy v8 assertiveness counterweight (PR #24302)
//   — un-gate once validated on external via A/B

// @[MODEL LAUNCH]: Update comment writing for Capybara 
//   — remove or soften once the model stops over-commenting by default
```

**流程**：
1. 新模型内部测试发现行为变化（如 v8 false-claim 率从 17% 涨到 30%）
2. 写 prompt 缓解措施
3. 标记 `@[MODEL LAUNCH]`，加 feature flag 门控
4. 内部 A/B 验证通过
5. 外部 A/B 验证通过
6. 摘除门控，成为正式 prompt

---

## 四、安全验证驱动（HackerOne/PR Review）

CC 的安全设计也是实验驱动的，但实验来源不同：

```typescript
// src/tools/BashTool/bashSecurity.ts
// "This check catches the eval bypass discovered in HackerOne review."
// → 安全检查的"eval"来自白帽攻击报告

// src/tools/BashTool/bashPermissions.ts:603
// "intentional for allow rules (see HackerOne #3543050)"
// → 特定行为经过安全报告确认为设计预期

// src/tools/BashTool/pathValidation.ts:1160-1171
// "Hit 3× in PR #21075, twice more in PR #21503"
// → 安全审查轮次记录（3 轮 review，每轮发现新边界）
```

---

## 五、实现模板

```python
class EvalFramework:
    """Agent prompt 的实验驱动设计框架"""

    def __init__(self, eval_dir: str):
        self.eval_dir = eval_dir
        self.hypotheses: dict[str, Hypothesis] = {}

    def define_hypothesis(self, id: str, description: str, variants: list[dict]):
        """定义假设 + 变体"""
        self.hypotheses[id] = Hypothesis(
            id=id,
            description=description,
            variants=variants,  # [{"name": "action_cue", "prompt": "..."}, ...]
            results={},
        )

    async def run_eval(self, hypothesis_id: str, eval_cases: list[dict]) -> dict:
        """对每个变体跑所有 eval case"""
        h = self.hypotheses[hypothesis_id]
        for variant in h.variants:
            passed = 0
            for case in eval_cases:
                result = await self._run_case(variant["prompt"], case)
                if result.passed:
                    passed += 1
            h.results[variant["name"]] = f"{passed}/{len(eval_cases)}"
        return h.results

    def generate_code_comment(self, hypothesis_id: str) -> str:
        """生成注释（嵌入到 prompt 代码旁边）"""
        h = self.hypotheses[hypothesis_id]
        lines = [f"// {h.id} ({h.description}):"]
        for variant, score in h.results.items():
            lines.append(f"//   {variant}: {score}")
        return "\n".join(lines)

# 使用示例
eval = EvalFramework("evals/memory-prompt/")

eval.define_hypothesis("H1", "verify function/file claims", [
    {"name": "as_bullet", "prompt": "- If memory names a file: check exists"},
    {"name": "as_section", "prompt": "## Before recommending\n\nIf memory names a file: check exists"},
])

results = await eval.run_eval("H1", [
    {"input": "memory says utils.py has foo()", "expected": "grep for foo()"},
    {"input": "memory says config has DEBUG flag", "expected": "check config"},
])
# results = {"as_bullet": "0/2", "as_section": "2/2"}
```

---

## 六、实施步骤

请分析用户的 $ARGUMENTS 中指定的项目，然后：

1. **给关键 prompt 指令命名假设**（H1, H2, ...）
2. **定义 eval case**：每个假设至少 3 个具体场景
3. **控制变量**：一次只变一个维度（措辞/位置/强度/注入方式）
4. **记录分数到代码注释**：`// H1: 0/2 → 3/3 via section header`
5. **标注已知缺口**：不假装 100% 解决
6. **模型换代时重跑 eval**：新模型可能在已验证的维度上回归
7. **安全相关用真实攻击验证**：HackerOne 报告 > 理论分析

**反模式警告**：
- 不要拍脑袋写 prompt — 跑 eval
- 不要只测"能不能工作" — 测"在哪个位置/哪种措辞下工作最好"
- 不要假设新模型行为不变 — v4 → v8 false-claim 率翻倍
- 不要把 eval 结果只放在文档里 — 放在代码注释里，紧挨着被验证的代码
