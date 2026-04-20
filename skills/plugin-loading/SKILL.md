---
name: plugin-loading
description: "Skill/插件加载：4 个独立 loader（file-based / plugin / bundled / MCP）+ 7 源合并顺序 + 条件激活 + disable-model-invocation 真实语义"
user-invocable: false
argument-hint: "<目标项目路径或模块名>"
---

# Skill 与插件加载

> 参考实现：`src/skills/loadSkillsDir.ts`（文件 skill）、`src/utils/plugins/loadPluginCommands.ts`（插件命令）、`src/skills/bundledSkills.ts`（内置 skill）、`src/skills/mcpSkillBuilders.ts`（MCP skill）、`src/commands.ts`（合并调度）

## 源码事实

### 1. 四个独立的 loader，不是一个统一的加载系统

| Loader | 文件 | 加载什么 | loadedFrom |
|--------|------|---------|-----------|
| **File-based Skills** | `loadSkillsDir.ts` | `.claude/skills/` 和 `~/.claude/skills/` 下的 SKILL.md | `'skills'` |
| **Plugin Commands** | `loadPluginCommands.ts` | 插件目录中的 .md 文件和 SKILL.md | `'plugin'` |
| **Bundled Skills** | `bundledSkills.ts` | `registerBundledSkill()` 编译期注册 | `'bundled'` |
| **MCP Skills** | `mcpSkillBuilders.ts` | MCP 服务器的 prompts/list 响应 | `'mcp'` |

**Plugin loader 和 Skill loader 是完全独立的。** `loadPluginCommands.ts` 不调用 `loadSkillsDir.ts`，它有自己的目录遍历和 manifest 解析逻辑。

### 2. 七源合并顺序（先加载 = 先去重 = 优先级更高）

```typescript
// src/commands.ts:449-468 — loadAllCommands()
return [
  ...bundledSkills,          // 1. 内置 skill（编译期）
  ...builtinPluginSkills,    // 2. 内置插件 skill
  ...skillDirCommands,       // 3. 文件 skill（.claude/skills/）
  ...workflowCommands,       // 4. 工作流脚本
  ...pluginCommands,         // 5. 插件命令（plugin.json）
  ...pluginSkills,           // 6. 插件 skill（插件内的 SKILL.md）
  ...COMMANDS(),             // 7. 内建 CLI 命令（/clear, /config 等）
]
```

**去重规则**：先出现的同名命令胜出。所以内置 skill 可以被用户覆盖（用户在 `.claude/skills/` 创建同名），但插件不能覆盖内置。

### 3. File-based Skill 的去重用 realpath，不是文件名

```typescript
// src/skills/loadSkillsDir.ts
const fileIds = await Promise.all(
  allSkills.map(({ filePath }) => getFileIdentity(filePath))  // realpath()
)

// 同一物理文件通过不同路径引用 → 只加载一次
const seen = new Map<string, SettingSource>()
for (const fileId of fileIds) {
  if (seen.has(fileId)) continue  // 跳过
  seen.set(fileId, source)
}
```

### 4. 条件 Skill（paths frontmatter）是两阶段加载

```
会话启动：
  无 paths: 的 skill → 立即加载到可见列表
  有 paths: 的 skill → 存入 conditionalSkills Map（不可见）

运行时：
  Agent 编辑 src/utils/helper.py
  → activateConditionalSkillsForPaths(["src/utils/helper.py"])
  → glob 匹配 "src/**/*.py" → 激活该 skill
  → 移入 dynamicSkills Map → 下一轮对模型可见
```

### 5. disable-model-invocation 的真实语义

检查位置：`src/tools/SkillTool/SkillTool.ts:412`

```typescript
// SkillTool.validateInput() 中
if (foundCommand.disableModelInvocation) {
  return { result: false, message: `Skill ... cannot be used with SkillTool` }
}
```

**真实行为**：
- `disable-model-invocation: true` → 模型不能通过 SkillTool 调用此 skill
- 用户仍然可以通过 `/skill-name` 手动调用
- **不是"禁止模型看到"——skill 仍然出现在 skill listing 中**，只是模型调用 SkillTool 时被 validateInput 拦截

### 6. MCP Skill 复用 builder 但不复用信任边界

```typescript
// src/skills/mcpSkillBuilders.ts — 注册 builder 函数
registerMCPSkillBuilders({
  createSkillCommand,           // 复用 loadSkillsDir.ts 的 builder
  parseSkillFrontmatterFields,  // 复用 frontmatter 解析
})

// 但 MCP skill 的 shell 执行被禁止
if (loadedFrom !== 'mcp') {
  finalContent = await executeShellCommandsInPrompt(...)
}
// MCP skill 跳过所有 !`command` 和 ```! 块
```

---

## 可迁移设计

### 多 loader 独立 + 统一合并

```python
# 每个来源有自己的 loader
loaders = [
    BundledLoader(),     # 编译期注册
    FileBasedLoader(),   # 文件系统扫描
    PluginLoader(),      # 插件 manifest
    RemoteLoader(),      # 远程来源（MCP 等）
]

# 统一合并，先加载的同名优先
commands = []
seen_names = set()
for loader in loaders:
    for cmd in await loader.load():
        if cmd.name not in seen_names:
            seen_names.add(cmd.name)
            commands.append(cmd)
```

### 条件激活模式

```python
# 有 paths glob 的 skill 不立即加载
unconditional = []
conditional = {}

for skill in all_skills:
    if skill.paths:
        conditional[skill.name] = skill
    else:
        unconditional.append(skill)

# 运行时：文件操作触发激活
def on_file_touched(filepath):
    for name, skill in list(conditional.items()):
        if any(glob_match(p, filepath) for p in skill.paths):
            unconditional.append(skill)
            del conditional[name]
```

---

## 不要照抄的实现细节

- CC 的 `loadPluginCommands.ts` 处理了插件 manifest（plugin.json）的完整生命周期——你的项目大概率不需要插件 manifest 格式
- `realpath()` 去重是因为 CC 支持符号链接和 `--add-dir`——简单项目用文件名去重就够
- `COMMANDS()` 返回的内建命令（/clear, /config）是 CC 特有的 CLI 命令，不是 skill

---

## 反模式

- 不要让远程 skill（MCP）执行本地 shell 命令——`!`command`` 只允许本地来源
- 不要混淆 plugin loader 和 skill loader——它们是独立的代码路径
- 不要用插入顺序做优先级——用显式的来源优先级列表
- 不要让 `disable-model-invocation` 注释写反——它禁止的是模型调用，不是用户调用
