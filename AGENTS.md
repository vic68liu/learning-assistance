# AGENTS.md — AI Learning Copilot 工程规范

> **本文件定位**：这是**开发规范**，读者是 OpenCode（以及任何参与本仓库开发的编码代理）。
> 它**不是** OpenClaw 运行时指令。运行时指令位于 OpenClaw workspace 的 `AGENTS.md`，
> 两者职责不同，禁止互相复制粘贴（见 R3）。

---

## 0. 一句话项目定位

为中国家庭七年级学生提供数学学习辅助的 PoC：学生上传作业 → 分析 → 诊断知识掌握 →
生成三天学习计划 → 苏格拉底式辅导 → 独立验证 → 学习报告。

PoC 阶段用 **OpenClaw** 验证业务流程闭环，之后再开发正式 Web 产品。

## 1. 技术栈与运行环境

| 组件 | 角色 |
|---|---|
| OpenClaw | Agent Runtime，Skill 加载位置为 workspace 下 `skills/` |
| OpenCode | 本仓库的 Skill 开发工具（**只在开发时使用，运行时不依赖**） |
| Qwen | 主模型 |
| DeepSeek | 推理与结果对照模型 |
| Feishu | 用户交互入口 |
| OpenClaw Web Console | 开发与测试入口 |
| Python 3.11+（本机 3.14，venv 位于 `.venv/`） | 辅助脚本与测试 |
| JSON | PoC 阶段存储格式 |
| Git | 版本管理：Skill、Prompt、测试结果三类资产 |

**开发机为 Windows**（`D:\workspace\learning-assistance`）。因此：

