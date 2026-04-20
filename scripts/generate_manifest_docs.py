#!/usr/bin/env python3
"""Validate manifest/skills.json and generate derived docs."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "manifest" / "skills.json"
README_PATH = REPO_ROOT / "README.md"
CATALOG_PATH = REPO_ROOT / "skills" / "harness" / "skill-catalog.md"
DEPENDENCY_PATH = REPO_ROOT / "skills" / "harness" / "dependency-graph.md"

README_START = "<!-- GENERATED:SKILL_SUMMARY:START -->"
README_END = "<!-- GENERATED:SKILL_SUMMARY:END -->"

STAGE_LABELS = {
    "stage-0-contracts": "阶段 0：契约定义",
    "stage-1-minimal-loop": "阶段 1：最小循环",
    "stage-2-security": "阶段 2：安全与资源控制",
    "stage-3-long-session": "阶段 3：长会话支持",
    "stage-4-memory": "阶段 4：跨会话与记忆",
    "stage-5-extensibility": "阶段 5：可扩展性",
    "stage-6-multi-agent": "阶段 6：多 Agent 编排",
    "stage-7-production": "阶段 7：生产化",
    "stage-8-enterprise": "阶段 8：企业治理",
}

CATEGORY_ORDER = [
    "orchestration",
    "harness-infrastructure",
    "foundation-contracts",
    "agent-core",
    "capability-extensions",
    "production",
    "long-session",
    "memory-extensions",
    "ide-input",
    "enterprise",
    "methodology",
]

REQUIRED_SKILL_FIELDS = {
    "name",
    "path",
    "category",
    "portability",
    "purpose",
    "depends_on",
    "parallel_safe_with",
    "user_invocable",
}


def load_manifest() -> dict[str, object]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def validate_manifest(manifest: dict[str, object]) -> list[str]:
    errors: list[str] = []
    categories = {item["id"]: item for item in manifest["categories"]}
    skills = manifest["skills"]
    skill_names = {item["name"] for item in skills}

    if len(skill_names) != len(skills):
        errors.append("skill names must be unique")

    for skill in skills:
        missing = REQUIRED_SKILL_FIELDS - set(skill)
        if missing:
            errors.append(f"{skill.get('name', '<unknown>')}: missing fields {sorted(missing)}")
        if skill["category"] not in categories:
            errors.append(f"{skill['name']}: unknown category {skill['category']}")
        if not (REPO_ROOT / skill["path"] / "SKILL.md").exists():
            errors.append(f"{skill['name']}: missing path {skill['path']}/SKILL.md")
        if skill.get("stage") is not None and skill["stage"] not in STAGE_LABELS:
            errors.append(f"{skill['name']}: unknown stage {skill['stage']}")
        if skill["user_invocable"] and skill.get("default_invocation_mode") != "direct":
            errors.append(f"{skill['name']}: user_invocable skills must use direct mode")
        if not skill["user_invocable"] and skill.get("default_invocation_mode") == "direct":
            errors.append(f"{skill['name']}: non-public skills cannot use direct mode")
        if skill["name"] == "harness-verify" and skill.get("default_invocation_mode") != "internal_only":
            errors.append("harness-verify must stay internal_only")
        for dep in skill["depends_on"]:
            if dep not in skill_names:
                errors.append(f"{skill['name']}: unknown dependency {dep}")
        for peer in skill["parallel_safe_with"]:
            peer_name = peer.split("（", 1)[0]
            if peer_name not in skill_names:
                errors.append(f"{skill['name']}: unknown parallel peer {peer}")

    for group_kind, groups in manifest["parallel_groups"].items():
        for group in groups:
            for skill_name in group["skills"]:
                if skill_name not in skill_names:
                    errors.append(f"parallel_groups.{group_kind}: unknown skill {skill_name}")

    return errors


def category_map(manifest: dict[str, object]) -> dict[str, dict[str, object]]:
    return {item["id"]: item for item in manifest["categories"]}


def ordered_categories(manifest: dict[str, object]) -> list[dict[str, object]]:
    categories = category_map(manifest)
    return [categories[key] for key in CATEGORY_ORDER if key in categories]


def render_readme_summary(manifest: dict[str, object]) -> str:
    categories = category_map(manifest)
    skills = manifest["skills"]
    counts = Counter(skill["category"] for skill in skills)
    worker_count = sum(1 for skill in skills if categories[skill["category"]]["role"] == "worker")
    non_worker_count = len(skills) - worker_count
    portable_count = sum(1 for skill in skills if skill["portability"] == "portable")
    cc_bound_count = sum(1 for skill in skills if skill["portability"] == "cc-bound")
    invocation_counts = Counter(skill["default_invocation_mode"] for skill in skills)

    lines = [
        README_START,
        "",
        f"- 总计：`{len(skills)}` 个 skill",
        f"- 角色：`{worker_count}` 个 worker，`{non_worker_count}` 个 non-worker",
        f"- 可移植性：`{portable_count}` 个 portable，`{cc_bound_count}` 个 cc-bound",
        f"- 入口模式：`{invocation_counts['direct']}` 个 direct，`{invocation_counts['orchestrated']}` 个 orchestrated，`{invocation_counts['internal_only']}` 个 internal-only",
        "",
        "| 分类 | 数量 | 默认阶段 | 说明 |",
        "|------|------|----------|------|",
    ]

    for category in ordered_categories(manifest):
        stage = STAGE_LABELS.get(category["default_stage"], "按 skill 决定")
        lines.append(
            f"| {category['title']} | {counts.get(category['id'], 0)} | {stage} | role=`{category['role']}` |"
        )

    lines.extend(
        [
            "",
            "详细调度元数据请查看 [`skills/harness/skill-catalog.md`](skills/harness/skill-catalog.md)。",
            "",
            README_END,
        ]
    )
    return "\n".join(lines)


def render_skill_catalog(manifest: dict[str, object]) -> str:
    categories = category_map(manifest)
    skills = manifest["skills"]
    skills_by_category: dict[str, list[dict[str, object]]] = defaultdict(list)
    for skill in skills:
        skills_by_category[skill["category"]].append(skill)

    portable_count = sum(1 for skill in skills if skill["portability"] == "portable")
    cc_bound_count = sum(1 for skill in skills if skill["portability"] == "cc-bound")
    worker_count = sum(1 for skill in skills if categories[skill["category"]]["role"] == "worker")
    non_worker_count = len(skills) - worker_count
    invocation_counts = Counter(skill["default_invocation_mode"] for skill in skills)
    public_skills = [skill for skill in skills if skill["user_invocable"]]

    lines = [
        "# Skill 调度目录",
        "",
        "> 本文件由 `python scripts/generate_manifest_docs.py` 从 `manifest/skills.json` 生成，请勿手工编辑。",
        "",
        "## 角色分类",
        "",
        "| 角色 | 含义 | harness 默认调度 |",
        "|------|------|-----------------|",
        "| `worker` | 可被 harness 分派给子 Agent 执行设计/编码/审计 | 是 |",
        "| `non-worker` | 不被 harness 调度（协调器自身、课程体系） | 否 |",
        "",
        "| 可移植性 | 含义 | 跨项目建议 |",
        "|----------|------|-----------|",
        "| `portable` | 已按 design-oriented spec 重写，有 Do Not Cargo-Cult + Minimal Portable Version | 可安全用于其他项目 |",
        "| `cc-bound` | 仍以 CC 源码解剖为主，缺少迁移指引 | 跨项目使用时需人工判断哪些是 CC 特有实现 |",
        "",
        "**non-worker skill 注册表：**",
        "",
        "| name | role | portability | reason |",
        "|------|------|-------------|--------|",
    ]

    for skill in sorted(skills_by_category["orchestration"], key=lambda item: item["name"]):
        lines.append(
            f"| `{skill['name']}` | `non-worker` | `{skill['portability']}` | {skill['purpose']} |"
        )

    lines.extend(
        [
            "",
            "**特殊 worker skill（harness 基础设施）：**",
            "",
            "| name | role | portability | purpose |",
            "|------|------|-------------|---------|",
        ]
    )

    for skill in skills_by_category["harness-infrastructure"]:
        lines.append(
            f"| `{skill['name']}` | `worker` | `{skill['portability']}` | {skill['purpose']} |"
        )

    lines.extend(
        [
            "",
            f"**当前 skill 总数：{len(skills)} 个** = **{worker_count} 个 worker** + **{non_worker_count} 个 non-worker**。",
            f"当前可移植性分布：`{portable_count}` 个 `portable`，`{cc_bound_count}` 个 `cc-bound`。",
            f"当前入口模式分布：`{invocation_counts['direct']}` 个 `direct`，`{invocation_counts['orchestrated']}` 个 `orchestrated`，`{invocation_counts['internal_only']}` 个 `internal_only`。",
            "",
            "**cc-bound → portable 重写记录：**",
        ]
    )

    for entry in manifest["portability_history"]:
        lines.append(f"- {entry['date']}：{entry['summary']}")

    lines.append("")
    lines.append("Worker 通过 SkillTool 调用，不由 Coordinator 手工复制内容。")
    lines.append("")
    lines.append("## 入口治理")
    lines.append("")
    lines.append("- `direct`：允许用户直接调用，仅保留协调器、课程体系和少数架构专家入口。")
    lines.append("- `orchestrated`：默认通过 `harness` 调度，不建议用户直连。")
    lines.append("- `internal_only`：仅供内部收尾或系统流程使用。")
    lines.append("")
    lines.append("| direct entrypoint | role | category | note |")
    lines.append("|-------------------|------|----------|------|")
    for skill in sorted(public_skills, key=lambda item: item["name"]):
        lines.append(
            f"| `{skill['name']}` | `{categories[skill['category']]['role']}` | {categories[skill['category']]['title']} | {skill['notes'][0] if skill['notes'] else skill['purpose']} |"
        )
    lines.append("")
    lines.append("## 调度元数据")
    lines.append("")

    for category in ordered_categories(manifest):
        category_id = category["id"]
        if category_id in {"orchestration", "harness-infrastructure"}:
            continue
        lines.append(
            f"### {category['title']} `role: {category['role']}` · `default stage: {STAGE_LABELS.get(category['default_stage'], '按 skill 决定')}`"
        )
        lines.append("")
        lines.append("| name | portability | stage | purpose | best_for | depends_on | parallel_safe_with | needs_user_context | invocation |")
        lines.append("|------|-------------|-------|---------|----------|------------|-------------------|-------------------|------------|")

        for skill in sorted(skills_by_category[category_id], key=lambda item: item["name"]):
            depends_on = ", ".join(skill["depends_on"]) if skill["depends_on"] else "无"
            parallel = ", ".join(skill["parallel_safe_with"]) if skill["parallel_safe_with"] else "无"
            stage = STAGE_LABELS.get(skill["stage"], "—") if skill["stage"] else "—"
            best_for = skill["best_for"] or "—"
            needs_user_context = skill["needs_user_context"] or "无"
            lines.append(
                f"| `{skill['name']}` | `{skill['portability']}` | {stage} | {skill['purpose']} | {best_for} | {depends_on} | {parallel} | {needs_user_context} | `{skill['default_invocation_mode']}` |"
            )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_dependency_graph(manifest: dict[str, object]) -> str:
    categories = category_map(manifest)
    skills = manifest["skills"]
    workers = [skill for skill in skills if categories[skill["category"]]["role"] == "worker"]
    dependencies = [skill for skill in workers if skill["depends_on"]]
    roots = sorted(
        skill["name"]
        for skill in workers
        if not skill["depends_on"] and skill["category"] != "harness-infrastructure"
    )

    lines = [
        "# Skill 依赖关系图",
        "",
        "> 本文件由 `python scripts/generate_manifest_docs.py` 从 `manifest/skills.json` 生成，请勿手工编辑。",
        "",
        "## 依赖边",
        "",
        "| skill | depends_on | stage | note |",
        "|------|------------|-------|------|",
    ]

    for skill in sorted(dependencies, key=lambda item: item["name"]):
        stage = STAGE_LABELS.get(skill["stage"], "—") if skill["stage"] else "—"
        note = "多依赖，建议串行调度。" if len(skill["depends_on"]) > 1 else "单一上游依赖。"
        lines.append(f"| `{skill['name']}` | {', '.join(skill['depends_on'])} | {stage} | {note} |")

    lines.extend(
        [
            "",
            "## 无依赖（可独立起步）",
            "",
            "```",
        ]
    )
    lines.extend(roots)
    lines.extend(["```", "", "## 并行安全组", ""])

    lines.append("### 无条件安全并行组")
    lines.append("")
    for group in manifest["parallel_groups"]["always"]:
        lines.append(f"- `{', '.join(group['skills'])}`")
        lines.append(f"  说明：{group['note']}")
    lines.append("")
    lines.append("### 条件并行组（设计可并行，编码需重新判断）")
    lines.append("")
    for group in manifest["parallel_groups"]["design_only"]:
        lines.append(f"- `{', '.join(group['skills'])}`")
        lines.append(f"  说明：{group['note']}")

    lines.extend(
        [
            "",
            "## 依赖决策速查",
            "",
            "1. 命中条件并行组时：设计可并行，编码和审计默认串行。",
            "2. 存在显式依赖边时：按依赖顺序串行。",
            "3. 命中无条件安全并行组时：可并行。",
            "4. 同时操作同一文件或目录时：串行。",
            "5. 仍不确定时：保守串行。",
            "",
        ]
    )

    return "\n".join(lines)


def replace_readme_block(content: str, replacement: str) -> str:
    if README_START not in content or README_END not in content:
        raise ValueError("README is missing generated summary markers.")
    start = content.index(README_START)
    end = content.index(README_END) + len(README_END)
    return content[:start] + replacement + content[end:]


def write_outputs(manifest: dict[str, object]) -> None:
    README_PATH.write_text(
        replace_readme_block(README_PATH.read_text(encoding="utf-8"), render_readme_summary(manifest)),
        encoding="utf-8",
    )
    CATALOG_PATH.write_text(render_skill_catalog(manifest), encoding="utf-8")
    DEPENDENCY_PATH.write_text(render_dependency_graph(manifest), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="validate manifest only")
    args = parser.parse_args()

    manifest = load_manifest()
    errors = validate_manifest(manifest)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    if args.check:
        print("Manifest validation passed.")
        return 0

    write_outputs(manifest)
    print("Generated README summary, skill catalog, and dependency graph.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
