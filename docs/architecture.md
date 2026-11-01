# 架构说明 — AI Learning Copilot

- Status: 基线版（P1–P3.5）
- Related: `AGENTS.md`、`docs/skill-contracts.md`、`docs/decisions/*`

## 1. 业务闭环

```
Homework Upload
   ↓
Homework Analysis      题目转录 / 学生作答 / 参考解答 / 错误分类 / 知识点映射
   ↓
Knowledge Diagnosis     掌握状态 + observations/hypotheses + evidence 引用
   ↓
Learning Plan           三天计划 + 基础/变式/迁移题 + exit ticket
   ↓
AI Math Tutor           苏格拉底式引导，分级提示
   ↓
Independent Assessment  新题独立验证 → 生成 evidence
   ↓
Learning Report         家长可见，只陈述证据支持的结论
```

## 2. 角色分工（谁做什么，谁不做什么）

| 组件 | 职责 | 明确不负责 |
|---|---|---|
| **OpenClaw** | 加载 Skill、调度主 Agent、提供工具与权限 | 不提供持久化 Workflow 引擎 |
| **主 Agent** | 按 `workflows/*.md` 顺序调用 Skill、推进状态游标 | 不做数学验算（交给脚本）、不自行编造 ID |
| **OpenCode** | 开发期：设计、编码、测试、文档 | 运行时不被依赖（R4） |
| **Skill** | 描述"如何完成某项任务" + 附带 references/scripts | ≠ Agent，≠ Workflow（R1） |
| **确定性脚本** | Schema 校验、数学验算、ID 生成、状态落盘 | 不做语义判断 |
| **模型（Qwen/DeepSeek）** | 转录、推理、教学对话、生成题目 | 不判定自己已验证 |

**核心设计立场**：凡能用代码确定的，绝不交给模型判断。
模型的自由裁量只保留在三处 —— 转录歧义的提示、教学对话、题目生成。

## 3. 四个 Skill 的职责与依赖

### homework-analysis（P4）

- 输入：`student_id` `grade` `subject` `homework_id` 图片或文本
- 输出：逐题的转录 / 学生答案 / 学生步骤 / 参考答案 / 参考解法 / 错误分类 / 知识点 ID / 置信度 / 验证状态
- 依赖：`knowledge-base/grade-7-math.json`（只读）、`schemas/homework-analysis.schema.json`、
  `scripts/math_check.py`、`scripts/state_store.py`
- 被依赖：knowledge-diagnosis
- **本项目质量上限的决定因素**：下游三个 Skill 全部消费它的输出

### knowledge-diagnosis（P5）

- 输入：homework-analysis 输出 + 知识库 + 关系表 + 历史 evidence
- 输出：`student-profile` JSON，逐知识点给 `status` / `confidence` /
  `observations` / `hypotheses` / `evidence_ids` / `next_verification`
- 依赖：上述，另需 `references/mastery-rules.md`（量化规则表）与实现该规则的脚本
- 被依赖：learning-plan、math-tutor
- 第一版**用可解释规则模型，不用 BKT/DKT**：先保证每个结论有证据，再谈算法精度

### learning-plan（P6）

- 输入：diagnosis + 学习历史 + 可用时间 + 可选考试范围
- 输出：三天计划，每天 ≤2 个重点知识点，含基础/变式/迁移题与 exit ticket
- 依赖：diagnosis、关系表（前置优先）、`schemas/learning-plan.schema.json`
- 被依赖：math-tutor
- 策略：Retrieval / Spaced / Interleaving / Self-Explanation / Worked Examples / Transfer

### math-tutor（P7）

- 输入：知识点 + 学生提问 + 当前任务 + 历史证据 + 会话历史
- 输出：教学对话 + `hint_level` + 学生反应 + 独立/提示后判定 + 验证题
- 依赖：diagnosis（读，不改）、plan、`schemas/tutor-session.schema.json`
- 特殊：**其会话结果必须能作为 evidence 回写**（append-only），形成闭环

依赖图（无环）：

```
knowledge-base（人工审核，只读）
   ├── homework-analysis ──→ knowledge-diagnosis ──→ learning-plan ──→ math-tutor
   │                                ↑                                      │
   └────────────────────────────────┴──── evidence（append-only 回写）◄────┘
```

## 4. 数据契约

唯一真相是 `schemas/*.json`，本文档只描述关系，不重复字段定义。

| Schema | 生产者 | 消费者 |
|---|---|---|
| `knowledge-point.schema.json` | 人工维护知识库 | 全部 Skill（只读校验） |
| `homework-analysis.schema.json` | homework-analysis | knowledge-diagnosis |
| `student-profile.schema.json` | knowledge-diagnosis | learning-plan、math-tutor |
| `learning-plan.schema.json` | learning-plan | math-tutor、主 Agent |
| `tutor-session.schema.json` | math-tutor | state_store → evidence |

所有输出共享信封字段：`schema_version` `skill_name` `prompt_version`
`generated_at` `student_id` `confidence`。

## 5. 状态与持久化

见 `ADR-0003`。要点：

- 唯一写入者 `scripts/state_store.py`；Skill 不直接写文件
- `events.jsonl` append-only 为事实来源，成品 JSON 可由其重放重建
- Workflow 游标存 `workflow.json`，状态集 8 个正向 + `BLOCKED` + `FAILED`

## 6. 三条硬约束在架构里的落点

| 约束 | 落点 |
|---|---|
| R13/R14 不得虚构知识点 | 知识点 ID 只能来自知识库；`validate_*.py` 校验存在性；`origin` + `review_status` 决定关系边可用性 |
| R21 独立验证 | `scripts/math_check.py`（sympy + 数值双验 + 白名单解析），`verification_status` 由脚本给，不由模型给 |
| R22 证据不可变 | `state_store.py` 只追加；知识点废弃而非删除 |

## 7. 明确不包含的东西（防止误读）

- **没有 Workflow 引擎**。`workflows/homework-learning-workflow.md` 是给主 Agent 的
  指令文档 + 状态定义，不会自动执行。持久化编排留给后续用脚本/状态机实现。
- **没有多 Agent 系统**。PoC 只有一个主 Agent 顺序调用 Skill。
- **没有数据库与微服务**。JSON 文件 + 本地脚本。
- **没有 Web 产品**。Feishu 作为交互入口，OpenClaw Web Console 作为开发测试入口。
- **没有 OCR 方案**。图像输入路径是当前最大的未定义项（`AGENTS.md` 第 10 节缺口 2）。

## 8. 已知架构风险

1. **homework-analysis 是单点质量瓶颈**：它的转录与验算质量决定整条链的信噪比。
2. **图像输入未定义**：若 OCR 质量不足，PoC 只能验证"文本输入"分支的闭环，
   结论适用范围要相应收窄。
3. **掌握度规则未量化前不可实现**：P5 开工前必须先有阈值表（几次、什么间隔、
   是否独立），否则诊断不可复现、benchmark 无法归因。
4. **sympy 覆盖不到应用题与几何**：这是设计取舍，会在报告中表现为
   `needs_human_check` 比例偏高，需要人工抽检兜底。
