#!/usr/bin/env python3
"""Bootstrap manifest/skills.json from legacy docs and skill frontmatter."""

from __future__ import annotations

import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = REPO_ROOT / "skills"
CATALOG_PATH = SKILLS_ROOT / "harness" / "skill-catalog.md"
OUTPUT_PATH = REPO_ROOT / "manifest" / "skills.json"

CATEGORIES = [
    {
        "id": "orchestration",
        "title": "协调层",
        "role": "non-worker",
        "default_stage": None,
        "default_target_path_policy": "not_applicable",
        "default_value_assessment": "retain",
        "default_invocation_mode": "direct",
    },
    {
        "id": "harness-infrastructure",
        "title": "Harness 基础设施层",
        "role": "worker",
        "default_stage": None,
        "default_target_path_policy": "coordinator_defined",
        "default_value_assessment": "situational",
        "default_invocation_mode": "internal_only",
    },
    {
        "id": "foundation-contracts",
        "title": "基础契约层",
        "role": "worker",
        "default_stage": "stage-0-contracts",
        "default_target_path_policy": "coordinator_defined",
        "default_value_assessment": "retain",
        "default_invocation_mode": "orchestrated",
    },
    {
        "id": "agent-core",
        "title": "Agent 核心层",
        "role": "worker",
        "default_stage": None,
        "default_target_path_policy": "coordinator_defined",
        "default_value_assessment": "retain",
        "default_invocation_mode": "orchestrated",
    },
    {
        "id": "capability-extensions",
        "title": "能力扩展层",
        "role": "worker",
        "default_stage": None,
        "default_target_path_policy": "coordinator_defined",
        "default_value_assessment": "retain",
        "default_invocation_mode": "orchestrated",
    },
    {
        "id": "production",
        "title": "生产化层",
        "role": "worker",
        "default_stage": "stage-7-production",
        "default_target_path_policy": "coordinator_defined",
        "default_value_assessment": "retain",
        "default_invocation_mode": "orchestrated",
    },
    {
        "id": "long-session",
        "title": "长会话扩展层",
        "role": "worker",
        "default_stage": "stage-3-long-session",
        "default_target_path_policy": "coordinator_defined",
        "default_value_assessment": "retain",
        "default_invocation_mode": "orchestrated",
    },
    {
        "id": "memory-extensions",
        "title": "记忆扩展层",
        "role": "worker",
        "default_stage": "stage-4-memory",
        "default_target_path_policy": "coordinator_defined",
        "default_value_assessment": "retain",
        "default_invocation_mode": "orchestrated",
    },
    {
        "id": "ide-input",
        "title": "IDE / 输入扩展层",
        "role": "worker",
        "default_stage": "stage-5-extensibility",
        "default_target_path_policy": "coordinator_defined",
        "default_value_assessment": "retain",
        "default_invocation_mode": "orchestrated",
    },
    {
        "id": "enterprise",
        "title": "企业 / 生产化扩展层",
        "role": "worker",
        "default_stage": "stage-8-enterprise",
        "default_target_path_policy": "coordinator_defined",
        "default_value_assessment": "retain",
        "default_invocation_mode": "orchestrated",
    },
    {
        "id": "methodology",
        "title": "方法论",
        "role": "worker",
        "default_stage": None,
        "default_target_path_policy": "coordinator_defined",
        "default_value_assessment": "situational",
        "default_invocation_mode": "direct",
    },
]

SECTION_TO_CATEGORY = {
    "基础契约层": "foundation-contracts",
    "Agent 核心层": "agent-core",
    "能力扩展层": "capability-extensions",
    "生产化层": "production",
    "长会话扩展层": "long-session",
    "记忆扩展层": "memory-extensions",
    "IDE / 输入扩展层": "ide-input",
    "企业 / 生产化扩展层": "enterprise",
    "方法论": "methodology",
}

