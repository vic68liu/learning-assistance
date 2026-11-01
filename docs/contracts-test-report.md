# P3 / P3.5 契约与知识库验收报告

- 日期：2026-11-01
- 范围：工程基线（P1）、契约（P2）、Schema 与确定性脚本（P3）、知识库结构化（P3.5）
- 结论：**M1 达成；M2 未达成（等待人工审核，非技术问题）**
- 原则：本报告只记录**实际执行过**的命令与其真实输出（R25）

## 1. 环境

```
OS       Windows（D:\workspace\learning-assistance）
Python   3.14.0（项目本地 venv .venv/，未复用外部 venv）
sympy    1.14.0     jsonschema 4.26.0     referencing 0.37.0     pytest 9.2.0
git      2.53.0.windows.2
```

## 2. 实际执行结果

```console
$ .venv/Scripts/python.exe scripts/validate_schemas.py
OK: 6 份 Schema 元校验通过，信封字段与枚举集中性一致，示例全部满足自身契约        exit=0

$ .venv/Scripts/python.exe scripts/validate_skills.py
SKIP: skills/ 下暂无 Skill（P3 阶段的正常状态）。未做加载检查。                  exit=0

$ .venv/Scripts/python.exe scripts/validate_knowledge_base.py
OK: 知识库结构合规 —— 26 个有效知识点 / 26 总数 / 44 条关系边
    （其中 PREREQUISITE 38 条，DAG 通过）
  按章分布: {'a01': 5, 'a02': 9, 'a03': 2, 'a04': 5, 'a05': 5}
  ⚠ 仍有 26 个知识点未人工审核；1 组待确认推断关系见 knowledge-base/REVIEW-QUEUE.md  exit=0

$ .venv/Scripts/python.exe -m pytest -q
103 passed in 3.18s

$ git ls-files student-data
student-data/README.md      # 仅说明文件，无任何学生数据

$ git ls-files | grep -Ei "student-data/.+\.(jpg|png|pdf)|\.env|key|credentials"
（无输出）
```

按章分布与规划一致：第1章 5 / 第2章 9 / 第3章 2 / 第4章 5 / 第5章 5 = **26**。

## 3. 数学验算实测（ADR-0002 的 verification_status 真实表现）

```console
-(2*x-3)+x   == -x+3   -> program_verified  equal=True
-(2x-3)+x    == -x-3   -> program_verified  equal=False  witness={x:1, lhs:2, rhs:-4}
-2**4        == 16     -> program_verified  equal=False  witness={lhs:-16, rhs:16}
(-2)**4      == 16     -> program_verified  equal=True
2*(x+3)-5(x-1)=3(2-x)  -> program_verified  reason=equation_has_no_real_solution
2x+3=7, x=2            -> program_verified  equal=True
"2 1/2"                -> needs_human_check reason=parse_failed:mixed_number_unsupported
'__import__("os")'     -> needs_human_check reason=parse_failed:illegal_character
```

三点值得注意：

1. **隐式乘法被支持**（`2x` 可直接解析），符合学生手写习惯；
   但并列数字（`2 1/2` 带分数）被**拒绝**而不是猜测成 `2.5` —— 这是 R11 的直接体现。
2. 判不等时返回**可复核的数值反例**，而不是只给一个"不相等"的断言。
3. 注入与非法文法一律降级为 `needs_human_check`，异常不穿透到调用层。

**尚未实测的部分**：本阶段无真实作业数据，因此"算术题 program_verified ≥95%"等目标
只是 ADR-0002 的**目标值**，没有实测支撑。真实分布必须在 P4 的 20 用例上得出（M3 判据）。

## 4. 教育伦理已进入"可机械判定"的部分

以下规则现在由 Schema 强制，模型无法靠措辞绕过（Layer 2 可直接断言）：

| 规则 | 强制方式 | 测试 |
|---|---|---|
| R18 提示后答对 ≠ 独立掌握 | `hint_level_max ∈ [2,3,4]` → `independence` 必须 `assisted` | `test_hint_level_2_forces_assisted_outcome` |
| R16 unknown ≠ needs_support | `status=unknown` → `evidence_ids` 必空、`confidence` 必 null | `test_unknown_status_with_evidence_is_rejected` |
| 无证据不得编造数值 | `evidence_count=0` → `value` 必须 null | `test_zero_evidence_metric_must_have_null_value` |
| R19 答案不得先于尝试出现 | 计划 Schema 内**不存在**答案字段，仅 `answer_key_ref` | 结构保证 |
| 不得泄露答案 | `outcome.answer_revealed` 为 `const false`（无合法值可表达泄露） | `test_answer_revealed_true_is_impossible` |
| R25 降级必须可解释 | `needs_human_check` → 必填 `verification_reason` | 结构保证 |
| R13 未映射必须可追溯 | `unmapped/partial` → 必填 `unmapped_description` | 结构保证 |
| 一次会话不改永久画像 | tutor 无权写 profile，仅写 evidence（`evidence_write` 须带回 store 分配的 id） | `test_...` + ADR-0003 |
| 声称已审核须有凭据 | `review_status=reviewed` → 必填 `reviewed_by`/`reviewed_at` | `test_reviewed_top_status_requires_credentials` |
| 废弃不得物理删除 | `deprecated=true` → 必填 `deprecated_at`/`deprecated_reason` | 结构保证 |
| R8 枚举集中 | 内联重复统一词表 → 校验失败；死定义 → 校验失败 | `test_inlined_duplicate_enum_is_caught` |