- 任何 `.sh` 脚本必须以 LF 换行（已由 `.gitattributes` 强制），执行需 Git Bash / WSL
- Python 代码处理路径一律使用 `pathlib`，禁止硬编码 `/` 或 `\`
- 解释器使用项目 venv：`.venv\Scripts\python.exe`（Windows）/ `.venv/bin/python`（bash）

## 2. 教材依赖（本项目最重要的外部事实来源）

- 版本：**人教版（人民教育出版社）七年级上册**，按 **2024 秋新版**（2022 课标）结构建模，
  共 6 章：有理数 / 有理数的运算 / 代数式 / 整式的加减 / 一元一次方程 / 几何图形初步。
- **章名与节名必须照抄教材目录**，这是 R13 的第一道凭据。
- 当前建模依据来自公开目录资料，**尚未经实体书版权页与目录页人工核对**，
  该待办记录在 `knowledge-base/REVIEW-QUEUE.md` 第 1 项。核对完成前：
  - `grade-7-math.json` 顶层 `review_status` 必须为 `pending_review`
  - 任何 Skill 不得基于该知识库输出面向用户的掌握度结论
- PoC 范围：**第 1–5 章（数与代数）**。第 6 章几何图形初步暂缓，理由见
  `docs/decisions/ADR-0006`。

## 3. 治理条款（不可协商）

以下条款逐条生效。任何代码、文档、Prompt 与之冲突时，以本文件为准。

### 3.1 Skill 本质

- **R1** Skill 是带 `SKILL.md` 的目录，可含 `references/` 与 `scripts/`；**Skill ≠ Agent，Skill ≠ Workflow**。
- **R2** `SKILL.md` 用 YAML frontmatter 定义身份（至少 `name`、`description`、`user-invocable`），
  正文描述"如何完成任务"；确定性计算交给脚本，复杂规则交给 `references/`；
  禁止把所有内容塞进单个超长 Prompt。
- **R3** 本文件（开发规范，给 OpenCode 看）与 OpenClaw workspace `AGENTS.md`（运行时指令，给 Agent 看）
  是两个文件，职责不得混淆，内容不得互相复制。
- **R4** Skill 必须可被 OpenClaw 独立加载运行，不得依赖 OpenCode 才能工作。

### 3.2 边界与契约

- **R5** 一个 Skill 只负责一个明确业务能力；职责不重叠。
- **R6** 每个 Skill 的输入、输出、执行步骤、错误处理必须显式定义，并有对应 JSON Schema。
- **R7** 所有模型输出必须先通过 Schema 校验才算有效结果。
- **R8** 跨 Skill 的字段命名与枚举值必须使用第 4 节统一词表，禁止各自发明。
- **R9** 数据 Schema 变更必须保持向后兼容；破坏性变更需 ADR + 迁移脚本。

### 3.3 认知诚实

- **R10** 观察到的事实（`observations`）与原因推断（`hypotheses`）必须分离存放，不得合并表述。
- **R11** 不确定内容（OCR 置信度低、题干残缺）必须标记 `uncertain`，禁止静默修正或猜测补全。
- **R12** 数学根因不能确定时，只能记为 hypothesis，并必须给出下一步验证题。
- **R13** 禁止虚构教材章节、知识点、知识点 ID；无法映射时使用 `unmapped`，不得新增 ID。
- **R14** 知识点 ID 的唯一合法来源是 `knowledge-base/grade-7-math.json`；
  该文件由人工审核维护，模型只能读取，不得写入或推断新条目。

### 3.4 教育伦理

- **R15** 单次答题不得判定学生永久掌握或未掌握。
- **R16** `unknown` 与 `needs_support` 语义严格不同：无证据即为 `unknown`，
  禁止当作 `needs_support` 输出。
- **R17** 掌握状态判定必须按 `references/` 中的**显式量化规则表**执行，禁止模型凭语感判断；
  规则表由确定性脚本实现。
- **R18** 提示后答对（`assisted`）不等于独立掌握（`independent`），两者必须分别记录。
- **R19** 学习计划的答案与解析必须独立存储，不得在学生尝试前出现在同一响应中。
- **R20** 禁止给学生贴能力、智力或性格标签。

### 3.5 可验证性与安全

- **R21** 数学验算使用确定性代码：算术与代数统一由 **sympy** 求解，再做数值抽样双验
  （symbolic 与 numeric 结果一致才允许标记 `program_verified`）。
  禁止 `eval()`、禁止执行模型生成的任意代码；送入 sympy 的表达式必须先经
  `scripts/math_check.py` 的白名单解析器（仅允许数字、变量 `x`/`y`、`+ - * / ^`、
  括号、分数、根号的受限文法），解析失败即 `needs_human_check`。
  符号验证超时、含图形/表格/应用题语义、或双验不一致 → 一律降级并记录原因。
- **R22** 历史 evidence 采用 append-only，禁止覆盖或删除。
- **R23** 学生数据一律使用 pseudonymous ID（形如 `stu_7a1f`），禁止真实姓名、校名、班级、
  人脸、含姓名的作业照片进入仓库。
- **R24** API Key 与凭证只能来自环境变量或本地未跟踪文件，禁止进入源码、日志、Git。
- **R25** 未运行测试不得声称通过；未获得 OpenClaw 加载确认不得声称部署成功；
  禁止编造任何测试结果或评分。
- **R26** 业务规则变更必须同步新增或修改测试用例。

### 3.6 流程

- **R27** 一次只开发一个 Skill；一个阶段验收通过并 Git 提交后，才进入下一阶段。
- **R28** 每个重要设计决策写 ADR（`docs/decisions/ADR-NNNN-title.md`），格式见 `ADR-0001`。
- **R29** 每个阶段结束必须报告：新建文件、修改文件、实际执行的测试与真实结果、
  已知缺口、建议下一步。

## 4. 统一词表（Schema 与所有 Skill 共用，一字不差）

```
mastery status      : mastered | developing | needs_support | unknown
error type          : correct | calculation_error | concept_error | method_error
                      | incomplete | unreadable | needs_human_check
verification status : program_verified | model_checked | needs_human_check | not_applicable
independence        : independent | assisted | not_attempted
relation type       : PREREQUISITE | CONTAINS | RELATED | SIMILAR | EASILY_CONFUSED | TRANSFER_TO
review status       : reviewed | pending_review | rejected
```

**通用信封字段**（所有 Skill 输出顶层必须包含）：

```
schema_version  skill_name  prompt_version  generated_at
student_id      confidence
```

`confidence` 取值域 `[0.0, 1.0]`，且必须附带 `confidence_basis`（说明该数字从何而来）。
无法给出依据时，`confidence` 必须为 `null`，而不是取中间值。

## 5. 目录约定

```
AGENTS.md                 本文件：开发规范
README.md                 开发/测试/部署流程
opencode.json             OpenCode 项目配置

