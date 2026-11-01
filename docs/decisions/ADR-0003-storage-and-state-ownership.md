# ADR-0003: 存储与状态所有权

- Status: **Proposed**（待人工批准）
- Date: 2026-11-01
- Deciders: OpenCode 起草，待项目负责人确认
- Related: R22、R23、ADR-0004、ADR-0005

## 背景

原方案说"PoC 使用 JSON 文件，按学生分目录"，但回避了四个必须回答的问题：
谁有权写 `homework_id` / `session_id` / evidence？并发怎么保证？
Workflow 的 8 个状态游标存在哪里？失败后如何恢复？

更关键的约束：**OpenClaw 提供的是 Skill 加载与 Agent 调度，不是持久化 Workflow Engine。**
因此把 `workflows/*.md` 当成"会自动执行的状态机"是不成立的（R25 禁止假装）。

## 决策

### 1. 唯一写入者：`scripts/state_store.py`

Skill **不直接写文件**。所有持久化经由一个确定性脚本，OpenClaw 侧通过 `allowed-tools`
只授予该脚本写权限。

| 对象 | 生成者 | 写入者 | 读取者 |
|---|---|---|---|
| `homework_id` | `state_store.py`（`hw_<yyyymmdd>_<seq>`） | `state_store.py` | 所有 Skill |
| `session_id` | `state_store.py`（`ts_<yyyymmdd>_<seq>`） | `state_store.py` | math-tutor |
| `evidence_id` | `state_store.py`（`ev_<student_id>_<seq>`） | `state_store.py` | diagnosis / tutor / plan |
| Skill 输出 JSON | 模型 | `state_store.py`（先校验后落盘） | 下游 Skill |
| Workflow 游标 | `state_store.py` | `state_store.py` | 主 Agent |

理由：ID 由模型自行编造会导致重复与不可追溯（R22 的前提被破坏）；
校验前置于落盘，保证磁盘上的数据永远 Schema 合法（R7）。

### 2. 目录与命名

```
student-data/<student_id>/
├── profile.json                     # 可变，覆盖式（非证据）
├── events.jsonl                     # 唯一事实来源，append-only
├── homework/<homework_id>/
│   ├── analysis.json                # 校验通过的 Skill 输出（可由事件重建）
│   └── diagnosis.json
├── plans/<plan_id>.json
├── sessions/<session_id>.json
└── reports/<report_id>.md
```

区分两类数据的理由：

- **不可变证据** → `events.jsonl`，每行一个事件，永不修改、永不删除（R22）
- **可变形成品** → `analysis.json` / `diagnosis.json` 等，属于"当前视图"，
  由事件投影生成，可随时从 `events.jsonl` 重放重建

这样既满足 append-only，又避免"下游必须自己解析日志"的复杂度。

### 3. 事件结构

```json
{ "seq": 7,
  "event_id": "ev_stu_7a1f_0007",
  "at": "2026-11-01T19:42:07+08:00",
  "type": "verification_result",
  "student_id": "stu_7a1f",
  "knowledge_point_id": "g7.math.a04.02.04",
  "source": "math-tutor",
  "payload": { "correct": true, "independence": "assisted", "hint_level": 2 } }
```

`seq` 单调递增、由 `state_store.py` 分配、失败重试不复用已分配序号。

### 4. 并发与幂等

PoC 只有一个学生一个 Agent，但仍要防止同一事件重复写入：

- **锁**：`student-data/<id>/.lock`，`os.open(..., O_CREAT|O_EXCL)` + 超时 10s；
  Windows 下不使用 `fcntl`
- **幂等键**：`(source, client_event_id)` 去重；Skill 重试时携带同一个
  `client_event_id`，重复写入返回已有 `event_id` 而不新增
- **原子写**：`analysis.json` 等成品文件用"写临时文件 + `os.replace`"，避免半截文件

### 5. Workflow 游标

```
student-data/<student_id>/workflow.json
{ "homework_id": "hw_20261101_001",
  "state": "DIAGNOSED",
  "states_seen": ["RECEIVED","EXTRACTED","ANALYZED","DIAGNOSED"],
  "updated_at": "...",
  "failure": null }
```

状态集合：`RECEIVED → EXTRACTED → ANALYZED → DIAGNOSED → PLANNED → TUTORING → VERIFIED → REPORTED`，
外加 `BLOCKED`（异常待人工）与 `FAILED`（记录 `failure.stage`）。

**推进规则**：由主 Agent 在每次成功调用 Skill 后请求 `state_store.py advance`。
没有引擎，`workflows/homework-learning-workflow.md` 只是给主 Agent 的**指令文档**，
不是可执行编排 —— 这一点必须在文档里显式写出。

### 6. 恢复

`state_store.py replay --student <id>` 从 `events.jsonl` 重建全部成品文件与游标。
这是"证据不可变"设计带来的直接收益：成品损坏不丢历史。

## 备选方案

1. **让每个 Skill 自己写文件** —— 否决：ID 生成规则分散、并发无保护、
   append-only 无法由 4 个独立实现共同保证。
2. **引入 SQLite** —— 否决（当前阶段）：PoC 要能被家长/老师直接读懂与核查，
   JSONL 可 grep、可 diff、可直接进 Git 审阅；关系库带来的模式迁移成本在 4 个 Skill
   尚未稳定时属于提前优化。正式产品阶段再评估。
3. **引入 LangGraph / 状态机引擎做编排** —— 否决（当前阶段）：会掩盖"Skill 契约是否
   真能串联"这一核心待验证问题。先用脚本 + 主 Agent 顺序调用把契约跑通，
   再决定是否值得引入引擎。
4. **只存成品 JSON，不存事件日志** —— 否决：R22 要求不覆盖历史，
   仅靠"每次新建 diagnosis_v2.json"会在半年内退化成不可维护的文件堆。

## 后果

- 正面：ID 空间可控、历史可审计、可重放恢复、下游 Skill 读成品而非日志。
- 负面：多一个需要测试的脚本；"成品可由事件重建"意味着两套写路径必须保持一致
  （由 `replay` 的单测保证）。
- 债务：事件 schema 演进策略（版本字段）需要在有第二个 Schema 版本前补齐；
  锁实现在跨平台文件语义上需要实测；单学生假设需在多学生并发时重审。

## 验证

- Layer 1：`tests/test_state_store.py`（P4 前实现）—— 断言：
  ① seq 单调且重试不复用 ② 同 `client_event_id` 幂等 ③ 锁超时报错而非死等
  ④ `replay` 后的成品文件与原始写入逐字节一致
- Layer 2：`workflow.json` 的 `state` 必须属于枚举集合，由 `validate_*.py` 检查
- Layer 3：端到端演示（P8）必须展示"中途 kill 进程后 replay 恢复"

**当前状态**：`state_store.py` **尚未实现**（本 ADR 为 Proposed）。
它将在 P4 与 Skill 一起落地，届时本 ADR 转 Accepted。
