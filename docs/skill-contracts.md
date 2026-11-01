# Skill 接口契约 — AI Learning Copilot

- Status: **基线已定义，待人工评审**（第 5 节三个问题已给出字段级答案，见文末评审结论）
- Related: `AGENTS.md` R6–R8、`docs/architecture.md`、`schemas/*.json`
- 约束：本文档描述关系，**字段定义的唯一真相是 `schemas/*.json`**。两者冲突时以 Schema 为准，
  并立即修正本文档。

## 0. 通用约定

### 0.1 信封字段（所有 Skill 输出顶层必含）

| 字段 | 类型 | 说明 |
|---|---|---|
| `schema_version` | string | 所用 Schema 的语义化版本 |
| `skill_name` | string | 必须与 SKILL.md 的 `name` 一致 |
| `prompt_version` | string | 用于回归对比（ADR-0004） |
| `generated_at` | string(date-time) | ISO 8601 带时区 |
| `student_id` | string | `stu_xxxx`，由 `state_store.py` 分配（R23） |
| `confidence` | number \| null | `[0,1]`；无依据时必须 `null` |
| `confidence_basis` | string | 该置信度从何而来 |

### 0.2 统一枚举

见 `AGENTS.md` 第 4 节。任何 Skill 不得引入表外取值（R8）。

### 0.3 共同错误码

| code | 含义 | 处置 |
|---|---|---|
| `E_INPUT_UNREADABLE` | 图片/文本无法解析 | 标 `unreadable`，暂停请求确认（不猜，R11） |
| `E_SCHEMA_MISMATCH` | 输入不符上游契约 | 拒绝处理，回传字段路径 |
| `E_KB_UNAVAILABLE` | 知识库缺失/未审 | 拒绝给出掌握度结论 |
| `E_VERIFICATION_UNAVAILABLE` | 验算脚本异常/超时 | 降级 `needs_human_check` |
| `E_ID_NOT_FOUND` | 引用了不存在的知识点/evidence | 判违规，改用 `unmapped`（R13） |

---

## 1. homework-analysis

| 项 | 内容 |
|---|---|
| **Skill Name** | `homework-analysis` |
| **Business Purpose** | 把学生作业（图片或文本）转为结构化逐题分析：转录、独立求解、定位错误步骤、分类、映射知识点 |
| **Trigger Conditions** | ① 主 Agent 处于 `RECEIVED`/`EXTRACTED` 且收到作业 ② 用户直接请求"分析这次作业" |
| **Input Contract** | `student_id*` `grade*` `subject*` `homework_id*` `content*`(image ref 或 text) `curriculum_version` `textbook_version` |
| **Output Contract** | `schemas/homework-analysis.schema.json` |
| **Execution Steps** | 1 归一化输入 → 2 逐题转录（带置信度）→ 3 白名单解析数学表达式 → 4 独立求解（`math_check.py`）→ 5 比对学生答案 → 6 逐步分析学生过程 → 7 定位首个错误步骤 → 8 错误分类 → 9 知识点映射（只允许查知识库）→ 10 分离记录 observations / hypotheses → 11 Schema 自检 → 12 交 `state_store.py` 落盘 |
| **Required Knowledge** | 七年级数学（人教版七上第 1–5 章）；错误分类口径；知识库结构 |
| **Dependencies** | `knowledge-base/grade-7-math.json`（只读）、`scripts/math_check.py`、`scripts/validate_result.py`、`scripts/state_store.py` |
| **Error Handling** | OCR 不确定 → `uncertain_regions` + 暂停请求确认；无法验算 → `needs_human_check` + `verification_reason`；知识点无匹配 → `knowledge_mapping_status: unmapped`，禁止新增 ID |
| **Confidence Policy** | 转录置信与结论置信分开记录；任一 < 0.7 必须显式标记并进入人工确认队列，不得静默输出结论 |
| **Security Policy** | 原始照片只留本地 L0（ADR-0005）；输出仅含 ID 与学生作答文本的人工重打版本；禁止 API Key |
| **Acceptance Criteria** | 20 个 Layer 2 用例 Schema 合规率 100%；算术/代数验算覆盖率有实测数字；`-(2x-3)+x → -x-3` 类案例必须识别出"括号前负号逐项变号"步骤级错误；`uncertain` 与 `unmapped` 路径各有用例 |

### 输出结构要点

