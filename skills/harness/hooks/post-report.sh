#!/usr/bin/env bash
# M1.2 Hook: post-report
# REPORT 完成后由 Coordinator 调用，验证 trace 完整性
# 用法: post-report.sh <trace_dir> <task_type> <worker_count>
#   task_type: "design" | "coding" | "audit"
#   worker_count: Worker 数量

set -euo pipefail

TRACE_DIR="$1"
TASK_TYPE="$2"
WORKER_COUNT="$3"

ERRORS=0

echo "=== M1.3 Trace Integrity Check ==="
echo "trace_dir: $TRACE_DIR"
echo "task_type: $TASK_TYPE"
echo "worker_count: $WORKER_COUNT"
echo ""

# 所有任务类型都必须有的文件
for file in verification.md scorecard.json; do
  if [ ! -f "$TRACE_DIR/$file" ]; then
    echo "FAIL: $file missing"
    ERRORS=$((ERRORS + 1))
  else
    echo "OK:   $file ($(wc -c < "$TRACE_DIR/$file") bytes)"
  fi
done

# 每个 Worker 必须有的文件
for n in $(seq 1 "$WORKER_COUNT"); do
  # prompt.md — 所有任务类型必填
  if [ ! -f "$TRACE_DIR/worker-${n}-prompt.md" ]; then
    echo "FAIL: worker-${n}-prompt.md missing"
    ERRORS=$((ERRORS + 1))
  else
    echo "OK:   worker-${n}-prompt.md"
  fi

  # result.md — 所有任务类型必填
  if [ ! -f "$TRACE_DIR/worker-${n}-result.md" ]; then
    echo "FAIL: worker-${n}-result.md missing"
    ERRORS=$((ERRORS + 1))
  else
    echo "OK:   worker-${n}-result.md"
  fi

  # 编码任务额外必填
  if [ "$TASK_TYPE" = "coding" ]; then
    if [ ! -f "$TRACE_DIR/worker-${n}-diff.patch" ]; then
      echo "FAIL: worker-${n}-diff.patch missing (coding task)"
      ERRORS=$((ERRORS + 1))
    else
      echo "OK:   worker-${n}-diff.patch"
    fi
  fi
done

# 编码任务必须有 commands.log
if [ "$TASK_TYPE" = "coding" ]; then
  if [ ! -f "$TRACE_DIR/commands.log" ]; then
    echo "FAIL: commands.log missing (coding task)"
    ERRORS=$((ERRORS + 1))
  else
    echo "OK:   commands.log ($(wc -l < "$TRACE_DIR/commands.log") lines)"
  fi
fi

# scorecard.json 校验
if [ -f "$TRACE_DIR/scorecard.json" ]; then
  # 检查 composite_score 存在
  if grep -q '"composite_score"' "$TRACE_DIR/scorecard.json"; then
    SCORE=$(grep -o '"composite_score": *[0-9.]*' "$TRACE_DIR/scorecard.json" | head -1 | grep -o '[0-9.]*$')
    echo "OK:   composite_score = $SCORE"
  else
    echo "FAIL: scorecard.json missing composite_score"
    ERRORS=$((ERRORS + 1))
  fi
fi

echo ""
if [ $ERRORS -eq 0 ]; then
  echo "=== ALL CHECKS PASSED ==="
  exit 0
else
  echo "=== $ERRORS CHECK(S) FAILED ==="
  exit 1
fi
