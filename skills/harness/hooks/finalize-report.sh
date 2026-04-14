#!/usr/bin/env bash
# M1 Hook: finalize-report
# REPORT 结束后 Coordinator 必须执行此脚本。
# 如果返回非 0，Coordinator 不允许提 commit。
#
# 用法: bash finalize-report.sh <project_path> <trace_dir> <task_type> <worker_count>
#   project_path: 项目根目录 (如 "D:/ai code/Zero_magic")
#   trace_dir:    本轮 trace 目录 (如 ".claude/harness-lab/traces/2026-04-07-stage-7")
#   task_type:    design | coding | audit
#   worker_count: Worker 数量

set -euo pipefail

if [ $# -lt 4 ]; then
  echo "❌ 用法: finalize-report.sh <project_path> <trace_dir> <task_type> <worker_count>"
  exit 1
fi

PROJECT_PATH="$1"
TRACE_DIR="$2"
TASK_TYPE="$3"
WORKER_COUNT="$4"

STATE_FILE="$PROJECT_PATH/.claude/harness-state.json"
FULL_TRACE_DIR="$PROJECT_PATH/.claude/$TRACE_DIR"
TODAY=$(date +%Y-%m-%d)
ERRORS=0
FIXES=""

echo "╔══════════════════════════════════════════╗"
echo "║   Harness Report Finalization Check      ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "project:      $PROJECT_PATH"
echo "trace_dir:    $TRACE_DIR"
echo "task_type:    $TASK_TYPE"
echo "worker_count: $WORKER_COUNT"
echo "today:        $TODAY"
echo ""

# ============================================
# 1. State 更新检查
# ============================================
echo "=== 1. harness-state.json 检查 ==="

if [ ! -f "$STATE_FILE" ]; then
  echo "FAIL: harness-state.json 不存在"
  FIXES="$FIXES\n- 创建或更新 $STATE_FILE"
  ERRORS=$((ERRORS + 1))
else
  # 检查 last_execution.date 包含今天的日期
  if grep -q "\"date\": \"${TODAY}" "$STATE_FILE"; then
    echo "OK:   last_execution.date 包含 $TODAY"
  else
    LAST_DATE=$(grep -o '"date": "[^"]*"' "$STATE_FILE" | head -1 | grep -o '[0-9T:.-]*')
    echo "FAIL: last_execution.date 是 $LAST_DATE，不是今天 ($TODAY)"
    FIXES="$FIXES\n- 用 Edit 工具更新 harness-state.json 的 last_execution.date 为 ${TODAY}T..."
    ERRORS=$((ERRORS + 1))
  fi

  # 检查 agents_dispatched > 0 (硬边界2: 不允许自执行)
  DISPATCHED=$(grep -o '"agents_dispatched": [0-9]*' "$STATE_FILE" | grep -o '[0-9]*')
  if [ -n "$DISPATCHED" ] && [ "$DISPATCHED" -gt 0 ]; then
    echo "OK:   agents_dispatched = $DISPATCHED"
  else
    echo "FAIL: agents_dispatched = ${DISPATCHED:-null} (必须 > 0，Coordinator 禁止自执行)"
    FIXES="$FIXES\n- 检查是否违反硬边界 2（Coordinator 自执行），更新 agents_dispatched"
    ERRORS=$((ERRORS + 1))
  fi

  # 检查 learnings 中最新条目有 trace_ref
  LATEST_LEARNING_HAS_REF=$(grep -c "trace_ref" "$STATE_FILE" 2>/dev/null || echo "0")
  TOTAL_LEARNINGS=$(grep -c '"insight"' "$STATE_FILE" 2>/dev/null || echo "0")
  if [ "$TOTAL_LEARNINGS" -gt 0 ]; then
    echo "OK:   learnings: $TOTAL_LEARNINGS 条, $LATEST_LEARNING_HAS_REF 条有 trace_ref"
    # 检查最新的 learning 是否有 trace_ref (粗略检查: 最后一个 insight 后 5 行内有 trace_ref)
  fi
fi

echo ""

# ============================================
# 2. Trace 目录完整性检查
# ============================================
echo "=== 2. Trace 完整性检查 ==="

mkdir -p "$FULL_TRACE_DIR"

# 所有任务类型必须有的文件
for file in verification.md scorecard.json; do
  if [ -f "$FULL_TRACE_DIR/$file" ]; then
    SIZE=$(wc -c < "$FULL_TRACE_DIR/$file")
    echo "OK:   $file ($SIZE bytes)"
  else
    echo "FAIL: $file 缺失"
    FIXES="$FIXES\n- 写入 $TRACE_DIR/$file"
    ERRORS=$((ERRORS + 1))
  fi
done

# 每个 Worker 的文件
for n in $(seq 1 "$WORKER_COUNT"); do
  # prompt.md — 所有类型必填
  if [ -f "$FULL_TRACE_DIR/worker-${n}-prompt.md" ]; then
    echo "OK:   worker-${n}-prompt.md"
  else
    echo "FAIL: worker-${n}-prompt.md 缺失"
    FIXES="$FIXES\n- 写入 worker-${n} 的完整 prompt 到 $TRACE_DIR/worker-${n}-prompt.md"
    ERRORS=$((ERRORS + 1))
  fi

  # result.md — 所有类型必填
  if [ -f "$FULL_TRACE_DIR/worker-${n}-result.md" ]; then
    echo "OK:   worker-${n}-result.md"
  else
    echo "FAIL: worker-${n}-result.md 缺失"
    FIXES="$FIXES\n- 写入 worker-${n} 的完整回复到 $TRACE_DIR/worker-${n}-result.md"
    ERRORS=$((ERRORS + 1))
  fi

  # 编码/审计任务额外必填
  if [ "$TASK_TYPE" = "coding" ] || [ "$TASK_TYPE" = "audit" ]; then
    if [ -f "$FULL_TRACE_DIR/worker-${n}-diff.patch" ]; then
      echo "OK:   worker-${n}-diff.patch"
    else
      echo "FAIL: worker-${n}-diff.patch 缺失 ($TASK_TYPE task)"
      FIXES="$FIXES\n- 执行 git diff 生成 worker-${n}-diff.patch"
      ERRORS=$((ERRORS + 1))
    fi
  fi
done

# 编码/审计任务必须有 commands.log
if [ "$TASK_TYPE" = "coding" ] || [ "$TASK_TYPE" = "audit" ]; then
  if [ -f "$FULL_TRACE_DIR/commands.log" ]; then
    LINES=$(wc -l < "$FULL_TRACE_DIR/commands.log")
    echo "OK:   commands.log ($LINES lines)"
  else
    echo "FAIL: commands.log 缺失 ($TASK_TYPE task)"
    FIXES="$FIXES\n- 执行 generate-coding-traces.sh 或手动运行 commands 写入 commands.log"
    ERRORS=$((ERRORS + 1))
  fi
fi

echo ""

# ============================================
# 3. Scorecard 校验
# ============================================
echo "=== 3. Scorecard 校验 ==="

if [ -f "$FULL_TRACE_DIR/scorecard.json" ]; then
  if grep -q '"composite_score"' "$FULL_TRACE_DIR/scorecard.json"; then
    SCORE=$(grep -o '"composite_score": *[0-9.]*' "$FULL_TRACE_DIR/scorecard.json" | head -1 | grep -o '[0-9.]*$' || echo "null")
    echo "OK:   composite_score = $SCORE"
  else
    echo "FAIL: scorecard.json 缺少 composite_score"
    ERRORS=$((ERRORS + 1))
  fi
fi

echo ""

# ============================================
# 结果
# ============================================
if [ $ERRORS -eq 0 ]; then
  echo "╔══════════════════════════════════════════╗"
  echo "║   ✅ ALL CHECKS PASSED — 可以 commit     ║"
  echo "╚══════════════════════════════════════════╝"
  exit 0
else
  echo "╔══════════════════════════════════════════╗"
  echo "║   ❌ $ERRORS 项检查失败 — 不允许 commit    ║"
  echo "╚══════════════════════════════════════════╝"
  echo ""
  echo "修复清单："
  echo -e "$FIXES"
  echo ""
  echo "修复后重新执行此脚本验证。"
  exit 1
fi