skills/                   业务 Skill（本阶段为空，见 docs/development-roadmap.md）
knowledge-base/           知识点与关系：人工审核维护，模型只读
schemas/                  JSON Schema：数据契约唯一真相
scripts/                  确定性脚本：校验、验算、ID、状态存储
tests/                    Layer 1 单元测试（pytest）
benchmark/                Layer 3 语义质量评测
docs/                     架构、契约、路线图、测试与部署报告
docs/decisions/           ADR
student-data/             真实学生数据，永不入库（R23）
test-data/                只允许合成/脱敏数据
```

## 6. ID 与数据规则

- 知识点 ID：`g7.math.<册码><章序>.<节序>.<点序>`，册码 `a`=七上、`b`=七下。
  例 `g7.math.a04.02.04` = 七上第 4 章 4.2 节第 4 个诊断点。三级小节（如 `4.1.1`）不入 ID，
  存于 `subsection_title` 字段。
- 学生 ID：`stu_<4位十六进制>`，由 `scripts/new_id.py` 生成，禁止由模型自行编造。
- evidence ID：`ev_<学生ID>_<单调序号>`，append-only，序号永不复用、永不回填。
- 知识点删除一律用 `deprecated: true` 标记，禁止物理移除，以保证历史 evidence 永久可解析（R22 前提）。
- 详细规则见 `docs/decisions/ADR-0003`（状态所有权）与 `ADR-0006`（ID 与废弃策略）。

## 7. 测试分层（ADR-0004）

| 层 | 对象 | 工具 | 判定 |
|---|---|---|---|
| Layer 1 单元测试 | 脚本与确定性函数 | `pytest` | 可断言，必须可重复 |
| Layer 2 契约测试 | 模型输出结构 | `jsonschema` + `scripts/validate_*.py` | Schema 合规率 100% 才算过 |
| Layer 3 Benchmark | 语义质量 | `benchmark/` + 人工评分 | 记录真实 `model_id`/`prompt_version`/原始响应 |

硬性约束：

1. Layer 3 的 `model_output` 必须来自真实模型调用，**禁止由开发过程生成或改写**。
2. `gold_output` 必须人工审核并标注 `reviewed_by` 与日期。
3. 改 Prompt 后必须用 `--baseline-run` 与历史运行对比，不得只看绝对分数。
4. 报告必须能区分：模型能力问题 / Skill Prompt 问题 / 知识库问题 / 测试数据问题 / 数学验证问题。

## 8. 阶段门禁

| 阶段 | 产出 | 进入下一阶段的必要条件 |
|---|---|---|
| P1 基线 | 本文件 + 骨架 + `.gitignore` | R1–R29 可逐条核对 |
| P2 契约 | `docs/skill-contracts.md` + ADR | 第 5 节三个"能否串联"问题有字段级答案 |
| P3 Schema | `schemas/*.json` + 校验脚本 | `validate_schemas.py` 与 pytest 全绿 |
| P3.5 知识库 | `grade-7-math.json` T1 批次 | **人工核对教材版次 + 审核 26 个点** |
| P4 homework-analysis | 首个 Skill | 20 用例 Layer2 全过，验算覆盖率有实测数字 |
| P5–P7 其余 Skill | diagnosis / plan / tutor | 各自契约验收 |
| P8 集成 | Workflow | 端到端演示可复现，不假装 Markdown 自动执行 |
| P9 Benchmark | 模型对比 | ≥30 人工审核案例 |
| P10 部署 | OpenClaw skill 安装 | `openclaw skills list` 确认加载 |

**R27**：一次只推进一个阶段，先验收再提交。

## 9. 完成任务前必须自检并汇报

```bash
.venv/Scripts/python.exe scripts/validate_schemas.py
.venv/Scripts/python.exe scripts/validate_skills.py
.venv/Scripts/python.exe scripts/validate_knowledge_base.py
.venv/Scripts/python.exe -m pytest -q
git ls-files | grep -Ei "student-data|\.env|key|credentials"   # 期望：无输出
```

汇报格式（R29）：新建文件 / 修改文件 / 实现细节 / 实际执行的测试与其真实输出 /
已知缺口 / 建议下一步。

## 10. 当前已知缺口（不得假装已解决）

1. **教材版次未经实体书核对** —— 阻塞 P3.5 的 `reviewed` 状态。
2. **OCR / 图像输入路径未定义** —— 谁做手写识别、图片如何进入 Skill 尚无方案；
   homework-analysis 的真实准确率上限取决于此。计划为 P4 前做一次 OCR spike。
3. **sympy 对应用题与几何无效** —— 第 5.3 节实际问题与第 6 章几何题将大面积落在
   `needs_human_check`，这是设计选择而非 bug。
4. **无 Workflow Engine** —— PoC 由主 Agent 按序调用 Skill + `scripts/state_store.py` 持久化状态；
   在真正引入状态机之前，任何"自动编排"表述都不成立。
5. **依赖审批** —— `sympy` 已批准（ADR-0002）；`jsonschema`、`referencing`、`pytest`
   已在 `ADR-0007` 登记但仍为 `Proposed`，**批准前不得进入部署阶段（P10）**。
   本阶段代码已实际使用它们，ADR-0007 显式承认了这一事实。
