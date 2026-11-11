# 中国 K-12 教学 Skills 与本地 MCP

两种入口共用教学规则与文档脚本：

- **Skill**：安装 `k12-teacher-skill-planning` 或 `k12-teacher-skill-differentiation`，Agent 直接读取规则并运行脚本；原有用法保持不变。
- **本地 MCP**：AI 应用启动本机服务，Agent 通过工具获取规则、设计材料、校验并生成 Word。不需要另行安装 Skill；程序安装包已包含所需资源。

服务不调用大模型、不联网查课标。教学内容由宿主 Agent 按返回规则设计；课程依据仍需结合教师材料或宿主检索能力核实。首次安装需要联网下载程序和依赖，后续工具处理在本机完成；宿主模型的数据处理方式由所用 AI 应用决定。

## 本地启动

需要 [uv](https://docs.astral.sh/uv/) 和 Python 3.11+（uv 可管理 Python）。在仓库根目录运行：

```powershell
uv sync --locked
uv run --locked k12-teacher-mcp
```

启动后没有聊天界面，程序等待 stdin 消息是正常现象。使用支持 stdio MCP 的应用连接；不要把普通聊天文本输入服务终端。

也可以在任意目录启动（将路径换成实际绝对路径）：

```powershell
uvx --from "C:/Users/Eden/Desktop/teacher skill/K12_Teacher_Skills" k12-teacher-mcp
```

## MCP 连接配置

以下适用于使用 `mcpServers` JSON 配置的客户端；其他客户端需按其格式填写相同的 command / args。路径中的空格不需要额外嵌入引号，每个参数是独立数组元素。

当前电脑可直接参考 `examples/mcp-config.json`（本机路径示例，换电脑须修改）。本项目不会自动改动你的 AI 应用配置。

```json
{
  "mcpServers": {
    "k12-teacher": {
      "command": "uvx",
      "args": [
        "--from",
        "C:/Users/Eden/Desktop/teacher skill/K12_Teacher_Skills",
        "k12-teacher-mcp"
      ],
      "env": {
        "K12_TEACHER_OUTPUT_DIR": "C:/Users/Eden/Documents/K12-Teacher-Outputs"
      }
    }
  }
}
```

如果客户端找不到 uvx，请把 command 改成 `uvx.exe` 的绝对路径。`K12_TEACHER_OUTPUT_DIR` 可省略，默认输出到用户主目录下的 `K12-Teacher-Outputs`。

代码发布到 GitHub 后，可以将 `--from` 后的本地路径换成 `git+https://github.com/confusedstardust/K12_Teacher_Skills.git@<已发布提交号>`，从仓库获取运行。**当前本地修改尚未发布，不能直接用远程地址获取本次新增入口。** 对外使用应固定已验证的提交号。

## 三个工具与调用顺序

| 工具 | 参数 | 返回 |
| --- | --- | --- |
| `get_teaching_guidance` | `mode`, `subjects` | 完整工作流、所需学科参考、材料 schema、示例 |
| `validate_teaching_materials` | `mode`, `materials` | `valid`, `errors`, `warnings` |
| `render_teaching_documents` | `mode`, `materials` | 再校验后生成 Word/HTML，返回本机路径、file URI、文件大小 |

`mode` 为 `planning`（从零备课）或 `differentiation`（已有课例改造）。`subjects` 是学科中文名称数组，例如 `["数学"]`、`["语文", "历史"]`；不确定具体学科时先向教师澄清。

1. Agent 获取教学指导，依照返回内容向教师澄清必要信息。
2. Agent 设计内容，并按 schema 组织为 `{"shared": {...}, "documents": [...]}`。
3. 调用校验，修正错误；结构校验不证明课标真实性或教学质量。
4. 调用渲染。规划模式输出教学设计、观察表等；差异化模式输出教师方案和三份学生任务单。
5. 向教师交付 `.docx`。HTML 用于预览，`materials.json` 用于后续修订；改内容源后重新渲染。

示例首次调用参数：

```json
{"mode": "planning", "subjects": ["数学"]}
```

可对 Agent 说：“使用 k12-teacher MCP，先获取数学课程设计指导，再为五年级设计一节45分钟的三角形面积课。教材版本暂未提供，标记待核对；校验通过后生成 Word。”

规则中的本地参考文件已由指导工具返回，原 Skill 中执行脚本的步骤在 MCP 入口下改为调用校验和渲染工具。提示和工具描述会引导此顺序，但不能保证任何宿主模型严格遵循；仍需在目标客户端验收。

## 文件与运行边界

- 本服务是本地 stdio 程序，没有监听 HTTP 端口，也不是远程托管服务。
- 每次生成创建独立目录，避免覆盖之前的材料；渲染失败不会交付暂存产物。
- 返回的是服务所在电脑的文件路径，不是公网下载链接。是否能点击、预览或附加文件取决于客户端；无法显示时可直接按路径打开。
- 不接受任意脚本名或任意读取路径，教学参考来自程序包，输出根目录由启动环境配置。
- 当前复用已有结构校验器；未覆盖的格式问题可能在渲染时报错。不会自动联网安装渲染依赖。
- MCP SDK 采用有上界的 1.x 兼容系列，实际依赖固定在 `uv.lock`；后续升级需重新测试。

## 开发与验证

两套 Skill 在材料交付后按本课目标提供可选的 NarrativeOS 案例引导。维护时编辑课程设计 Skill 的 `references/narrativeos-case-guidance.md`，并复制到差异化 Skill 的同名路径，供单独安装时读取。MCP 两种模式均读取课程设计目录的原版，集成测试检查副本一致。

```powershell
uv sync --locked
uv run --locked python tests/smoke_mcp.py
uv build
```

测试使用真实 stdio 客户端启动子进程，验证初始化、工具发现、两种模式的规则获取/校验/渲染、错误输入和生成文件内容。wheel 构建时从现有两个 Skill 目录打包资源，源码不维护第二份教学规则。渲染和校验使用独立子进程，避免两套脚本的同名模块互相污染。
