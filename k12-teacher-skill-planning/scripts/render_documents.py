#!/usr/bin/env python3
# Copyright 2026 Anthropic, PBC
# Copyright 2026 Learning Commons
# SPDX-License-Identifier: Apache-2.0

"""Render every document in a multi-document source JSON (HTML previews and/or editable .docx).

Used by skills whose output is a set of documents that must stay consistent with each other
(e.g. the differentiation skills: 1 teacher plan + 3 tiered worksheets). The source JSON holds
ONE `shared` block (content that appears in more than one document) plus a `documents` array.
Each document is a full block-document — same schema as render_lesson_html.py /
render_lesson_docx.py (eyebrow / title / meta / sections / theme / audience) — and pulls shared
content with {"type": "from_shared", "key": ...} blocks, so shared content is written once and
cannot drift between documents.

Material source shape:
  {
    "shared": {"standard_code": ..., "standard_text": ...,
               <any model-chosen keys: a block, a list of blocks, or a faceted
                {teacher, student, stimulus} value>, ...},
    "theme": {...},                              // default theme for every document
    "documents": [
      {"id": "teacher_plan",      "audience": "teacher", "title": ..., "sections": [...]},
      {"id": "worksheet_group_a", "audience": "student", "title": ..., "sections": [...]},
      {"id": "worksheet_group_b", "audience": "student", "title": ..., "sections": [...]},
      {"id": "worksheet_group_c", "audience": "student", "title": ..., "sections": [...]}
    ]
  }

`id` becomes the output filename; a document's own `theme` overrides the top-level one.

Usage:
    python render_documents.py differentiation.json --format html             # all docs -> HTML previews
    python render_documents.py differentiation.json --format docx             # all docs -> editable .docx
    python render_documents.py differentiation.json --only worksheet_group_a worksheet_group_b --format docx
"""
from __future__ import annotations

import argparse
import json
import re
import shlex
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def build_doc(source: dict, doc: dict) -> dict:
    """Merge a document entry with the source's shared block and default theme."""
    out = dict(doc)
    out.setdefault("shared", source.get("shared", {}))
    theme = dict(source.get("theme") or {})
    theme.update(doc.get("theme") or {})
    if theme:
        out["theme"] = theme
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", help="source JSON with a `documents` array")
    ap.add_argument("--format", choices=["html", "docx", "both"], default="html")
    ap.add_argument("--only", nargs="*", default=None,
                    help="document ids to render (default: all)")
    ap.add_argument("--outdir", default=".")
    args = ap.parse_args()

    source = json.loads(Path(args.input).read_text(encoding="utf-8"))
    docs = source.get("documents", [])
    if not docs:
        print("error: no `documents` array in input", file=sys.stderr)
        return 1

    render_docx = None
    if args.format in ("docx", "both"):
        try:
            from docx import Document  # noqa: F401 — check the active Python environment
        except (ImportError, OSError) as exc:
            install_args = ["-m", "pip", "install", "--force-reinstall", "python-docx==1.1.2"]
            if sys.platform == "win32":
                executable = sys.executable.replace("'", "''")
                command = f"& '{executable}' " + " ".join(install_args)
            else:
                command = shlex.join([sys.executable, *install_args])
            print("error [WORD_DEPENDENCY_UNAVAILABLE]: 当前 Python 无法加载 python-docx，未生成 Word。",
                  file=sys.stderr)
            print(f"原因：{exc}\n修复：在运行渲染脚本的同一 Python 环境安装或修复 python-docx。\n{command}\n"
                  "保留原材料 JSON，修复后重试原命令。如需先看预览，可用 --format html。",
                  file=sys.stderr)
            return 3
        from render_lesson_docx import render as render_docx

    from render_lesson_html import render as render_html

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    written = []
    for i, doc in enumerate(docs):
        # Sanitize the document id before it becomes a filename: the id comes from generated
        # JSON, so strip path separators and anything outside [A-Za-z0-9_-].
        doc_id_raw = str(doc.get("id") or f"document_{i + 1}")
        doc_id = re.sub(r"[^A-Za-z0-9_\-]", "_", Path(doc_id_raw).name) or f"document_{i + 1}"
        if args.only and doc_id_raw not in args.only and doc_id not in args.only:
            continue
        full = build_doc(source, doc)
        # The HTML twin always ships — docx is the teacher deliverable, html is its
        # always-available preview. Rendering docx alone leaves the twin missing, so
        # "docx" implies both.
        path = outdir / f"{doc_id}.html"
        path.write_text(render_html(full), encoding="utf-8")
        written.append(str(path))
        if render_docx is not None:
            path = outdir / f"{doc_id}.docx"
            render_docx(full, str(path))
            written.append(str(path))

    if not written:
        print("nothing rendered — check --only ids against the documents' `id` fields",
              file=sys.stderr)
        return 1
    print("wrote " + ", ".join(written))
    return 0


if __name__ == "__main__":
    sys.exit(main())