```
questions[]:
  question_id, order
  transcription, transcription_confidence
  student_answer, student_work[]: {step_no, content, verdict}
  reference_answer, reference_solution[]: {step_no, content}
  result                       # error type 枚举
  first_incorrect_step         # 整数或 null
  verification_status          # 由脚本给，不由模型给
  verification_reason
  knowledge_point_ids[], knowledge_mapping_status
  observations[]               # 只写看到的事实
  hypotheses[]: {statement, needs_verification, verification_question_id}
  confidence, confidence_basis
summary:
  total_questions, by_result{}, by_verification_status{},
  unmapped_knowledge_points[], needs_human_check_question_ids[], notes
```

`observations` 与 `hypotheses` 分列是 R10 的落地形式：
"学生在第 3 步把 `-3` 写成 `+3`" 是 observation；
"根因可能是去括号时未逐项变号" 是 hypothesis 且 `needs_verification: true`。

---

## 2. knowledge-diagnosis

| 项 | 内容 |
|---|---|
| **Skill Name** | `knowledge-diagnosis` |
| **Business Purpose** | 由作业分析 + 历史证据，逐知识点给出掌握状态与下一步验证建议 |
| **Trigger Conditions** | ① 存在合法的 homework-analysis 输出 ② 主 Agent 处于 `ANALYZED` |
| **Input Contract** | `analysis`（上游输出对象，非摘要）、`knowledge_base_ref`、`knowledge_relations_ref`、`evidence[]`（历史）、`recent_independent_verifications[]` |
| **Output Contract** | `schemas/student-profile.schema.json` |
| **Execution Steps** | 1 校验输入 Schema → 2 收集本次 evidence + 历史 evidence → 3 逐知识点聚合六维指标 → 4 按 `mastery-rules.md` 量化规则表映射到 status（由脚本判定）→ 5 检查 `PREREQUISITE` 前置（只"检查"，不自动标薄弱）→ 6 生成/引用 `next_verification` → 7 校验所有 `evidence_ids` 真实存在 → 8 落盘 |
| **Required Knowledge** | 掌握度规则表；知识关系语义；学习分析基本口径 |
| **Dependencies** | homework-analysis 输出、`grade-7-math.json`、`knowledge-relations.json`、`events.jsonl` |
| **Error Handling** | 无证据 → `status: unknown` 且六维为 `null`（禁止编造数值，R16）；证据矛盾 → `status: developing` + `hypotheses` 记录矛盾并生成验证题；关系边 `origin: inferred` 且未审 → 只可用于提问，不可用于结论 |
| **Confidence Policy** | `confidence` 必须随 `evidence_count` 单调相关并给出依据；`evidence_count == 0` 时 `confidence` 必为 `null` |
| **Security Policy** | 只读 evidence；禁止修改或删除历史；输出不含身份信息（R23） |
| **Acceptance Criteria** | 8 类场景全覆盖（一次错误 / 连续多错 / 多次独立正确 / 提示后正确 / 基础对变式错 / 无历史 / 前置漏洞 / 证据矛盾）；任一结论缺 `evidence_ids` 即验收失败；单次错误绝不产出 `needs_support` |

### 六维指标

每维结构统一为 `{ value, evidence_count, basis }`，无证据时整维 `null`：

`accuracy` `independence` `transfer` `retention` `confidence` `evidence_count`

第一版**不引入 BKT/DKT**（ADR 待定），只用可解释规则表：先保证每个结论可追溯到证据，
再谈建模精度。

---

## 3. learning-plan

| 项 | 内容 |
|---|---|
| **Skill Name** | `learning-plan` |
| **Business Purpose** | 把诊断结果转为可执行的三天个性化计划 |
| **Trigger Conditions** | 存在 `student-profile`；主 Agent 处于 `DIAGNOSED` |
| **Input Contract** | `student_id*` `grade*` `diagnosis*` `knowledge_relations_ref` `previous_plans[]` `available_minutes_per_day*` `exam_scope` |
| **Output Contract** | `schemas/learning-plan.schema.json` |
| **Execution Steps** | 1 取 `status != mastered` 的点 2 按 `PREREQUISITE` 排序（前置优先）3 每天选 ≤2 个重点 4 按学习科学策略排活动 5 每点生成 basic/variation/transfer 三题 6 生成 exit ticket 7 答案与解析**分离写入 answer_key 文件** 8 校验题目难度与知识点匹配 9 落盘 |
| **Required Knowledge** | 七年级数学难度标定；六类学习策略适用场景；出题规则 |
| **Dependencies** | student-profile、知识库与关系表、`math_check.py`（生成题必须可验算） |
| **Error Handling** | 诊断全为 mastered → 生成维持性计划并说明；无诊断数据 → 拒绝生成"个性化"计划，改生成通用复习并标注；可用时间 < 20 分钟 → 缩减活动量但不减少重点点的验证题；题目验算失败 → 丢弃该题并重新生成，不得保留未验证题 |
| **Confidence Policy** | 计划本身不声称置信度，但必须携带所依据诊断的 `generated_at`，用于判断是否过期 |
| **Security Policy** | **R19**：`answer_key` 与学生可见内容分离存储；主 Agent 展示计划时不得加载 answer_key 文件 |
| **Acceptance Criteria** | 7 类场景（单点薄弱 / 多点相关 / 前置问题 / 时间不足 / 临考 / 无历史 / 复习混合）；每题有 gold 答案且通过 `math_check.py`；每重点点三档题齐备；计划可被 math-tutor 直接引用 `question_id` |

