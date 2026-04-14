#!/usr/bin/env bash
# M1.2 Hook: generate-coding-traces
# 编码轮 REPORT 结束后由 Coordinator 调用，自动生成 commands.log 和 per-worker diff.patch
#
# 用法: generate-coding-traces.sh <project_path> <trace_dir> <baseline_commit> <worker_specs...>
#   worker_specs 格式: "worker_n:path1,path2,path3" (每个 worker 一个 spec)
#
# 示例:
#   generate-coding-traces.sh "D:/ai code/Zero_magic" \
#     "D:/ai code/Zero_magic/.claude/harness-lab/traces/2026-04-06-stage-6-coding" \
#     "abc1234" \
#     "1:backend/runtime/src/graph/state.py,backend/runtime/src/multi_agent/" \
#     "2:backend/gateway/src/routes/agents.ts"

set -euo pipefail

PROJECT_PATH="$1"
TRACE_DIR="$2"
BASELINE="$3"
shift 3

mkdir -p "$TRACE_DIR"

# ============================================
# 1. commands.log — 从 harness-state.json 读取并执行 commands
# ============================================
STATE_FILE="$PROJECT_PATH/.claude/harness-state.json"
COMMANDS_LOG="$TRACE_DIR/commands.log"

echo "=== commands.log generation ===" > "$COMMANDS_LOG"
echo "date: $(date -Iseconds)" >> "$COMMANDS_LOG"
echo "baseline: $BASELINE" >> "$COMMANDS_LOG"
echo "" >> "$COMMANDS_LOG"

if [ -f "$STATE_FILE" ]; then
  # 提取所有 command key-value pairs
  # 跳过 structural_diff 和 per_worker_diff (模板命令，需要替换变量)
  COMMANDS=$(grep -oP '"(typecheck_\w+|build_\w+|smoke_\w+)"\s*:\s*"([^"]*)"' "$STATE_FILE" 2>/dev/null || true)

  if [ -n "$COMMANDS" ]; then
    while IFS= read -r line; do
      CMD_NAME=$(echo "$line" | grep -oP '"\K[^"]+' | head -1)
      CMD_VALUE=$(echo "$line" | grep -oP ':\s*"\K[^"]+')

      echo "=== $CMD_NAME ===" >> "$COMMANDS_LOG"
      echo "\$ $CMD_VALUE" >> "$COMMANDS_LOG"

      # 执行命令，捕获输出和 exit code
      OUTPUT=$(eval "$CMD_VALUE" 2>&1) || true
      EXIT_CODE=$?

      echo "$OUTPUT" >> "$COMMANDS_LOG"
      echo "exit_code: $EXIT_CODE" >> "$COMMANDS_LOG"
      echo "" >> "$COMMANDS_LOG"
    done <<< "$COMMANDS"
  else
    echo "WARNING: no commands found in harness-state.json" >> "$COMMANDS_LOG"
  fi
else
  echo "WARNING: $STATE_FILE not found" >> "$COMMANDS_LOG"
fi

echo "[generate-coding-traces] commands.log written ($(wc -l < "$COMMANDS_LOG") lines)"

# ============================================
# 2. per-worker diff.patch — 对每个 worker 按 target_paths 生成 diff
# ============================================
for SPEC in "$@"; do
  WORKER_N="${SPEC%%:*}"
  PATHS_CSV="${SPEC#*:}"

  DIFF_FILE="$TRACE_DIR/worker-${WORKER_N}-diff.patch"

  # 把逗号分隔的路径转成空格分隔
  IFS=',' read -ra PATH_ARRAY <<< "$PATHS_CSV"

  {
    echo "=== worker-${WORKER_N} diff ==="
    echo "baseline: $BASELINE"
    echo "target_paths: ${PATH_ARRAY[*]}"
    echo ""
    echo "=== git diff --stat ==="
    cd "$PROJECT_PATH" && git diff --stat "$BASELINE" HEAD -- "${PATH_ARRAY[@]}" 2>&1 || true
    echo ""
    echo "=== git diff ==="
    cd "$PROJECT_PATH" && git diff "$BASELINE" HEAD -- "${PATH_ARRAY[@]}" 2>&1 || true
  } > "$DIFF_FILE"

  echo "[generate-coding-traces] worker-${WORKER_N}-diff.patch written ($(wc -l < "$DIFF_FILE") lines)"
done

echo "[generate-coding-traces] done"
