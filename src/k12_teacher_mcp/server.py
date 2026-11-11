"""stdio MCP server. No model calls; the host Agent designs the lessons."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any, Literal
from uuid import uuid4

from mcp.server.fastmcp import FastMCP

Mode = Literal["planning", "differentiation"]
SUBJECT_FILES = {
    "语文": "subject-chinese.md",
    "数学": "subject-mathematics.md",
    "英语": "subject-english.md",
    **dict.fromkeys(["科学", "物理", "化学", "生物", "生物学"], "subject-science.md"),
    **dict.fromkeys(["道德与法治", "思想政治", "历史", "地理"], "subject-humanities.md"),
    **dict.fromkeys(["信息科技", "信息技术", "劳动", "艺术", "音乐", "美术", "体育", "体育与健康"], "subject-practice-arts.md"),
}

mcp = FastMCP(
    "k12_teacher_mcp",
    instructions=(
        "中国K-12备课、写教案、设计学习单、生成Word教案与分层教学。"
        "收到这类请求时，先发现 k12-teacher 的 get_teaching_guidance 工具；"
        "如果工具按需加载，使用宿主的工具搜索。确定学科后先调用该工具，读取返回的工作流、"
        "参考及schema，再由你设计材料数据。不要编造课标引文。调用 validate_teaching_materials，"
        "修正错误后调用 render_teaching_documents。服务不调用模型、不联网查课标。"
        "输出文件在运行本服务的电脑上；请根据宿主能力提供文件链接或打开文件。"
    ),
)


CASE_GUIDE = "references/narrativeos-case-guidance.md"


def skill_dir(mode: Mode) -> Path:
    """Use wheel assets after installation, original sources during development."""
    bundled = Path(__file__).parent / "assets" / mode
    if bundled.is_dir():
        return bundled
    root = Path(__file__).resolve().parents[2]
    path = root / f"k12-teacher-skill-{mode}"
    if not path.is_dir():
        raise ValueError("教学资源缺失，请重新安装完整的 k12-teacher-mcp 包。")
    return path


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
def get_teaching_guidance(mode: Mode, subjects: list[str]) -> dict[str, Any]:
    """为中国K-12备课、写教案、设计学习单、生成Word教案或分层教学提供工作流。

    生成材料之前先调用。planning=从零备课，differentiation=将已有教案改成差异化方案。

    subjects 填实际学科中文名称，如["数学"]；跨学科填多个。返回完整教学规则、
    所需参考、材料schema和样例。由宿主Agent据此提问、设计内容并生成shared/documents数据，
    再调用校验与渲染工具；本工具不会自动生成教学内容。
    """
    if not subjects or any(subject not in SUBJECT_FILES for subject in subjects):
        raise ValueError("subjects 必须包含支持的学科：" + "、".join(SUBJECT_FILES))
    directory = skill_dir(mode)
    files = [
        "SKILL.md",
        "references/curriculum-grounding.md",
        "references/document-schema.md",
    ]
    if mode == "planning":
        files += [f"references/{SUBJECT_FILES[subject]}" for subject in subjects]
        files += ["references/example_lesson.json"]
    else:
        files += ["references/differentiation-principles.md", "references/subject-routes.md",
                  "references/example_differentiation.json"]
    guidance_files = {name: (directory / name).read_text(encoding="utf-8") for name in dict.fromkeys(files)}
    guidance_files[CASE_GUIDE] = (skill_dir("planning") / CASE_GUIDE).read_text(encoding="utf-8")
    return {
        "mode": mode,
        "subjects": subjects,
        "execution": (
            "你是执行教学设计的Agent。下列文件中的相对路径已由本工具提供对应内容。"
            "不要执行SKILL中的shell命令；改用validate_teaching_materials和render_teaching_documents。"
            "服务端执行脚本，不要求宿主安装Skill。课程依据须由你结合用户材料或可用检索能力核实。"
            "最终提交的材料必须是顶层shared与documents数组；不是只有自然语言教案。"
        ),
        "files": guidance_files,
        "next_step": "依照教学工作流与教师交互，设计材料数据，然后调用validate_teaching_materials。",
    }


def run_script(mode: Mode, name: str, arguments: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            [sys.executable, str(skill_dir(mode) / "scripts" / name), *arguments],
            stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8", timeout=120,
            env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError("材料处理超过120秒，请缩小单次材料规模后重试。") from exc


def check_source(source: Path, mode: Mode) -> dict[str, Any]:
    result = run_script(mode, "validate_material_source.py", [str(source), "--mode", mode])
    errors, warnings = [], []
    for line in result.stderr.splitlines():
        if line.startswith("warning: "):
            warnings.append(line.removeprefix("warning: "))
        elif line.startswith("error: "):
            errors.append(line.removeprefix("error: "))
    if result.returncode and not errors:
        errors.append("材料结构无法处理，请检查shared、documents及各文档字段类型。")
    return {"valid": result.returncode == 0, "errors": errors, "warnings": warnings,
            "scope": "结构、共享引用及脚本已有规则检查；不证明课标真实性或教学质量。"}


def write_source(path: Path, materials: dict[str, Any]) -> None:
    payload = json.dumps(materials, ensure_ascii=False, allow_nan=False)
    if len(payload.encode("utf-8")) > 5_000_000:
        raise ValueError("单次材料超过5MB，请拆分课时。")
    path.write_text(payload, encoding="utf-8")


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
def validate_teaching_materials(mode: Mode, materials: dict[str, Any]) -> dict[str, Any]:
    """校验教学材料对象（顶层shared和documents数组）。返回valid/errors/warnings。

    必须先用get_teaching_guidance获取schema；错误修正后再生成Word。不会调用模型或联网。
    """
    with tempfile.TemporaryDirectory(prefix="k12-validate-") as temporary:
        source = Path(temporary) / "materials.json"
        write_source(source, materials)
        return check_source(source, mode)


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False,
                       "idempotentHint": False, "openWorldHint": False})
def render_teaching_documents(mode: Mode, materials: dict[str, Any]) -> dict[str, Any]:
    """校验通过后生成整套Word和HTML。输入与校验工具相同，每次创建独立目录，不覆盖旧版本。

    返回本机绝对路径和file URI；不提供公网下载地址。只向教师交付Word，JSON/HTML用于修订和预览。
    成功时先交付Word，再按返回的post_delivery_guidance调用宿主的可点击选择工具或展示链接。
    修改shared/documents后重新调用，勿直接修改生成的Word。无效材料不会生成文件。
    """
    with tempfile.TemporaryDirectory(prefix="k12-render-") as temporary:
        staging = Path(temporary)
        source = staging / "materials.json"
        write_source(source, materials)
        validation = check_source(source, mode)
        if not validation["valid"]:
            return {"status": "validation_failed", **validation, "files": []}
        result = run_script(mode, "render_documents.py",
                            [str(source), "--format", "both", "--outdir", str(staging)])
        if result.returncode:
            raise ValueError("文档渲染失败，请检查block类型和字段是否符合document-schema。详情："
                             + result.stderr[-2000:])
        expected = [staging / f"{doc['id']}.{extension}"
                    for doc in materials["documents"] for extension in ("docx", "html")]
        if any(not path.is_file() or not path.stat().st_size for path in expected):
            raise ValueError("生成文件不完整，未交付；请检查文档ID与材料结构。")
        base = Path(os.environ.get("K12_TEACHER_OUTPUT_DIR", str(Path.home() / "K12-Teacher-Outputs"))).expanduser().resolve()
        output = base / uuid4().hex
        output.mkdir(parents=True, exist_ok=False)
        files = []
        for path in [source, *expected]:
            target = output / path.name
            target.write_bytes(path.read_bytes())
            files.append({"name": target.name, "path": str(target), "uri": target.as_uri(),
                          "bytes": target.stat().st_size,
                          "role": "deliverable" if target.suffix == ".docx" else "revision_or_preview"})
        return {"status": "ok", "directory": str(output), "files": files,
                "warnings": validation["warnings"],
                "delivery": (
                    "先交付Word附件或本机文件链接。若有present_files，先调用它；成功后继续按"
                    "post_delivery_guidance调用宿主的可点击选择工具，再发送最终回复。"
                ),
                "post_delivery_guidance": (skill_dir("planning") / CASE_GUIDE).read_text(encoding="utf-8")}


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