PORTABLE_SKILLS = {
    "harness",
    "harness-lite",
    "agent-architecture-curriculum",
    "harness-verify",
    "api-client-layer",
    "auth-identity",
    "config-cascade",
    "instruction-file-system",
    "harness-entry-points",
    "unified-tool-interface",
    "agent-loop",
    "layered-permission",
    "context-engineering",
    "model-routing",
    "mcp-runtime",
    "telemetry-pipeline",
    "process-lifecycle",
    "compact-system",
    "session-memory",
    "team-memory-sync",
    "magic-docs",
    "ide-feedback-loop",
    "tip-system",
    "voice-input",
    "runtime-summaries",
    "platform-integration",
    "policy-limits",
    "remote-managed-settings",
    "settings-sync",
}

DIRECT_ENTRY_SKILLS = {
    "harness",
    "harness-lite",
    "agent-architecture-curriculum",
    "unified-tool-interface",
    "config-cascade",
    "instruction-file-system",
    "harness-entry-points",
    "architecture-invariants",
    "eval-driven-design",
}

INTERNAL_ONLY_SKILLS = {
    "harness-verify",
}

STAGE_BY_SKILL = {
    "unified-tool-interface": "stage-0-contracts",
    "config-cascade": "stage-0-contracts",
    "api-client-layer": "stage-0-contracts",
    "auth-identity": "stage-0-contracts",
    "instruction-file-system": "stage-0-contracts",
    "harness-entry-points": "stage-0-contracts",
    "agent-loop": "stage-1-minimal-loop",
    "layered-permission": "stage-2-security",
    "agent-tool-budget": "stage-2-security",
    "command-sandbox": "stage-2-security",
    "context-engineering": "stage-3-long-session",
    "agent-resilience": "stage-3-long-session",
    "concurrent-dispatch": "stage-3-long-session",
    "compact-system": "stage-3-long-session",
    "session-memory": "stage-3-long-session",
    "agent-memory": "stage-4-memory",
    "agent-reflection": "stage-4-memory",
    "session-recovery": "stage-4-memory",
    "team-memory-sync": "stage-4-memory",
    "magic-docs": "stage-4-memory",
    "plugin-loading": "stage-5-extensibility",
    "event-hook-system": "stage-5-extensibility",
    "model-routing": "stage-5-extensibility",
    "plan-mode": "stage-5-extensibility",
    "ide-feedback-loop": "stage-5-extensibility",
    "tip-system": "stage-5-extensibility",
    "mcp-runtime": "stage-5-extensibility",
    "multi-agent-design": "stage-6-multi-agent",
    "startup-optimization": "stage-7-production",
    "telemetry-pipeline": "stage-7-production",
    "feature-flag-system": "stage-7-production",
    "process-lifecycle": "stage-7-production",
    "prompt-cache-economics": "stage-7-production",
    "runtime-summaries": "stage-7-production",
    "platform-integration": "stage-7-production",
    "voice-input": "stage-7-production",
    "policy-limits": "stage-8-enterprise",
    "remote-managed-settings": "stage-8-enterprise",
    "settings-sync": "stage-8-enterprise",
}

