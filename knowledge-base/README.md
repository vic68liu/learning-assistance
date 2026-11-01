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

## 关系边的 `origin` 字段 —— 关键治理设计

```json
{ "from": "g7.math.a04.02.01", "to": "g7.math.a04.02.02",
  "type": "PREREQUISITE", "origin": "human", "confidence": 1.0 }
```

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
   枚举合法性。任一失败即非零退出。
4. 人工逐条处置 `REVIEW-QUEUE.md`，把确认无误的条目改为 `review_status: "reviewed"`
   并填 `reviewed_by` / `reviewed_at`
5. Git 提交，commit message 用 `feat(knowledge-base): ...`

## 当前状态

- 范围：人教版七年级上册 **第 1–5 章**（数与代数），T1 批次 26 个诊断点。
  第 6 章几何图形初步暂缓（理由：sympy 无法符号验算图形题、且图像输入路径未定义，
  会污染 benchmark 的归因能力）。
- 顶层 `review_status`: **`pending_review`** —— 因为教材版次尚未经实体书核对（REVIEW-QUEUE 第 1 项）。
  在此状态解除前，任何 Skill 不得基于本知识库输出面向用户的掌握度结论。
