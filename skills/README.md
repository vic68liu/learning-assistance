# skills/

业务 Skill 目录。**本阶段为空** —— 按 `AGENTS.md` R27 与 `docs/development-roadmap.md`，
只有在 P2（契约）与 P3（Schema）验收通过后才开始开发第一个 Skill。

## 计划中的四个 Skill

| 目录名 | 职责 | 开发阶段 |
|---|---|---|
| `homework-analysis/` | 从作业图片/文本提取题目、答案、过程，独立求解并诊断错误 | P4 |
| `knowledge-diagnosis/` | 由分析结果 + 历史证据判定知识点掌握状态 | P5 |
| `learning-plan/` | 由诊断结果生成三天个性化学习计划 | P6 |
| `math-tutor/` | 苏格拉底式引导，不直接给答案 | P7 |

## 每个 Skill 的强制结构

```
<skill-name>/
├── SKILL.md            # YAML frontmatter: name / description / user-invocable
├── references/         # 复杂业务规则（详细规则放这里，不放 SKILL.md）
├── scripts/            # 确定性计算与校验（确有需要时才建）
└── tests/              # 该 Skill 的测试数据与期望结果
```

约束（R1–R4、R6、R17）：

- Skill ≠ Agent，Skill ≠ Workflow。它只描述"如何完成某项任务"。
- `name` 必须与目录名一致，且全局唯一（`scripts/validate_skills.py` 会检查）。
- 掌握状态等判定规则必须是**量化规则表**并由脚本实现，不能只写在 `SKILL.md` 里让模型凭语感判断。
- 必须能被 OpenClaw 独立加载运行，不依赖 OpenCode。