PARALLEL_GROUPS = {
    "always": [
        {
            "skills": [
                "unified-tool-interface",
                "config-cascade",
                "api-client-layer"
            ],
            "note": "基础契约层核心模块，可同轮并行。"
        },
        {
            "skills": [
                "auth-identity",
                "instruction-file-system"
            ],
            "note": "共享 config-cascade 但彼此独立。"
        },
        {
            "skills": [
                "layered-permission",
                "agent-tool-budget"
            ],
            "note": "都依赖 unified-tool-interface，但互不阻塞。"
        },
        {
            "skills": [
                "plugin-loading",
                "event-hook-system"
            ],
            "note": "扩展点与插件协议可以并行。"
        },
        {
            "skills": [
                "model-routing",
                "plan-mode"
            ],
            "note": "分别建立模型路由与计划审批层。"
        },
        {
            "skills": [
                "startup-optimization",
                "telemetry-pipeline",
                "feature-flag-system"
            ],
            "note": "生产化基础设施互无直接依赖。"
        },
        {
            "skills": [
                "team-memory-sync",
                "magic-docs"
            ],
            "note": "都位于记忆扩展层，但功能边界独立。"
        },
        {
            "skills": [
                "ide-feedback-loop",
                "tip-system",
                "voice-input"
            ],
            "note": "IDE / 输入相关能力可独立推进。"
        },
        {
            "skills": [
                "policy-limits",
                "remote-managed-settings",
                "settings-sync"
            ],
            "note": "都依赖 auth-identity，但彼此独立。"
        },
        {
            "skills": [
                "runtime-summaries",
                "platform-integration",
                "voice-input"
            ],
            "note": "面向运行体验的能力可并行建设。"
        }
    ],
    "design_only": [
        {
            "skills": [
                "agent-memory",
                "agent-reflection"
            ],
            "note": "设计阶段可并行；编码阶段 reflection 依赖 memory。"
        },
        {
            "skills": [
                "compact-system",
                "session-memory"
            ],
            "note": "设计阶段可并行；编码阶段 session-memory 依赖 compact-system。"
        },
        {
            "skills": [
                "agent-loop",
                "concurrent-dispatch"
            ],
            "note": "前置 unified-tool-interface 完成后，设计可并行；编码需视接口稳定性判断。"
        }
    ]
}


def parse_frontmatter() -> dict[str, dict[str, object]]:
    meta: dict[str, dict[str, object]] = {}
    for skill_file in sorted(SKILLS_ROOT.glob("*/SKILL.md")):
        text = skill_file.read_text(encoding="utf-8")
        name = skill_file.parent.name
        inv_match = re.search(r"^user-invocable:\s*(true|false)", text, re.M)
        meta[name] = {
            "path": str(skill_file.parent.relative_to(REPO_ROOT)).replace("\\", "/"),
            "user_invocable": inv_match.group(1) == "true" if inv_match else False,
        }
    return meta


def parse_catalog_tables() -> dict[str, dict[str, object]]:
    text = CATALOG_PATH.read_text(encoding="utf-8")
    section = None
    in_dispatch_metadata = False
    skills: dict[str, dict[str, object]] = {}

    for line in text.splitlines():
        if line.startswith("## 调度元数据"):
            in_dispatch_metadata = True
            continue
        if not in_dispatch_metadata:
            continue
        if line.startswith("### "):
            section = line[4:].split(" `role")[0].strip()
            continue
        if not line.startswith("| `"):
            continue

        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) == 9:
            name = cells[0].strip("`")
            purpose = cells[3]
            best_for = None if cells[4] == "—" else cells[4]
            depends_on = [] if cells[5].startswith("无") or cells[5] == "—" else [item.strip() for item in cells[5].split(",")]
            parallel_safe_with = [] if cells[6].startswith("无") or cells[6] == "—" else [item.strip() for item in cells[6].split(",")]
            needs_user_context = None if cells[7].startswith("无") or cells[7] == "—" else cells[7]
        elif len(cells) == 6:
            name = cells[0].strip("`")
            purpose = cells[1]
            best_for = None if cells[2] == "—" else cells[2]
            depends_on = [] if cells[3].startswith("无") or cells[3] == "—" else [item.strip() for item in cells[3].split(",")]
            parallel_safe_with = [] if cells[4].startswith("无") or cells[4] == "—" else [item.strip() for item in cells[4].split(",")]
            needs_user_context = None if cells[5].startswith("无") or cells[5] == "—" else cells[5]
        else:
            continue

        skills[name] = {
            "category": SECTION_TO_CATEGORY[section],
            "purpose": purpose,
            "best_for": best_for,
            "depends_on": depends_on,
            "parallel_safe_with": parallel_safe_with,
            "needs_user_context": needs_user_context,
        }

    skills["harness"] = {
        "category": "orchestration",
        "purpose": "Coordinator 自身，只生成计划和汇总，不作为 worker 调度",
        "best_for": None,
        "depends_on": [],
        "parallel_safe_with": [],
        "needs_user_context": None,
    }
    skills["harness-lite"] = {
        "category": "orchestration",
        "purpose": "Lite Coordinator：只处理叶子模块、小范围补丁与 <= 2 文件的快路径任务",
        "best_for": None,
        "depends_on": [],
        "parallel_safe_with": [],
        "needs_user_context": None,
    }
    skills["agent-architecture-curriculum"] = {
        "category": "orchestration",
        "purpose": "课程化文档生成器，不作为设计/编码/审计 worker 使用",
        "best_for": None,
        "depends_on": [],
        "parallel_safe_with": [],
        "needs_user_context": None,
    }
    skills["harness-verify"] = {
        "category": "harness-infrastructure",
        "purpose": "编码/审计轮完成后的验证 Worker：执行 commands、生成 diff、产出 verification.md + scorecard.json + commands.log。",
        "best_for": "编码/审计轮的最后一个串行验证步骤",
        "depends_on": [],
        "parallel_safe_with": [],
        "needs_user_context": None,
    }
    return skills


