# ADR-0007: 第三方依赖清单与审批状态

- Status: **Proposed**（`sympy` 已获批准；`jsonschema`、`pytest` 待人工批准）
- Date: 2026-11-01
- Deciders: 项目负责人（sympy）；其余待批
- Related: R21、ADR-0001、ADR-0002、ADR-0004

## 背景

`AGENTS.md` 与原始方案要求"使用标准库或经过明确批准的依赖"。
实际落地时，仅 sympy 被明确批准过；Schema 校验与测试框架也需要依赖，
否则要么手写一个不可靠的 Schema 验证器（风险：把不合法输出判为合法），
要么用 `unittest` 但失去 fixture 与参数化能力。

依赖必须显式登记，否则会在几个月后变成"没人知道为什么在这里的包"。

## 决策

### 登记清单

| 包 | 版本（实测） | 用途 | 依赖类别 | 审批状态 |
|---|---|---|---|---|
| `sympy` | 1.14.0 | 符号数学验证（ADR-0002） | **运行时** | ✅ Accepted |
| `jsonschema` | 4.26.0 | Draft 2020-12 Schema 校验（R7 / Layer 2） | 运行时（校验路径） | ⏳ Proposed，待批 |
| `referencing` | 0.37.0 | 跨文件 `$ref` 解析（本仓库**直接 import**，非仅隐式传递） | 运行时（校验路径） | ⏳ Proposed，待批 |
| `pytest` | 9.2.0 | Layer 1 单元测试（ADR-0004） | 仅开发 | ⏳ Proposed，待批 |

> `referencing` 必须单独登记的原因：它虽随 `jsonschema` 安装，但本仓库代码直接依赖其 API
> （`Registry` / `Resource.from_contents`）。若不锁版本，`jsonschema` 升级即可能悄悄破坏
> Schema 校验链路（`validate_schemas.py` 会因此 SKIP，属于会被察觉的失败，但不应依赖运气）。

环境：Python 3.14.0，项目本地 venv `.venv/`（不入库）。
**不使用其它项目的全局/共享 venv** —— 本机默认 `python` 曾指向
`C:\Users\vic\PyCharmMiscProject\.venv`，会造成不可复现的依赖环境。

### 标准库优先项（明确不引入第三方）

| 需求 | 标准库 |
|---|---|
| `PREREQUISITE` 有环检测 | `graphlib.TopologicalSorter` |
| 精确分数运算、数值双验 | `fractions.Fraction` |
| JSON 读写与顺序稳定 | `json` |
| 时间戳（含时区） | `datetime` + `zoneinfo` |
| 跨平台路径 | `pathlib` |
| 文件锁（PoC 简化实现） | `os.open(O_CREAT|O_EXCL)` |
| 随机抽样点 | `random`（seed 可固定以保证可重复） |

### 规则

1. 新增任何第三方包必须先补本 ADR（或新 ADR）并获批（ADR-0001 §判定标准 1）。
2. `requirements.txt` 锁定主次版本（`~=x.y`），禁止裸包名。
3. 运行时依赖与开发依赖分离：`requirements.txt` / `requirements-dev.txt`。
4. **不得为了少装一个包而手写 Schema 验证器**：自研验证器的错误会把不合法输出判为合法，
   直接破坏 R7。
5. 校验脚本在 `jsonschema` 缺失时**必须明确 SKIP 并非零退出**，
   禁止退化成"跳过即通过"（R25）。
6. 禁止引入会执行任意代码的解析器（`yaml.load` 非安全 loader、`sympify` 直吃模型原文、`eval`）。

## 备选方案

1. **零第三方依赖（标准库到底）** —— 否决。代数恒等判断无解（ADR-0002 备选 1 同理），
   Schema 校验只能自研，风险高于收益。
2. **用 `pydantic` 替代 jsonschema + Schema 文件** —— 当前否决。
   本项目的契约要同时给 OpenClaw 侧（非 Python）与人工审阅使用，
   JSON Schema 文件是跨语言可读的；`pydantic` 只能作为**便利层**叠加，不能替代契约本身。
   未来若引入，需新 ADR。
3. **用 `unittest` 替代 pytest** —— 可行但否决。参数化用例（数学验算的 20+ 组输入）
   在 unittest 里需要 subTest 样板代码，可读性差。列为"如批准受阻则回退方案"。

## 后果

- 正面：依赖可审计；离线可复现（venv + 锁版本）；开发与运行时依赖分离。
- 负面：sympy 导入慢（约 1–3s），批量验算需考虑常驻进程或延迟导入；
  依赖 Python 3.14 的最新生态兼容性。
- 债务：`jsonschema`、`pytest` 尚未获批但**已被本阶段使用** —— 本 ADR 的存在即为对该事实的
  显式承认，批准前不得进入部署阶段（P10）。

## 验证

- `scripts/validate_schemas.py` 在缺 `jsonschema` 时输出 `SKIP` 并以非零码退出（有单测覆盖）
- `requirements.txt` 与 `requirements-dev.txt` 内容与本表一致
- `.venv` 不出现在 `git ls-files` 中
