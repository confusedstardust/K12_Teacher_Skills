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
                    malformed = copy.deepcopy(materials)
                    malformed["documents"].append(7)
                    report = data(await session.call_tool("validate_teaching_materials",
                                  {"mode": mode, "materials": malformed}))
                    assert not report["valid"]
                    assert any(issue["code"] == "INVALID_DOCUMENT"
                               and issue["path"] == f"documents[{len(materials['documents'])}]"
                               and issue["fix_hint"] for issue in report["diagnostics"]), report
                    if mode == "planning":
                        materials["shared"]["duration"] += 5
                        report = data(await session.call_tool("validate_teaching_materials", args))
                        assert not report["valid"]
                        assert any(issue["code"] == "DURATION_MISMATCH"
                                   and issue["path"] == "shared.duration"
                                   for issue in report["diagnostics"]), report
                        materials["shared"]["duration"] -= 5
                    else:
                        broken = copy.deepcopy(materials)
                        group = next(doc for doc in broken["documents"] if doc["id"] == "worksheet_group_a")

                        def remove_reference(value):
                            if isinstance(value, list):
                                value[:] = [item for item in value if item != {"type": "from_shared", "key": "exit_ticket"}]
                                for item in value:
                                    remove_reference(item)
                            elif isinstance(value, dict):
                                for item in value.values():
                                    remove_reference(item)

                        remove_reference(group)
                        report = data(await session.call_tool("validate_teaching_materials",
                                      {"mode": mode, "materials": broken}))
                        assert not report["valid"]
                        assert any(issue["code"] == "MISSING_COMMON_REFERENCE"
                                   and "exit_ticket" in issue["fix_hint"] for issue in report["diagnostics"]), report
                    rendered = data(await session.call_tool("render_teaching_documents", args))
                    assert rendered["status"] == "ok", rendered
                    assert rendered["post_delivery_guidance"] == current_guidance
                    assert "去资源广场看看" in current_guidance and "完成本次备课" in current_guidance
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
                    assert "post_delivery_guidance" not in rejected
                    assert set(Path(temporary).iterdir()) == before
                assert len(set(outputs)) == 3
                # Shared reference drift must be rejected, not silently rendered.
                materials["documents"][0]["sections"][0].setdefault("blocks", []).append(
                    {"type": "from_shared", "key": "missing_task"})
                rejected = data(await session.call_tool("validate_teaching_materials",
                                  {"mode": "planning", "materials": materials}))
                assert not rejected["valid"]
                assert any(issue["code"] == "MISSING_SHARED_REFERENCE"
                           and issue["path"].startswith("documents[0].sections[0].blocks[")
                           and issue["path"].endswith("].key")
                           and "missing_task" in issue["message"] for issue in rejected["diagnostics"]), rejected
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
