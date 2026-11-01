# benchmark/ — Layer 3 语义质量评测

依据 `docs/decisions/ADR-0004`。这里做的是**质量评分**，不是单元测试。

## 与 skills/*/tests 的分界

| | 位置 | 验证什么 | 能否断言 |
|---|---|---|---|
| Layer 1 | `tests/` | 确定性脚本的行为 | ✅ pytest 断言 |
| Layer 2 | `scripts/validate_*.py` | 模型输出的结构合规（Schema、枚举、ID 合法性） | ✅ 合规率 100% |
| Layer 3 | `benchmark/` | 模型输出的**语义质量**（诊断是否合理、提示是否泄露答案） | ❌ 需人工/评审模型打分 |

一句话：**能被 `assert` 的放 tests/，需要人来判断好坏的放这里。**

## 文件规划（P9 阶段实现）

```
benchmark/
├── cases.json                        # 案例：case_id / skill_name / input / gold_output
├── evaluation-rules.yaml             # 0~5 分评分标准与维度权重
├── runs/
│   └── <run_id>/
│       ├── manifest.json             # model_id / prompt_version / 模型参数 / 日期
│       ├── scores.json               # 评分结果
│       └── artifacts/                # 原始响应（.gitignore 排除）
└── reports/
    └── model-comparison-report.md    # Qwen vs DeepSeek 对比
```

## 硬约束（不得违反）

1. `model_output` **必须来自真实模型调用**。禁止由开发过程生成、补写或"修正"期望输出（R25）。
2. `gold_output` 必须人工审核并记录 `reviewed_by` + 日期。
3. 每个案例必须记录 `model_id`、`prompt_version`、`evaluator`、`score`、`failure_reason`。
4. 报告必须能区分五类失败原因：模型能力 / Skill Prompt / 知识库 / 测试数据 / 数学验证。
5. 必须展示**具体失败案例**，不得只给总分。
6. 回归：对比历史基线用 `--baseline-run`，而不是只看绝对分数。

## 规模说明（诚实标注）

P9 的 ≥30 案例只是**第一轮最低门槛**，不足以证明模型对七年级数学普遍可靠。
正式评估需覆盖：不同题型、不同手写质量、不同错误类型、不同难度层级。

## 当前状态

空目录。四个 Skill 尚未开发，尚无评测对象。