---

## 4. math-tutor

| 项 | 内容 |
|---|---|
| **Skill Name** | `math-tutor` |
| **Business Purpose** | 引导学生自己理解概念与解法，不直接给答案，并产出独立验证证据 |
| **Trigger Conditions** | 学习计划中的活动被学生开始；学生就某知识点提问 |
| **Input Contract** | `student_id*` `knowledge_point_id*` `current_question*` `learning_plan_ref` `historical_evidence[]` `previous_session` |
| **Output Contract** | `schemas/tutor-session.schema.json` |
| **Execution Steps** | 五阶段：① 基础检查（先前理解、前置知识）② 定位卡点（让学生复述过程）③ 分级提示（L1 概念提醒 → L2 方向 → L3 关键步骤 → Worked Example）④ 学生解释（要求完成下一步并说明为什么）⑤ 独立验证（换数字/换表述的新题，不给答案） |
| **Required Knowledge** | 苏格拉底式提问；hint 策略；七年级常见错误模式 |
| **Dependencies** | student-profile（读）、learning-plan（读 question_id）、知识库、`state_store.py`（写 evidence） |
| **Error Handling** | 学生索要答案 → 给提示不给完整答案，并记录 `answer_requested: true`；连续 3 级提示仍错 → 停止升级，建议回退前置知识点并生成验证题；学生答对但无法解释 → `independence: assisted` 且 `explanation_quality` 低，不得记为掌握 |
| **Confidence Policy** | 不输出主观置信度；结论性字段只有 `correctness` / `independence` / `verification.status` 三项客观记录 |
| **Security Policy** | 会话内容属学生数据（L1，不入库）；不得基于一次会话修改永久画像（R15/R18） |
| **Acceptance Criteria** | 8 类场景（完全不会 / 只知一部分 / 答对但无法解释 / 计算错误 / 反复答错 / 主动要答案 / 能独立迁移 / 只会模仿例题）；**零答案泄露**（benchmark 维度硬失败项）；每次会话必须产出可回写的 evidence |

---

## 5. 三个"能否串联"问题（本阶段的核心验收）

### Q1：homework-analysis 的输出能否直接被 knowledge-diagnosis 使用？

**能。** 字段级映射：

| 上游（analysis） | 下游（diagnosis）消费方式 |
|---|---|
| `questions[].knowledge_point_id` | 聚合主键：按知识点分桶 |
| `questions[].result` | accuracy 维度输入（`correct` vs 各类错误） |
| `questions[].student_work[].verdict` | independence 与错误定位（步骤级，而非仅最终答案） |
| `questions[].verification_status` | **门控**：`needs_human_check` 的题不计入 accuracy 分子分母，只入 `pending_verification` |
| `questions[].observations[]` | 直接进入 profile 的 observations |
| `questions[].hypotheses[]` | 进入 hypotheses，`needs_verification` 驱动 `next_verification` |
| `questions[].question_id` | 构成 `evidence_ids` 的引用锚点 |
| `summary.by_result` | 快速判定是否需整体重试 |

缺口与处置：

1. **analysis 不产出 `independence`** —— 作业天然是"课后完成"，是否独立完成无法从
   纸面判断。处置：`input.context` 增加 `completion_setting`
   （`classroom` / `home_supervised` / `home_unsupervised` / `unknown`，默认 `unknown`），
   诊断侧对 `unknown` 不参与 independence 计算，**不默认视为独立**。
2. **analysis 不产出时间戳序列** —— retention 需要跨时间证据。
   处置：evidence 的时间来自 `events.jsonl` 的 `at`，不由 analysis 提供（职责分离）。
