# AI Learning Copilot

七年级数学学习辅助 PoC。用 **OpenClaw** 跑通业务闭环，用 **OpenCode** 开发 Skill。

```
学生上传作业 → 作业分析 → 知识诊断 → 三天学习计划 → 数学辅导 → 独立验证 → 学习报告
```

> 工程规范（R1–R29 治理条款）在 [`AGENTS.md`](AGENTS.md)，不是本文件。
> 架构见 [`docs/architecture.md`](docs/architecture.md)，进度见 [`docs/development-roadmap.md`](docs/development-roadmap.md)。

## 当前状态

**P1–P3.5：工程基线 + 数据契约 + 知识库结构化。** 业务 Skill 尚未开发（`skills/` 为空）。

已知阻塞项：教材版次待人工核对、OCR/图像输入路径未定、`jsonschema`/`pytest` 依赖待正式批准。
详见 `AGENTS.md` 第 10 节与 `knowledge-base/REVIEW-QUEUE.md`。

## 环境准备

```bash
# 1. 项目本地虚拟环境（勿复用其它项目的 venv）
python -m venv .venv

# 2. 安装依赖
.venv/Scripts/python.exe -m pip install -r requirements.txt      # Windows
.venv/bin/python -m pip install -r requirements.txt              # Git Bash / WSL
```

Python 3.11+（本项目在 3.14 上开发）。依赖清单与审批状态见 `docs/decisions/ADR-0007`。

## 开发流程

```bash
# 用 OpenCode 打开工程根目录
cd D:/workspace/learning-assistance
opencode
# 首次运行 /init，然后按 docs/development-roadmap.md 的阶段逐个提交 Prompt
```

铁律（R27）：**一次只推进一个阶段，先验收，再 Git 提交，才进入下一阶段。**
禁止让编码代理在一次任务里连续跑完多个阶段。

## 测试与校验

四条命令，任何一次代码提交前都必须全绿（AGENTS.md 第 9 节）：

```bash
P=.venv/Scripts/python.exe        # bash 下改用 .venv/bin/python

$P scripts/validate_schemas.py             # Schema 自身合法 + 内置示例可自校验
$P scripts/validate_skills.py              # Skill 目录结构与 frontmatter（空目录时为 SKIP）
$P scripts/validate_knowledge_base.py      # 知识点 ID 规范 + PREREQUISITE 无环检测
$P -m pytest -q                            # Layer 1 单元测试
```

另外必须确认没有学生数据或凭证被跟踪：

```bash
git ls-files | grep -Ei "student-data|\.env|key|credentials"     # 期望无输出
```

## 提交规范

Conventional Commits，按阶段分组，**禁止 `git add .`**（必须显式列出 pathspec）：

```bash
git status --short
git add .gitignore AGENTS.md README.md          # 显式列文件
git commit -m "feat(skill): implement homework analysis"
```

常用 type：`chore`（骨架/配置）、`docs`（契约/ADR）、`feat(schemas)`、`feat(knowledge-base)`、
`feat(skill)`、`test`、`fix`。

## 目录

| 路径 | 内容 |
|---|---|
| `skills/` | 四个业务 Skill（待开发） |
| `knowledge-base/` | 知识点与关系，**人工审核维护，模型只读** |
| `schemas/` | JSON Schema，数据契约唯一真相 |
| `scripts/` | 确定性脚本：校验、验算、ID、状态存储 |
| `tests/` | Layer 1 单元测试 |
| `benchmark/` | Layer 3 语义质量评测与模型对比 |
| `docs/` | 架构、契约、路线图、各类报告 |
| `docs/decisions/` | ADR-0001 ~ ADR-0007 |
| `student-data/` | 真实学生数据，**永不入库** |
| `test-data/` | 只允许合成/脱敏数据 |

## 部署到 OpenClaw（尚未执行）

Skill 需部署到 OpenClaw workspace 的 `skills/` 目录，并在部署后用
`openclaw skills list` 确认加载。**未获得加载确认前，不得声称部署成功**（R25）。
部署与回滚流程见 `docs/development-roadmap.md` P10；本阶段尚无可用 Skill。

## 隐私

学生数据使用 pseudonymous ID（`stu_xxxx`，由 `scripts/new_id.py` 生成）。
作业照片、含姓名班级的任何素材一律被 `.gitignore` 排除，不得手工绕过。
