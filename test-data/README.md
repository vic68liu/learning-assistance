# test-data/ — 只允许合成或脱敏数据

本目录存放**可公开**的测试数据。与 `student-data/` 的边界是唯一的判断标准：
**如果这份数据来自某个真实孩子的作业，它就不该出现在这里。**

## 入库规则

| 允许 | 禁止 |
|---|---|
| 人工重打的题干文本 | 作业照片、扫描件、PDF 拍照页 |
| 自行构造的题目与学生作答文本 | 录音、截图（含姓名/班级/头像） |
| 手写作答的**模拟文本**（按真实错误模式编写） | 从照片 OCR 出来的原文（未改写、含个人笔迹特征） |
| 已审核的 `expected-results.json` | 未审核答案当作 gold 标准 |

图片、PDF、音视频文件已被 `.gitignore` 全量排除（见 `test-data/**/*.{jpg,png,pdf,...}` 规则）。
**不要**为"测试方便"而取消这些规则。

## 目录结构（Skill 开发阶段填充）

```
test-data/
├── homework-analysis/
│   ├── synthetic/                 # 合成题干与作答文本
│   │   ├── case_001.json
│   │   └── ...
│   └── README-case-format.md      # 案例格式说明
└── textbook/                      # 教材目录摘录（用于 R13 溯源，不含习题照片）
    └── renjiaobu-7a-2024-outline.md
```

## gold 标准的要求（ADR-0004）

- 每道题的参考答案与解析必须**人工审核**，记录 `reviewed_by` 与日期
- 数学结论必须能通过 `scripts/math_check.py` 的 sympy 验算；不能通过验算的题目
  只能作为"需要人工复核"路径的测试用例
- 错误模式必须对应 `AGENTS.md` 第 4 节的 `error type` 枚举，禁止自造分类