3. **analysis 无法给出"变式题"信息** —— transfer 维度需要"同点不同形式"。
   处置：由 `question_kind`（`basic` / `variation` / `transfer` / `unknown`）标注，
   作业来源题默认 `unknown`，只有 plan/tutor 生成的题能标 `variation`/`transfer`。
   **PoC 期间 transfer 维度大概率为 `null`，这是真实状态而非 bug。**

### Q2：knowledge-diagnosis 的输出能否直接被 learning-plan 使用？

**能。** 映射：

| 上游（profile） | 下游（plan）消费方式 |
|---|---|
| `knowledge_points[].status` | 选取依据：`needs_support` / `developing` 优先，`unknown` 转验证活动 |
| `knowledge_point_id` | 重点知识点标识 |
| `dimensions.*.evidence_count` | 排序权重：证据少的先补 |
| `prerequisite_review.flagged[]` | 前置优先插入 Day 1 |
| `next_verification.question` | 直接作为 exit ticket 候选 |
| `profile.generated_at` | 过期判断（超 14 天要求重新诊断） |
| `unmapped_items[]` | 写入 `plan_notes`，提示需要人工补知识库 |

缺口与处置：

1. **`unknown` 点无法直接生成"学习计划"**（不知道该教什么）。
   处置：plan 的 `activities[].type` 允许 `diagnostic_probe`（验证性小测），
   专门处理 `unknown`，且不计入"学习重点 ≤2"的名额。
2. **plan 需要可用时间，profile 不提供**。由主 Agent 从 `profile.json` 注入
   （`available_minutes_per_day`），属输入装配职责，不由 diagnosis 负责。
3. **exam_scope 缺位**：可选输入；缺失时 plan 按 `PREREQUISITE` 深度排序，
   并在 `success_criteria` 里标注"无考试范围，按前置优先"。

### Q3：math-tutor 的会话能否作为 evidence 回写并被 diagnosis 复用？

**能，且这是闭环成立的关键。** 机制（详见 `docs/skill-dependency-map.md`）：

```
tutor 会话完成
  → 产出 client_event_id（会话内幂等键）
  → 调 state_store.py append(type="verification_result")
  → 返回 {event_id: "ev_stu_7a1f_0012", seq: 12}
  → tutor-session 输出记录该 event_id
  → 下次 diagnosis 读取 events.jsonl，把该条作为
     independence（assisted/independent）、accuracy、transfer 的证据
  → profile.evidence_ids 含 ev_stu_7a1f_0012
```

约束：

- **`hint_level_max > 1` 的会话不得记为 `independent`**（R18）
- `verification.status != program_verified && != model_checked` 时，
  该 evidence 只能支撑 `hypotheses`，不进入 accuracy 统计
- evidence 只追加，**tutor 无权修改 profile**（R15：一次会话不改永久画像）

---

## 6. 接口设计评审结论

| 检查项 | 结论 |
|---|---|
| 四个 Skill 输出是否都有 Schema | ✅ P3 落地 5 份 |
| 枚举是否统一（R8） | ✅ 集中在 `AGENTS.md` 第 4 节，Schema 引用同一组常量 |
| 信封字段是否一致 | ✅ 6 字段 + `confidence_basis` |
| Q1 能否串联 | ✅ 附 3 项缺口处置，其中 2 项需在 Schema 里新增字段 |
| Q2 能否串联 | ✅ 附 3 项缺口处置，需新增 `diagnostic_probe` 活动类型 |
| Q3 能否串联 | ✅ 依赖 `state_store.py`（ADR-0003，当前 Proposed） |
| 是否有 Skill 职责重叠 | ✅ analysis 只描述"发生了什么错误"，diagnosis 只判"掌握状态"，无重叠 |
| **是否可进入 P4** | ⚠️ **有条件可以**：`state_store.py` 未实现（ADR-0003 Proposed）、
  掌握度规则表未量化、OCR 路径未定义、教材版次未核对。四项均阻塞 P5 起的效果，
  其中版次与规则表不阻塞 P4 的 Layer 2 验收 |

**建议的最小前置动作**（P4 开工前）：

1. 人工核对教材版次 → 解除 REVIEW-QUEUE 第 1 项
2. 批准 `ADR-0003`、`ADR-0004`、`ADR-0007`
3. 定 OCR spike，决定 homework-analysis 的输入边界（文本优先 or 图像可用）
