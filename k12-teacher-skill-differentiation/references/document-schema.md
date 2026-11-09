# 差异化材料 JSON 结构

## 顶层

```text
theme: {primary?}
shared:
  education_stage, grade, subject, duration
  curriculum_standard, standard_basis, textbook
  core_task, check_task, vocabulary, anchor_activity, reflect_prompt
  <复用键>: string | block | block[] | {teacher, student, stimulus?}
documents[]:
  teacher_plan
  worksheet_group_a
  worksheet_group_b
  worksheet_group_c
```

每个文档：

```text
{id, audience: teacher|student, eyebrow, title, meta?,
 sections[]: {heading, blocks[]}}
```

常用 block：

```text
from_shared, paragraph, labeled, callout, h2, h3, list, checklist
phase_header, table, fill_table, number_line, source_card, cards
workspace, group, columns, page_break
```

## 强制规则

- 每个核心任务单独注册为 `shared.t1`、`shared.t2` 等。
- 三组通过 `from_shared` 拉取同一任务文本。
- A 组支架直接位于对应任务之前，并逐步减少。
- C 组额外任务放在独立“进一步思考” section，不改写共享任务。
- 三组都包含共同课堂检测、`anchor_activity` 和 `reflect_prompt`。
- 教师方案的任务清单逐项覆盖任务单实际打印内容。
- 学生页不出现能力等级、诊断或教师分组理由。

渲染前运行：

```bash
python scripts/validate_material_source.py differentiation.json --mode differentiation
```