## 5. 开发过程中被测试/校验抓到的真实缺陷（已全部修复）

如实记录，因为这类信息决定后续阶段该在何处加防护：

| # | 缺陷 | 如何被发现 | 修复 |
|---|---|---|---|
| 1 | `kp_id.split("g7.math.", 1)` 按 3 值解包 → `ValueError`，**同一 bug 复制到两个文件** | `test_new_id` + KB 校验 12 项失败 | 改为 2 值解包；教训：跨文件复制的解析逻辑应收敛到 `new_id.py` 单一出口 |
| 2 | `sympy.denom()` 对未合并的 Add 返回 1，导致"解使分母为 0"未被识别，错判为 `program_verified` | `test_verify_solution_rejects_value_making_denominator_zero` | 先 `together()` 再取 `denom()` |
| 3 | `solve_equation` 对无解方程返回 `solutions: []` 且标 `program_verified` → 下游会把无解题当可用题 | 手动跑真实方程发现 | 显式区分 `EmptySet`，返回 `reason=equation_has_no_real_solution`，并加"不可达空集"保护 |
| 4 | 危险命令正则扫 `.md` 文档，把规范文字"禁止 eval()"判为违规（11 处误报） | `test_real_repo_has_no_secrets_in_scripts` | 危险命令只扫可执行文件；文档只扫凭证 |
| 5 | `re.compile` 被判为危险的 `compile()` 调用 | 同上测试 | 改 AST 判定，只禁裸名 `eval/exec/compile` |
| 6 | JSON 与 CSV 对同一知识点写了两个不同标题（`有理数减法法则` vs `减法转化为加法…`） | 新加的 CSV 同步检查**首次运行即抓到** | 统一标题；并把该检查固化为回归项 |
| 7 | `{"type": ["string","null"], "$ref": ...}` 组合使 `null` 不合法（`$ref` 内含 `type: string`） | 示例自校验失败 | 3 处改为 `anyOf: [ref, {type: null}]` |
| 8 | 死定义：`envelope_skill_name`（改用 `const` 后遗留）、`relation_type`（无 Schema 引用它） | `check_defs_usage` | 删前者；后者改为由 `validate_knowledge_base.py` 从 `common.defs.json` **读取**，消除脚本内第二份枚举字面量 |
| 9 | 关系边方向语义在 README 示例中被写反（`from 依赖 to`） | 自查契约 | 显式写明方向定义并修正示例，`knowledge-relations.json` 内置 `semantics` 字段 |

## 6. 已知缺口（不得假装已解决）

1. **教材版次未经实体书核对** —— 全部 26 点为 `origin: inferred` + `pending_review`；
   `review_status` 非 `reviewed` 前，Skill 不得输出面向用户的掌握度结论。**阻塞 M2 与 P4 的实际效果**。
2. **`state_store.py` 未实现**（ADR-0003 仍为 Proposed）→ evidence 生命周期、
   ID 分配、幂等、append-only 目前只有契约与规则，没有落地实现。P4 落盘路径依赖它。
3. **OCR/图像输入未 spike** —— homework-analysis 的真实质量上限未知；
   `input.ocr` 字段结构已就绪，但没有任何真实识别数据填充过。
4. **掌握度规则表未量化** —— `mastery-rules.md` 属 P5；
   `rule_applied` 字段已预留（强制强结论引用规则编号），但规则表本身不存在。
5. **Layer 2 尚未跑过真实模型输出** —— 目前只校验过 Schema 自带的 examples。
   "合规率 100%"这句话要到 P4 才有实证意义。
6. **`jsonschema` / `referencing` / `pytest` 未获正式批准**（ADR-0007，Proposed）。
7. **benchmark 完全未建** —— 30 个人工审核案例、评分规则、模型对比脚本均属 P9。
8. **Windows 路径与 `--strict` 未验证** —— 若 CI 化需补 bash 侧 `PYTHONIOENCODING=utf-8`
   （本次开发中已遇到 GBK 控制台乱码，非功能缺陷但影响可读性）。

## 7. 里程碑判据对照

- **M1（P3 完）**："5 份 Schema 自身合法，内置示例全部通过自校验；pytest 全绿，
  其中 `math_check.py` 的 4 类对抗用例全部通过。" → ✅ **达成**
  （Schema 实为 6 份，含共享定义文件）
- **M2（P3.5 完）**："26 个知识点，PREREQUISITE 无环，教材版次经人工核对，`review_status: reviewed`。"
  → 🟡 **部分达成**：26 点 ✅、DAG 无环 ✅、人工核对 ❌（等你执行 REVIEW-QUEUE 第 1、2 项）

## 8. 是否可以进入 P4

**技术上可以，效果上有风险。** 建议顺序：

1. 你处置 `knowledge-base/REVIEW-QUEUE.md` 第 1、2 项（预计 15–20 分钟，只需看课本目录 + 勾选）
2. 批准 `ADR-0003` / `ADR-0004` / `ADR-0007`（决定是否照此实现 `state_store.py`）
3. P3.7 OCR spike（10 张题照，决定 homework-analysis 的输入边界）
4. 才开始 P4

若跳过 1–3 直接写 homework-analysis，最可能的结果是：Skill 逻辑正确，
但知识点 ID 事后要重排、验算覆盖率数字无法解释、图像分支从未被验证。
