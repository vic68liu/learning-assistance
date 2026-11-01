# knowledge-base/

知识点与知识关系。**人工审核维护，模型只读。**

这是 `AGENTS.md` R14 的落地点：四个 Skill 唯一允许的知识点 ID 来源就是本目录的
`grade-7-math.json`。模型不得写入、不得推断新条目、不得虚构章节（R13）。

## 文件

| 文件 | 内容 | 真相地位 |
|---|---|---|
| `grade-7-math.json` | 知识点清单（章/节/诊断点三级 + 元数据） | 知识点 ID 的唯一来源 |
| `knowledge-relations.json` | 知识点之间的关系边 | 关系类型的唯一来源 |
| `outline-t1.csv` | **人工输入**：教材目录摘录 + 高频错误观察 | 上述两文件的溯源凭据 |
| `REVIEW-QUEUE.md` | 待人工确认清单 | 状态从 `pending_review` 变 `reviewed` 的唯一途径 |
| `grade-7-math.schema.json` → 实际位于 `schemas/knowledge-point.schema.json` | 结构约束 | Layer 2 校验依据 |

## ID 规则（ADR-0006）

```
g7.math.a04.02.04
│ │  │  │  │  └── 诊断点序号：该节内单调递增，永不复用、永不回填
│ │  │  │  └───── 节：4.2 → "02"
│ │  │  └──────── 章：第四章 → "04"
│ │  └─────────── 册码：a = 七上，b = 七下
│ └────────────── 学科
└──────────────── 学段
```

- 三级小节（如 `1.2.3 相反数`）**不进 ID**，存 `subsection_title` 字段，避免编码过长且便于章内重排。
- 知识点废弃一律 `deprecated: true` + `deprecated_at`，**禁止物理删除** ——
  否则历史 evidence 会指向不存在的 ID，违反 R22。

## 诊断粒度规则

一个知识点应当独立成"诊断点"，当且仅当满足以下任一条件：

1. **可分离失败**：学生可能对 A 全对、对 B 全错
2. **补救动作不同**：需要不同的教学干预（符号约定 vs 运算法则）
3. **错误类型分布不同**：一处偏 `concept_error`，一处偏 `calculation_error`

**不应**独立成点：只是数字规模不同、只是题目情境不同、只是"简单/困难"的差异。

这条规则决定了能否为每个点单独出验证题（`learning-plan` 与 `math-tutor` 都依赖这点）。

## 关系边的方向与 `origin` 字段 —— 关键治理设计

**方向定义：`from` 依赖 `to`，即 `to` 是 `from` 的前置知识。**
所以"先会同类项判定，才会合并同类项"要写成 `from=合并同类项 → to=同类项判定`：

```json
{ "from": "g7.math.a04.02.02", "to": "g7.math.a04.02.01",
  "type": "PREREQUISITE", "origin": "human", "confidence": 1.0 }
```

`EASILY_CONFUSED` / `SIMILAR` / `RELATED` 是对称关系，只存一条边，读侧按无向处理。

| origin | 含义 | 使用限制 |
|---|---|---|
| `human` | 来自 `outline-t1.csv` 的人工填写 | 可直接用于诊断结论 |
| `inferred` | OpenCode 从结构推断（如节内相邻、章节顺序） | **未过 REVIEW-QUEUE 前，禁止用于给出掌握度结论** |

这是 R13/R14 唯一真正可执行的约束点：把"不许瞎编"变成"来源可查、未审即禁用"。

## 维护流程

1. 人工修改 `outline-t1.csv`（教材照抄 + 教学观察）
2. 用 OpenCode 按脚本结构化 → 生成/更新 `grade-7-math.json` 与 `knowledge-relations.json`
   （OpenCode 只能做：字段拆分、ID 分配、一致性检查、把推断关系写入 REVIEW-QUEUE）
3. 运行校验：
   ```bash
   .venv/Scripts/python.exe scripts/validate_knowledge_base.py
   ```
   检查项：ID 格式与唯一性、`PREREQUISITE` 无环、孤儿节点、`from/to` 引用存在性、
   枚举合法性、**CSV 与 JSON 的同步性**（标题集合、章名节名、册码，以及 PREREQUISITE 边
   必须与 CSV 的 `prereq` 列一一对应）。任一失败即非零退出。
4. 人工逐条处置 `REVIEW-QUEUE.md`，把确认无误的条目改为 `review_status: "reviewed"`
   并填 `reviewed_by` / `reviewed_at`
5. Git 提交，commit message 用 `feat(knowledge-base): ...`

> CSV 同步检查不是锦上添花：本次开发中它立刻抓到一个真实缺陷 ——
> JSON 与 CSV 对同一个知识点写了两个不同标题。没有这道检查，
> "知识点来自人工大纲"就会慢慢退化成一句无法核查的话。

## 当前状态

- 范围：人教版七年级上册 **第 1–5 章**（数与代数），T1 批次 **26 个诊断点**、
  **44 条关系边**（PREREQUISITE 38 条，已通过 DAG 检测）。
  分布：第1章 5 / 第2章 9 / 第3章 2 / 第4章 5 / 第5章 5。
- 第 6 章几何图形初步**已显式记录为排除项**并附理由与重入条件（见 JSON 的 `scope.excluded`）；
  两个「综合与实践」不建诊断点。
- 顶层 `review_status`: **`pending_review`**，全部条目 `origin: inferred` ——
  因为教材版次尚未经实体书核对（REVIEW-QUEUE 第 1 项），且诊断点拆分与高频错误观察需人确认。
  在此状态解除前，任何 Skill 不得基于本知识库输出面向用户的掌握度结论。
