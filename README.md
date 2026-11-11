# 中国 K-12 教学 Skills

用 AI 为中国 K-12 课堂设计教学材料，或把已有教案改成差异化教学方案。生成可编辑的 Word 文档，交付后可按本课主题去 [NarrativeOS 教师资源广场](https://www.narrativeos.cn/teacher-ecosystem/) 找案例。

| 功能 | 适合什么时候用 | 交付物 |
| --- | --- | --- |
| [课程设计](k12-teacher-skill-planning/SKILL.md) | 有课题，需要从零备课 | 教学设计、学生学习材料、课堂观察表 |
| [差异化教学](k12-teacher-skill-differentiation/SKILL.md) | 已有课例，想让学生用不同支架达成同一目标 | 教师差异化方案、三份学生任务单 |

## 开始使用

任选一种入口。Skill 适合已有 Skills 功能的 AI 应用，MCP 适合支持本地 stdio 工具的 AI 应用。

### 安装 Skill

在支持 Skills 的应用中，按该应用的安装方式导入本仓库里的 `k12-teacher-skill-planning` 或 `k12-teacher-skill-differentiation` **整个目录**。在对话中分别使用 `china-k12-lesson-planning` 或 `china-k12-lesson-differentiation`。

### 连接 MCP

**1. 准备 uv。** 打开终端运行 `uvx --version`。如果能看到版本号，直接跳到第 2 步。否则按系统选择一条安装命令。

- **Windows**：打开 PowerShell，运行 `winget install --id astral-sh.uv -e`。
- **macOS 或 Linux**：打开终端，运行 `curl -LsSf https://astral.sh/uv/install.sh | sh`。

安装后重新打开终端，用 `uvx --version` 确认，再重新打开 AI 应用。若系统没有对应的安装命令，可选择官方提供的其他安装方式。 [uv 安装指南](https://docs.astral.sh/uv/getting-started/installation/)

**2. 添加 MCP 配置。** 打开 AI 应用的 MCP 设置。使用 `mcpServers` JSON 配置的客户端可以复制下面的配置。已有其他 MCP 时，只把 `k12-teacher` 条目加到现有的 `mcpServers` 里。使用表单的客户端选择 stdio，分别填写下方的 `command` 和 `args`。 [配置文件](examples/mcp-config.json)

```json
{
  "mcpServers": {
    "k12-teacher": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/confusedstardust/K12_Teacher_Skills.git",
        "k12-teacher-mcp"
      ],
      "disabled": false,
      "disabledTools": []
    }
  }
}
```

支持这两个开关的客户端会启用服务并开放全部工具。如果客户端提示这两个字段无法识别，删掉它们即可，保留 `command` 和 `args`。

**3. 开始备课。** 保存配置后，在 AI 应用里确认 `k12-teacher` 已连接，再使用下面的对话示例。第一次连接时，`uvx` 会通过 Git 从 GitHub 获取程序并安装依赖，所需的 Python 也可由 uv 管理。如果提示找不到 Git，可先安装 [Git](https://git-scm.com/install)，然后重新打开应用。

如果终端能运行 `uvx --version`，但应用仍提示找不到 `uvx`，可在 Windows PowerShell 运行 `(Get-Command uvx).Source`，在 macOS 或 Linux 运行 `command -v uvx`，再用输出的路径替换配置里的 `command`。

如果你的应用支持 Skills，也可以直接使用上面的 Skill 安装入口，跳过这三步。

### 让 AI 在备课时发现 MCP

如果应用按需加载 MCP 工具，并支持始终加载的自定义指令或项目规则，把下面这段加入该设置。它让 AI 在决定如何备课前先搜索工具。

> 当用户要求备课、写教案、设计学习单、生成 Word 教案，或将已有教案改成分层教学方案时，先在可用工具中查找 `k12-teacher` 的 `get_teaching_guidance`。如果工具按需加载，先用工具搜索查找 `k12-teacher get_teaching_guidance 备课 教案 分层教学`。确定学科后调用该工具获取教学流程，再按流程询问必要信息、设计和交付材料。

配置后，开一个新对话，用下面的备课示例测试。工具搜索和调用由客户端及模型决定。若客户端支持固定显示工具或为备课请求配置工具路由，也可以在客户端设置。

## 使用示例

> 请用中国 K-12 课程设计，为五年级数学《三角形的面积》设计一节 45 分钟的课。教材版本先标记为待核对，最后交付可编辑的 Word。

> 请根据我提供的教案做差异化改造。三个小组保留同一个学习目标，按学生需要调整提示和支架，输出教师方案和三份任务单。

AI 应用里的模型负责设计教学内容和核实课程依据。MCP 在本机校验材料并生成 Word 和 HTML，默认保存到用户主目录下的 `K12-Teacher-Outputs`。如需自定义目录，可在客户端的 MCP 环境变量中设置 `K12_TEACHER_OUTPUT_DIR`。

## MCP 工具

| 工具 | 用途 |
| --- | --- |
| `get_teaching_guidance` | 按备课模式和学科提供教学规则、材料格式和示例 |
| `validate_teaching_materials` | 检查材料结构和共享引用，返回可修正的问题 |
| `render_teaching_documents` | 校验通过后生成 Word 和 HTML，返回本机文件路径 |

## 开发与验证

在克隆后的仓库根目录运行。

```bash
uv sync --locked
uv run --locked python tests/smoke_mcp.py
uv build
```

教学规则、参考资料和渲染脚本会随 MCP 安装包一起打包。更新 NarrativeOS 引导时，编辑[课程设计目录中的引导规则](k12-teacher-skill-planning/references/narrativeos-case-guidance.md)，再同步到差异化教学目录。集成测试会检查两份规则一致。
