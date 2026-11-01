# Skill 依赖图与 evidence 生命周期

- Related: `docs/skill-contracts.md` 第 5 节、`ADR-0003`、`ADR-0006`

## 1. 依赖图

```
                    ┌─────────────────────────────────────────┐
                    │  knowledge-base/（人工审核，模型只读）    │
                    │  grade-7-math.json  knowledge-relations  │
                    └───────┬───────────────┬─────────────────┘
                     只读引用│               │只读引用
                            ▼               ▼
   作业输入 ──► [homework-analysis] ──► [knowledge-diagnosis]
                    │  analysis.json         │  student-profile.json
                    │ (Layer2 校验后落盘)     │
                    │                         ├──────────► [learning-plan]
                    │                         │                 │ plan.json
                    │                         │                 ▼
                    │                         └──────────► [math-tutor]
                    │                                      │ tutor-session.json
                    │                                      │
                    ▼                                      ▼
              events.jsonl ◄──── state_store.py append ────┘
              （append-only 证据池，回流给 diagnosis）
```

横切依赖（所有 Skill 共用）：

| 脚本 | 作用 |
|---|---|
| `scripts/math_check.py` | 白名单解析 + sympy 符号验证 + 数值双验（ADR-0002） |
| `scripts/new_id.py` | `stu_xxxx` / `ev_*` ID 规则（R23） |
| `scripts/state_store.py` | 唯一写入者：ID 分配、加锁、幂等、落盘、replay（ADR-0003，待实现） |
| `scripts/validate_*.py` | Layer 2 结构校验（ADR-0004） |

## 2. 调用顺序（主 Agent 责任，非引擎）

```
RECEIVED → EXTRACTED → ANALYZED → DIAGNOSED → PLANNED → TUTORING → VERIFIED → REPORTED
              │            │           │           │          │           │
              └ 失败进 BLOCKED，任一阶段致命失败进 FAILED 并记 failure.stage
```

**重要**：`workflows/homework-learning-workflow.md` 是给主 Agent 的指令文档，
不会自动执行。没有 Workflow Engine，就没有自动编排（`AGENTS.md` 第 10 节缺口 4）。

## 3. evidence 生命周期

### 3.1 产生

| 来源 | type | 关键字段 | 可支撑的维度 |
|---|---|---|---|
| homework-analysis | `homework_attempt` | `result`、`first_incorrect_step`、`verification_status` | accuracy（部分）、错误事实 |
| math-tutor 会话 | `tutoring_turn` | `hint_level`、`independence`、`explanation_quality` | independence、accuracy |
| 独立验证题 | `verification_result` | `independent_result`、`status` | accuracy、transfer、retention |
| learning-plan exit ticket | `exit_ticket_result` | `correct`、`independence` | accuracy、transfer |

### 3.2 写入

```
append(student_id, type, payload, client_event_id)
  → 获取 .lock（超时 10s）
  → 分配 seq（单调，重试不复用）
  → 计算 event_id = ev_<student_id>_<seq:04d>
  → 幂等检查：同 (source, client_event_id) 已存在 → 返回既有 event_id，不新增
  → 写一行 JSON 到 events.jsonl，fsync
  → 释放锁
```

### 3.3 消费

- diagnosis 读全量 + 按 `knowledge_point_id` 聚合
- 只把 `verification_status in (program_verified, model_checked)` 的条目计入 accuracy
- `origin: inferred` 且未审的关系边只可用于生成提问，不可用于结论

### 3.4 不可变约束

- 无 UPDATE、无 DELETE（R22）
- 纠错方式：追加一条 `type: "evidence_correction"`，引用被更正的 `event_id`，
  并说明原因。旧条目保留，diagnosis 取最新有效解释
- 知识点废弃：`deprecated: true`，历史引用仍可解析（ADR-0006）

## 4. 数据流向表（谁读谁写）

| 数据 | 写者 | 读者 | 可变性 |
|---|---|---|---|
| `events.jsonl` | `state_store.py` | diagnosis、report | **append-only** |
| `analysis.json` | `state_store.py`（校验后） | diagnosis | 可重放重建 |
| `student-profile.json` | `state_store.py` | plan、tutor | 可重放重建 |
| `plan.json` | `state_store.py` | tutor、家长视图 | 版本化保留 |
| `answer_key.json` | `state_store.py` | tutor（仅验证阶段） | 与学生视图分离（R19） |
| `workflow.json` | `state_store.py` | 主 Agent | 游标，非证据 |
| `grade-7-math.json` | **人工** | 全部 Skill | 人工审核维护 |
| `knowledge-relations.json` | **人工** + 审核后入的推断 | diagnosis | 同上 |

## 5. 版本兼容

- 每个产物带 `schema_version`；读取方必须容忍"更高版本"并给出明确错误，
  不得静默降级解析（R9）
- 新增可选字段 = minor bump；改语义或删字段 = major bump + ADR + 迁移脚本
- `prompt_version` 变化不影响数据契约，但必须进 benchmark run manifest（ADR-0004）

## 6. 依赖健康检查（可由脚本自动验证）

| 检查 | 实现 | 状态 |
|---|---|---|
| 知识点 ID 存在于知识库且未废弃 | `validate_knowledge_base.py` + Layer 2 | ✅ 已实现 |
| `PREREQUISITE` 无环 | `validate_knowledge_base.py`（`graphlib`） | ✅ 已实现 |
| evidence_id 真实存在 | diagnosis 侧校验 | ⛔ 待 `state_store.py` |
| Skill 目录与 frontmatter 合法 | `validate_skills.py` | ✅ 已实现（skills 为空时 SKIP） |
| 无凭证/身份字段入库 | `git ls-files` 扫描 + 内容嗅探 | ⚠️ 仅手工命令，自动嗅探待 P10 |
