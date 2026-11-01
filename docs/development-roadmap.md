# 开发路线图

- Related: `AGENTS.md` 第 8 节阶段门禁、`docs/skill-contracts.md`
- 原则（R27）：**一个阶段验收 + Git 提交后，才进入下一个阶段。**
  禁止在一次编码代理任务里连续跑完多个阶段。

## 阶段总览

| 阶段 | 名称 | 产出 | 门禁（进入下一阶段的必要条件） | 状态 |
|---|---|---|---|---|
| P1 | 工程基线 | 骨架 + `AGENTS.md`(R1–R29) + README | R1–R29 可逐条核对；无学生数据/凭证被跟踪 | ✅ commit `77ca977` |
| P2 | 契约与决策 | `skill-contracts.md`、`skill-dependency-map.md`、ADR-0001~0007、架构与路线图 | 三个"能否串联"问题有字段级答案 | ✅ 本提交 |
| P3 | 数据契约落地 | 5 份 JSON Schema + 校验脚本 + Layer 1 测试 | `validate_schemas.py` + `pytest` 全绿（真实执行） | ✅ commit `35f2eb1` |
| P3.5 | 知识库结构化 | `grade-7-math.json`(T1 26 点)、关系表、`outline-t1.csv`、REVIEW-QUEUE | **人工核对教材版次 + 审核 26 点**；DAG 校验通过 | 🟡 结构已建并通过校验，待人工审核 |
| P3.7 | OCR spike | 10 张真实手写（脱敏/合成）识别记录 + 结论 | 明确 homework-analysis 输入边界：文本优先 or 图像可用 | ⛔ 未开始 |
| P4 | homework-analysis | 首个 Skill：SKILL.md + 4 references + validate 脚本 + 20 用例 | Layer 2 合规率 100%；验算覆盖率有实测数字；步骤级错误定位案例通过 | ⛔ |
| P5 | knowledge-diagnosis | Skill + `mastery-rules.md`（量化规则表）+ 8 场景测试 | 每个结论都有 `evidence_ids`；单次错误不产出 `needs_support` | ⛔ |
| P6 | learning-plan | Skill + `learning-methods.md` + `question-generation-rules.md` | 每题 gold 答案通过 `math_check.py`；answer_key 分离 | ⛔ |
| P7 | math-tutor | Skill + `tutoring-methods.md` + `hint-policy.md` | 零答案泄露；会话可回写 evidence | ⛔ |
| P8 | Workflow 集成 | `workflows/*.md` + 测试用例 + 端到端演示 | 演示可复现；**不假装 Markdown 自动执行** | ⛔ |
| P9 | Benchmark | `cases.json`、`evaluation-rules.yaml`、3 个脚本、对比报告 | ≥30 人工审核案例；含五类归因与 case 级 diff | ⛔ |
| P10 | 部署 OpenClaw | deploy/rollback 脚本 + 部署报告 | dry-run 先行；`openclaw skills list` 确认加载 | ⛔ |

## 关键路径与人工介入点

```
P1 → P2 → P3 ──┬──► P3.5(需人工核对教材) ──► P4 ──► P5 ──► P6 ──► P7 ──► P8 ──► P9 ──► P10
               │
               └──► P3.7 OCR spike（可与 P3.5 并行，但必须在 P4 定边界前完成）
```

必须由人（不能由编码代理）完成的三件事：

1. **教材版次核对**（P3.5）—— 看版权页版次 + 数目录章数
2. **gold 标准审核**（P3.5 / P4 / P9）—— ADR-0004 禁止由开发过程生成期望输出
3. **ADR 批准**（ADR-0003 / 0004 / 0005 / 0007）—— ADR-0001 规定只有人可写 `Accepted`

## 各阶段交付清单

### P3 数据契约（下一提交）

```
schemas/knowledge-point.schema.json
schemas/homework-analysis.schema.json
schemas/student-profile.schema.json
schemas/learning-plan.schema.json
schemas/tutor-session.schema.json
scripts/validate_schemas.py
scripts/validate_skills.py
scripts/validate_knowledge_base.py
scripts/new_id.py
scripts/math_check.py
requirements.txt
tests/test_math_check.py
tests/test_validate_schemas.py
tests/test_new_id.py
tests/test_validate_skills.py
tests/test_validate_knowledge_base.py
```

### P3.5 知识库

- T1 批次 26 个诊断点：第1章 5 / 第2章 9 / 第3章 2 / 第4章 5 / 第5章 5
- 范围：人教版七上第 1–5 章；第 6 章几何暂缓（ADR-0006）
- 关系边：`PREREQUISITE` 为主，少量 `EASILY_CONFUSED`
- 交付：`grade-7-math.json`、`knowledge-relations.json`、`outline-t1.csv`、`REVIEW-QUEUE.md`

### P4 homework-analysis（最优先的业务 Skill）

理由：下游三个 Skill 的效果全部受它的转录与验算质量约束（`docs/architecture.md` 第 8 节）。

必须先定的两件事：

1. 输入边界（P3.7 结论）
2. `references/error-types.md` 的判定口径与 `AGENTS.md` 枚举一致

## 暂不引入清单（防止过早复杂化）

| 不引入 | 原因 | 何时重新评估 |
|---|---|---|
| 多 Agent 系统 | PoC 目标是验证流程，不是验证架构 | P10 之后 |
| BKT / DKT 掌握度模型 | 需先保证"每个结论有证据"，可解释规则优先 | P5 验收且 evidence ≥ 每点 5 条 |
| 数据库（SQLite/PG） | JSON 可读、可 diff、可人工审阅 | 正式产品阶段 |
| LangGraph / 编排引擎 | 会掩盖"契约能否串联"这一真实待验证问题 | P8 之后 |
| Web 产品 / 微服务 | PoC 用 Feishu + OpenClaw Console | PoC 结论成立后 |
| 真实 OCR 服务选型 | 未做 spike 前选型等于猜 | P3.7 完成 |

## 里程碑判据（写成可判定的话）

- **M1（P3 完）**："5 份 Schema 自身合法，内置示例全部通过自校验；
  `pytest` 全绿，其中 `math_check.py` 的 4 类对抗用例（漏变号、乘方括号、注入、降级）全部通过。"
- **M2（P3.5 完）**："26 个知识点，PREREQUISITE 无环，教材版次经人工核对，
  `review_status: reviewed`。"
- **M3（P4 完）**："homework-analysis 在 20 个用例上 Schema 合规率 100%；
  算术题 `program_verified` 实测覆盖率 ≥ 90%，代数题 ≥ 80%；
  `-(2x-3)+x → -x-3` 案例正确定位到'括号前负号逐项变号'步骤级错误；
  `needs_human_check` 比例有实测数字。"
- **M4（P8 完）**："从作业文本输入到学习报告的端到端演示可复现，
  中途终止后可通过 `replay` 恢复。"

注意：M3 里刻意**不写**"Skill 开发完成"这种不可判定的表述。
