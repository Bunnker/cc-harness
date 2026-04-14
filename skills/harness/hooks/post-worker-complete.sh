#!/usr/bin/env bash
# M1.2 Hook: post-worker-complete
# 每个 Worker 完成后由 Coordinator 调用
# 用法: post-worker-complete.sh <project_path> <trace_dir> <worker_n> <baseline_commit> <target_paths...>
#
# 自动执行:
#   1. git diff --stat && git diff -- target_paths → worker-{n}-diff.patch
#   2. 验证 trace 目录中 worker-{n}-result.md 存在

set -euo pipefail

PROJECT_PATH="$1"
TRACE_DIR="$2"
WORKER_N="$3"
BASELINE_COMMIT="$4"
shift 4
TARGET_PATHS=("$@")

# 确保 trace 目录存在
mkdir -p "$TRACE_DIR"

# 1. 生成 per-worker diff
DIFF_FILE="$TRACE_DIR/worker-${WORKER_N}-diff.patch"
{
  echo "=== git diff --stat ==="
  cd "$PROJECT_PATH" && git diff --stat "$BASELINE_COMMIT" HEAD -- "${TARGET_PATHS[@]}" 2>&1 || true
  echo ""
  echo "=== git diff ==="
  cd "$PROJECT_PATH" && git diff "$BASELINE_COMMIT" HEAD -- "${TARGET_PATHS[@]}" 2>&1 || true
} > "$DIFF_FILE"

echo "[post-worker-complete] worker-${WORKER_N}-diff.patch written ($(wc -l < "$DIFF_FILE") lines)"

# 2. 检查 result.md 存在
RESULT_FILE="$TRACE_DIR/worker-${WORKER_N}-result.md"
if [ ! -f "$RESULT_FILE" ]; then
  echo "[post-worker-complete] WARNING: $RESULT_FILE not found"
  exit 1
fi

echo "[post-worker-complete] worker-${WORKER_N} trace OK"