def category_defaults() -> dict[str, dict[str, object]]:
    return {item["id"]: item for item in CATEGORIES}


def build_manifest() -> dict[str, object]:
    frontmatter = parse_frontmatter()
    catalog = parse_catalog_tables()
    defaults = category_defaults()
    skills = []

    for name in sorted(frontmatter):
        info = catalog[name]
        category = defaults[info["category"]]
        user_invocable = name in DIRECT_ENTRY_SKILLS
        if name in INTERNAL_ONLY_SKILLS:
            default_mode = "internal_only"
        elif user_invocable:
            default_mode = "direct"
        else:
            default_mode = "orchestrated"
        skill = {
            "name": name,
            "path": frontmatter[name]["path"],
            "category": info["category"],
            "stage": STAGE_BY_SKILL.get(name, category["default_stage"]),
            "portability": "portable" if name in PORTABLE_SKILLS else "cc-bound",
            "purpose": info["purpose"],
            "best_for": info["best_for"],
            "depends_on": info["depends_on"],
            "parallel_safe_with": info["parallel_safe_with"],
            "parallel_mode": "contextual" if name in {
                "agent-loop",
                "agent-memory",
                "agent-reflection",
                "compact-system",
                "session-memory",
                "concurrent-dispatch"
            } else "always",
            "needs_user_context": info["needs_user_context"],
            "user_invocable": user_invocable,
            "default_invocation_mode": default_mode,
            "target_path_policy": category["default_target_path_policy"],
            "value_assessment": category["default_value_assessment"] if name != "harness-verify" else "situational",
            "notes": [],
        }
        if name == "harness-verify":
            skill["notes"] = ["编码/审计轮必须作为最后一个串行组调度。"]
        elif user_invocable and category["role"] == "worker":
            skill["notes"] = ["专家直连入口：用于定向架构咨询，不替代 harness 的 state/trace 治理。"]
        elif default_mode == "orchestrated":
            skill["notes"] = ["默认通过 harness 调度，不建议用户直接调用。"]
        skills.append(skill)

    return {
        "version": 1,
        "categories": CATEGORIES,
        "skills": skills,
        "parallel_groups": PARALLEL_GROUPS,
        "portability_history": [
            {
                "date": "initial",
                "summary": "初始：24 个 cc-bound + 18 个 portable。"
            },
            {
                "date": "2026-04-04",
                "summary": "agent-loop / layered-permission / context-engineering 重写为 portable，变为 21 + 21。"
            },
            {
                "date": "2026-04-15",
                "summary": "阶段 0 根节点 unified-tool-interface / config-cascade / instruction-file-system / harness-entry-points 改写为 portable-first，入口治理同步收口到 8 个 direct / 36 个 orchestrated / 1 个 internal-only。"
            },
            {
                "date": "2026-04-15",
                "summary": "新增 harness-lite 作为叶子模块快路径协调器，用于 <= 2 文件、无阶段跳转的小任务。"
            }
        ]
    }


def main() -> None:
    manifest = build_manifest()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
