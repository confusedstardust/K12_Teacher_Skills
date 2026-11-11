#!/usr/bin/env bash
# Copyright 2026 Anthropic, PBC
# Copyright 2026 Learning Commons
# SPDX-License-Identifier: Apache-2.0

# Render all four artifacts (teacher plan + three tier worksheets) from one
# differentiation.json in a single invocation. Writes editable .docx (the teacher
# deliverable) and an .html twin of each (a preview that renders even without python-docx).
# Fail-fast: any renderer error stops the run.
#
# Usage: bash scripts/render_all.sh differentiation.json "$OUTPUT_DIR"
set -euo pipefail

json="${1:?usage: render_all.sh DIFFERENTIATION_JSON OUTPUT_DIR}"
outdir="${2:?usage: render_all.sh DIFFERENTIATION_JSON OUTPUT_DIR}"
here="$(cd "$(dirname "$0")" && pwd)"

if ! command -v python3 >/dev/null 2>&1; then
  echo "error: 找不到 python3。请在渲染环境安装 Python，保留原材料 JSON 后重试。" >&2
  exit 3
fi

mkdir -p "$outdir"
word_status=0
# python-docx powers the .docx output; the .html twins render without it. If the install
# can't complete (offline container), render html now so the twins always exist.
if ! python3 -c "from docx import Document" 2>/dev/null; then
  python3 -m pip install -q "python-docx==1.1.2" || true
fi
if python3 -c "from docx import Document" 2>/dev/null; then
  python3 "$here/render_documents.py" "$json" --format both --outdir "$outdir"
else
  # Render the html twins so a readable preview still exists, then fail loudly: the
  # teacher's .docx deliverables could not be produced.
  python3 "$here/render_documents.py" "$json" --format html --outdir "$outdir"
  word_status=3
fi
# Persist the source JSON alongside the rendered artifacts so later revision
# turns can re-render from it (same guarantee the lesson-planning renderer
# makes with lesson.json).
cp "$json" "$outdir/differentiation.json" 2>/dev/null || true

# Delivery guarantee: when $OUTPUT_DIR is set and the render went elsewhere
# (a staging dir like /tmp/out), mirror EVERYTHING into $OUTPUT_DIR too.
# Revision turns re-render from the differentiation.json that lands there;
# hand-copying a subset there is the failure this removes.
if [ -n "${OUTPUT_DIR:-}" ] && [ "$(cd "$outdir" && pwd)" != "$(mkdir -p "$OUTPUT_DIR" && cd "$OUTPUT_DIR" && pwd)" ]; then
  cp -R "$outdir"/. "$OUTPUT_DIR"/
fi

if [ "$word_status" -ne 0 ]; then
  echo "error [WORD_DEPENDENCY_UNAVAILABLE]: 已生成 HTML 预览，Word 尚未生成。" >&2
  echo '修复：在同一环境运行 python3 -m pip install --force-reinstall "python-docx==1.1.2"。' >&2
  echo "保留原材料 JSON（$json），修复后重新运行原命令。" >&2
  exit "$word_status"
fi
