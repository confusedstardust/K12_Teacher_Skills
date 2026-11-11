#!/usr/bin/env python3
"""Validate shared references and required document structure before rendering."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SAFE_ID = re.compile(r"^[A-Za-z0-9_-]+$")
TASK_KEY = re.compile(r"^t\d+$")
STUDENT_LABELS = re.compile(r"差生|学困组|低层|低水平|简单版|培优组|诊断报告|IEP")
IDENTITY_KEYS = {
    "education_stage",
    "grade",
    "subject",
    "duration",
    "curriculum_standard",
    "standard_basis",
    "textbook",
}
COMMON_DIFFERENTIATION_KEYS = {"exit_ticket", "anchor_activity", "reflect_prompt"}


def walk(value, path):
    """Yield nested objects and their zero-based JSON paths."""
    if isinstance(value, dict):
        yield path, value
        for key, child in value.items():
            child_path = f"{path}.{key}" if key.isidentifier() else f"{path}[{json.dumps(key, ensure_ascii=False)}]"
            yield from walk(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk(child, f"{path}[{index}]")


def diagnostic(code, path, message, fix_hint, severity="error"):
    return {"severity": severity, "code": code, "path": path, "message": message, "fix_hint": fix_hint}


def describe(value):
    return {type(None): "null", bool: "布尔值", int: "数字", float: "数字",
            str: "字符串", dict: "对象", list: "数组"}.get(type(value), "未知类型")


def validate_blocks(blocks, path, issues):
    if blocks is None:
        return
    if not isinstance(blocks, list):
        issues.append(diagnostic("INVALID_BLOCK_LIST", path, f"应为内容块数组，实际为{describe(blocks)}。",
                                 '把内容整理成块对象数组，例如 [{"type": "paragraph", "text": "内容"}]。'))
        return
    for index, block in enumerate(blocks):
        block_path = f"{path}[{index}]"
        if not isinstance(block, dict):
            issues.append(diagnostic("INVALID_BLOCK", block_path, f"应为块对象，实际为{describe(block)}。",
                                     "按文档格式把此项改成带 type 的块对象。"))
            continue
        block_type = block.get("type")
        if block_type is not None and not isinstance(block_type, str):
            issues.append(diagnostic("INVALID_BLOCK_TYPE", f"{block_path}.type",
                                     f"块类型应为字符串，实际为{describe(block_type)}。",
                                     "按内容用途设置 type，例如 paragraph、table 或 from_shared。"))
        if block_type == "group":
            validate_blocks(block.get("blocks"), f"{block_path}.blocks", issues)
        elif block_type == "columns":
            for side in ("left", "right"):
                if side in block:
                    validate_blocks(block[side], f"{block_path}.{side}", issues)


def validate_diagnostics(path: Path, mode: str) -> list[dict[str, str]]:
    issues = []
    try:
        source = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [diagnostic("INVALID_JSON", "$", f"第 {exc.lineno} 行第 {exc.colno} 列不是有效 JSON。",
                           "检查该位置附近的引号、逗号或括号，并以无 BOM 的 UTF-8 保存后重新校验。")]
    except (OSError, UnicodeError):
        return [diagnostic("UNREADABLE_SOURCE", "$", "无法读取 UTF-8 材料文件。",
                           "确认文件存在且可读取，并保存为 UTF-8 JSON。")]
    except RecursionError:
        return [diagnostic("SOURCE_TOO_DEEP", "$", "材料嵌套层级过深。",
                           "减少嵌套分组，保留教学内容并重新校验。")]
    if not isinstance(source, dict):
        return [diagnostic("INVALID_ROOT", "$", f"顶层应为对象，实际为{describe(source)}。",
                           "用一个对象组织材料，包含 shared 对象和 documents 数组。")]

    shared = source.get("shared")
    documents = source.get("documents")
    if not isinstance(shared, dict):
        issues.append(diagnostic("INVALID_SHARED", "shared", f"应为对象，实际为{describe(shared)}。",
                                 "在 shared 对象里放课程信息和供多份文档引用的内容。"))
    if not isinstance(documents, list) or not documents:
        issues.append(diagnostic("INVALID_DOCUMENT_LIST", "documents", "应为非空文档数组。",
                                 "按所选教学模式添加完整文档对象，再重新校验。"))
    if issues:
        return issues

    for key in sorted(IDENTITY_KEYS - shared.keys()):
        issues.append(diagnostic("MISSING_IDENTITY_FIELD", f"shared.{key}", "缺少课程身份字段。",
                                 "用原教案或教师已提供的信息补齐，无法确定时按 Skill 的流程确认。"))

    ids = {}
    valid_documents = []
    for index, document in enumerate(documents):
        doc_path = f"documents[{index}]"
        if not isinstance(document, dict):
            issues.append(diagnostic("INVALID_DOCUMENT", doc_path, f"应为文档对象，实际为{describe(document)}。",
                                     "将此项改成含 id、audience 和 sections 的文档对象。"))
            continue
        before = len(issues)
        doc_id = document.get("id")
        if not isinstance(doc_id, str) or not SAFE_ID.fullmatch(doc_id):
            issues.append(diagnostic("INVALID_DOCUMENT_ID", f"{doc_path}.id", "文档 ID 缺失或格式不合法。",
                                     "使用模式要求的 ID，或使用仅含字母、数字、下划线和连字符的唯一名称。"))
        elif doc_id in ids:
            issues.append(diagnostic("DUPLICATE_DOCUMENT_ID", f"{doc_path}.id", f"与 {ids[doc_id]} 重复使用 {doc_id}。",
                                     "合并重复文档，或为不同文档分配正确且唯一的 ID。"))
        else:
            ids[doc_id] = f"{doc_path}.id"

        if document.get("audience") not in ("teacher", "student"):
            issues.append(diagnostic("INVALID_AUDIENCE", f"{doc_path}.audience",
                                     f"应为 teacher 或 student，实际为{describe(document.get('audience'))}。",
                                     "教师用文档填 teacher，学生任务单填 student。"))
        sections = document.get("sections")
        if not isinstance(sections, list) or not sections:
            issues.append(diagnostic("INVALID_SECTIONS", f"{doc_path}.sections", "应为非空章节数组。",
                                     "按文档格式补上章节，每个章节包含 heading 和 blocks。"))
        else:
            for section_index, section in enumerate(sections):
                section_path = f"{doc_path}.sections[{section_index}]"
                if not isinstance(section, dict):
                    issues.append(diagnostic("INVALID_SECTION", section_path, f"应为章节对象，实际为{describe(section)}。",
                                             "把此项改成含 heading 和 blocks 的章节对象。"))
                elif "blocks" in section:
                    validate_blocks(section["blocks"], f"{section_path}.blocks", issues)
        if len(issues) == before:
            valid_documents.append((doc_path, document))

    shared_keys = set(shared)
    references = {}
    for doc_path, document in valid_documents:
        reference_keys = set()
        for block_path, block in walk(document, doc_path):
            if block.get("type") != "from_shared":
                continue
            key = block.get("key")
            if not isinstance(key, str) or not key.strip():
                issues.append(diagnostic("INVALID_SHARED_KEY", f"{block_path}.key", "共享引用缺少有效的键。",
                                         "填写 shared 中对应任务的键，例如 t1。"))
            elif key not in shared_keys:
                issues.append(diagnostic("MISSING_SHARED_REFERENCE", f"{block_path}.key", f"找不到 shared 中的键 {key!r}。",
                                         "改用原本应引用的共享键，或依据原教案补回该共享任务。"))
            else:
                reference_keys.add(key)
        references[doc_path] = reference_keys

    detected_mode = ("differentiation" if "teacher_plan" in ids else "planning") if mode == "auto" else mode
    if detected_mode == "planning":
        required = {"lesson_plan", "observation_template"}
    elif detected_mode == "differentiation":
        required = {"teacher_plan", "worksheet_group_a", "worksheet_group_b", "worksheet_group_c"}
    else:
        issues.append(diagnostic("INVALID_MODE", "mode", "未知教学模式。",
                                 "使用 planning、differentiation 或 auto。"))
        return issues

    missing = sorted(required - ids.keys())
    if missing:
        issues.append(diagnostic("MISSING_DOCUMENTS", "documents", "缺少文档：" + "、".join(missing),
                                 "按当前模式补上缺失文档，确认各自的 id 和 audience。"))

    if detected_mode == "planning":
        for doc_path, document in valid_documents:
            if document["id"] != "lesson_plan":
                continue
            duration = shared.get("duration")
            if type(duration) not in (int, float):
                continue
            minutes = sum(block["minutes"] for _, block in walk(document, doc_path)
                          if block.get("type") == "phase_header" and type(block.get("minutes")) in (int, float))
            if minutes and minutes != duration:
                issues.append(diagnostic("DURATION_MISMATCH", "shared.duration",
                                         f"计划 {duration} 分钟，{doc_path} 的教学环节共 {minutes} 分钟。",
                                         "按教师确认的课时调整环节 minutes，再检查各环节合计。"))
    else:
        for key in sorted(COMMON_DIFFERENTIATION_KEYS - shared_keys):
            issues.append(diagnostic("MISSING_COMMON_TASK", f"shared.{key}", "缺少全班共同任务。",
                                     "根据原课例补齐共同任务，再让三份学生任务单引用同一键。"))
        task_keys = {key for key in shared_keys if TASK_KEY.fullmatch(key)}
        if not task_keys:
            issues.append(diagnostic("NO_SHARED_CORE_TASK", "shared", "未发现 t1、t2 等共享核心任务键。",
                                     "如原课例有共同核心任务，把它整理到 shared 供各组引用。", "warning"))
        expected_refs = task_keys | (COMMON_DIFFERENTIATION_KEYS & shared_keys)
        for doc_path, document in valid_documents:
            if document["audience"] != "student":
                continue
            for key in sorted(expected_refs - references[doc_path]):
                issues.append(diagnostic("MISSING_COMMON_REFERENCE", f"{doc_path}.sections",
                                         f"{document['id']} 未引用共同任务 {key}。",
                                         f'在对应章节加入 {{"type":"from_shared","key":"{key}"}}，沿用其他组的任务。'))
            found = sorted(set(STUDENT_LABELS.findall(json.dumps(document, ensure_ascii=False))))
            if found:
                issues.append(diagnostic("STUDENT_LABEL", f"{doc_path}.sections",
                                         "学生材料含能力或诊断标签：" + "、".join(found),
                                         "保留任务和支架，用中性的任务单名称替换学生标签。"))
    return issues


def format_diagnostic(issue: dict[str, str]) -> str:
    return f"{issue['path']}：{issue['message']} 修复：{issue['fix_hint']}"


def validate(path: Path, mode: str) -> tuple[list[str], list[str]]:
    issues = validate_diagnostics(path, mode)
    return ([format_diagnostic(issue) for issue in issues if issue["severity"] == "error"],
            [format_diagnostic(issue) for issue in issues if issue["severity"] == "warning"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument(
        "--mode",
        choices=["auto", "planning", "differentiation"],
        default="auto",
    )
    parser.add_argument("--json", action="store_true", help="输出结构化诊断 JSON")
    args = parser.parse_args()
    diagnostics = validate_diagnostics(args.input, args.mode)
    errors = [format_diagnostic(issue) for issue in diagnostics if issue["severity"] == "error"]
    warnings = [format_diagnostic(issue) for issue in diagnostics if issue["severity"] == "warning"]
    if args.json:
        print(json.dumps({"valid": not errors, "errors": errors, "warnings": warnings,
                          "diagnostics": diagnostics}, ensure_ascii=False))
        return 1 if errors else 0
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    if errors:
        return 1
    print(f"valid: {args.input} ({args.mode})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
