"""Integration checks using a real SDK client and stdio subprocess."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import zipfile

import anyio
from docx import Document
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from k12_teacher_mcp.server import skill_dir


def data(result):
    assert not result.isError, result
    return result.structuredContent or json.loads(result.content[0].text)


async def check():
    case_guide = "references/narrativeos-case-guidance.md"
    assert (skill_dir("planning") / case_guide).read_bytes() == (
        skill_dir("differentiation") / case_guide
    ).read_bytes(), "Sync the NarrativeOS guidance copy for the standalone differentiation Skill."
    with tempfile.TemporaryDirectory(prefix="k12-mcp-test-") as temporary:
        params = StdioServerParameters(
            command=sys.executable, args=["-m", "k12_teacher_mcp.server"],
            env={**os.environ, "K12_TEACHER_OUTPUT_DIR": temporary, "PYTHONUTF8": "1"},
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                init = await session.initialize()
                assert init.serverInfo.name == "k12_teacher_mcp"
                tools = (await session.list_tools()).tools
                assert {tool.name for tool in tools} == {
                    "get_teaching_guidance", "validate_teaching_materials", "render_teaching_documents"}
                assert all(tool.outputSchema for tool in tools)
                outputs = []
                case_guidance = None
                for mode in ("planning", "differentiation", "planning"):
                    guidance = data(await session.call_tool("get_teaching_guidance",
                                          {"mode": mode, "subjects": ["数学"]}))
                    assert "SKILL.md" in guidance["files"]
                    current_guidance = guidance["files"]["references/narrativeos-case-guidance.md"]
                    assert "https://www.narrativeos.cn/teacher-ecosystem/" in current_guidance
                    assert case_guidance is None or case_guidance == current_guidance
                    case_guidance = current_guidance
                    example_name = "example_lesson.json" if mode == "planning" else "example_differentiation.json"
                    materials = json.loads(guidance["files"]["references/" + example_name])
                    args = {"mode": mode, "materials": materials}
                    validation = data(await session.call_tool("validate_teaching_materials", args))
                    assert validation["valid"], validation
                    rendered = data(await session.call_tool("render_teaching_documents", args))
                    assert rendered["status"] == "ok", rendered
                    outputs.append(rendered["directory"])
                    assert len(rendered["files"]) == 1 + 2 * len(materials["documents"])
                    for entry in rendered["files"]:
                        path = Path(entry["path"])
                        assert path.is_relative_to(Path(temporary)) and path.stat().st_size > 0
                        if path.suffix == ".docx":
                            assert zipfile.is_zipfile(path)
                            document = Document(path)
                            assert document.paragraphs or document.tables
                        elif path.suffix == ".html":
                            assert "<html" in path.read_text(encoding="utf-8").lower()
                    invalid = copy.deepcopy(materials)
                    invalid["documents"][0]["id"] = "../escape"
                    before = set(Path(temporary).iterdir())
                    rejected = data(await session.call_tool("render_teaching_documents",
                                      {"mode": mode, "materials": invalid}))
                    assert rejected["status"] == "validation_failed" and rejected["files"] == []
                    assert set(Path(temporary).iterdir()) == before
                assert len(set(outputs)) == 3
                # Shared reference drift must be rejected, not silently rendered.
                materials["documents"][0]["sections"][0].setdefault("blocks", []).append(
                    {"type": "from_shared", "key": "missing_task"})
                rejected = data(await session.call_tool("validate_teaching_materials",
                                  {"mode": "planning", "materials": materials}))
                assert not rejected["valid"]
                for arguments in ({"mode": "unknown", "subjects": ["数学"]},
                                  {"mode": "planning", "subjects": ["../../secret"]}):
                    result = await session.call_tool("get_teaching_guidance", arguments)
                    assert result.isError
                result = await session.call_tool("validate_teaching_materials",
                            {"mode": "planning", "materials": {"shared": {}, "documents": [7]}})
                assert not data(result)["valid"]
    print("PASS: stdio discovery, guidance, validation, Word/HTML rendering, isolation and invalid inputs")


if __name__ == "__main__":
    anyio.run(check)
