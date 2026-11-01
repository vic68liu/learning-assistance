# student-data/ — 永不入库

本目录存放真实学生数据。**除本 README 外，全部内容被 `.gitignore` 排除。**

依据 `AGENTS.md` R23 / R24 与 `docs/decisions/ADR-0005`。

## 允许存在于本目录的内容（仅本地）

```
student-data/
└── stu_7a1f/                     # 以 pseudonymous ID 分目录
    ├── profile.json              # 年级、教材版本、可用学习时间
    ├── homework/
    │   ├── hw_2026_10_31/
    │   │   ├── raw/              # 原始作业照片（绝不入库）
    │   │   ├── analysis.json     # homework-analysis 输出
    │   │   └── diagnosis.json
    ├── evidence.jsonl            # append-only 学习证据，序号永不复用
    ├── plans/
    └── sessions/
```

## 绝对禁止

- 真实姓名、校名、班级、学号写入任何 JSON 字段或文件名
- 含姓名/班级抬头页的作业照片被转录进仓库内的文本
- 把本目录任何文件 `git add -f` 强制加入 —— **这是不可协商的红线**
- API Key 放进本目录（凭证只走环境变量或未跟踪的本地文件）

## 为什么必须脱敏后再进 test-data/

测试与 benchmark 需要的题目文本，必须是**人工重打或合成**的版本，
不接受"把照片里的字复制出来"这种形式：原始笔迹本身即个人特征信息。
流程见 `ADR-0005`。
