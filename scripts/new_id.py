"""ID 生成规则的唯一实现处。

依据 AGENTS.md 第 6 节与 R23：ID 一律由脚本生成，**禁止模型自行编造**。
本模块只负责"形状正确"，序列号分配（evidence seq）由后续的 state_store.py 负责，
以保证单调不复用的语义有唯一归属（ADR-0003）。

格式：
    student     stu_<4 位十六进制>            例 stu_7a1f
    homework    hw_<yyyymmdd>_<3 位序号>       例 hw_20261101_001
    plan        plan_<yyyymmdd>_<3 位序号>
    session     ts_<yyyymmdd>_<3 位序号>
    evidence    ev_<student_id>_<4 位以上序号>  例 ev_stu_7a1f_0007
    knowledge   g7.math.<册码><章序>.<节序>.<点序>  例 g7.math.a04.02.04
"""

from __future__ import annotations

import argparse
import re
import secrets
import sys
from datetime import date

STUDENT_RE = re.compile(r"^stu_[0-9a-f]{4}$")
KNOWLEDGE_POINT_RE = re.compile(r"^g7\.math\.[ab][0-9]{2}\.[0-9]{2}\.[0-9]{2}$")
EVIDENCE_RE = re.compile(r"^ev_stu_[0-9a-f]{4}_[0-9]{4,}$")
_HOMEWORK_RE = re.compile(r"^hw_[0-9]{8}_[0-9]{3}$")
_PLAN_RE = re.compile(r"^plan_[0-9]{8}_[0-9]{3}$")
_SESSION_RE = re.compile(r"^ts_[0-9]{8}_[0-9]{3}$")

VOLUME_CODES = {"七上": "a", "七下": "b"}


def new_student_id(rng: secrets | None = None) -> str:
    """生成 pseudonymous 学生 ID。

    熵来源为 os.urandom（secrets），与姓名/校号/时间无关，因此不可反推身份。
    4 位十六进制 = 65536 空间，PoC 家庭数量级下碰撞概率可忽略；
    正式产品需换更长的 ID 并在建库时做唯一性约束（已记为债务）。
    """
    return "stu_" + secrets.token_hex(2)


def is_student_id(value: str) -> bool:
    return bool(STUDENT_RE.match(value))


def new_evidence_id(student_id: str, seq: int) -> str:
    """evidence ID = 学生 ID + 单调序号。

    序号必须来自 state_store 的分配结果。本函数**不做**幂等检查，
    也不接受已废弃的序号复用（R22）。
    """
    if not is_student_id(student_id):
        raise ValueError(f"非法 student_id: {student_id!r}")
    if not isinstance(seq, int) or seq < 1:
        raise ValueError(f"seq 必须是 >=1 的整数，收到 {seq!r}")
    return f"ev_{student_id}_{seq:04d}"


def is_evidence_id(value: str) -> bool:
    return bool(EVIDENCE_RE.match(value))


def new_knowledge_point_id(volume: str, chapter: int, section: int, point: int) -> str:
    """按 ADR-0006 文法生成知识点 ID。

    注意：本函数只用于**人工维护知识库时**生成候选 ID。
    Skill 侧禁止调用它来"创造"知识点（R14）——那属于虚构（R13）。
    """
    if volume not in VOLUME_CODES:
        raise ValueError(f"volume 必须是 {list(VOLUME_CODES)}，收到 {volume!r}")
    for name, val, lo, hi in (("chapter", chapter, 1, 12), ("section", section, 1, 12), ("point", point, 1, 99)):
        if not isinstance(val, int) or not (lo <= val <= hi):
            raise ValueError(f"{name} 需在 [{lo},{hi}]，收到 {val!r}")
    return f"g7.math.{VOLUME_CODES[volume]}{chapter:02d}.{section:02d}.{point:02d}"


def is_knowledge_point_id(value: str) -> bool:
    return bool(KNOWLEDGE_POINT_RE.match(value))


def knowledge_point_parts(kp_id: str) -> dict[str, object]:
    """反解 ID：用于报告里按章聚合。非法 ID 抛 ValueError。"""
    if not is_knowledge_point_id(kp_id):
        raise ValueError(f"非法知识点 ID: {kp_id!r}")
    _, tail = kp_id.split("g7.math.", 1)
    chapter_part, section, point = tail.split(".")
    volume = "七上" if chapter_part[0] == "a" else "七下"
    return {
        "volume": volume,
        "chapter_code": chapter_part,
        "chapter": int(chapter_part[1:]),
        "section": int(section),
        "point": int(point),
    }


def dated_id(prefix: str, day: date | None = None, seq: int = 1) -> str:
    """hw / plan / ts 三类按日序号 ID 的公共生成器。"""
    if prefix not in ("hw", "plan", "ts"):
        raise ValueError(f"prefix 必须是 hw/plan/ts，收到 {prefix!r}")
    if not isinstance(seq, int) or not (1 <= seq <= 999):
        raise ValueError(f"seq 需在 [1,999]，收到 {seq!r}")
    d = day or date.today()
    return f"{prefix}_{d.strftime('%Y%m%d')}_{seq:03d}"


def new_homework_id(day: date | None = None, seq: int = 1) -> str:
    return dated_id("hw", day, seq)


def new_plan_id(day: date | None = None, seq: int = 1) -> str:
    return dated_id("plan", day, seq)


def new_session_id(day: date | None = None, seq: int = 1) -> str:
    return dated_id("ts", day, seq)


def _main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="生成或校验本项目各类 ID（R23 / ADR-0006）")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("student", help="生成一个新的 pseudonymous 学生 ID")
    sp.add_argument("--count", type=int, default=1)

    ep = sub.add_parser("evidence", help="生成 evidence ID")
    ep.add_argument("student_id")
    ep.add_argument("seq", type=int)

    kp = sub.add_parser("knowledge-point", help="生成知识点 ID（仅人工维护知识库时使用）")
    kp.add_argument("volume", choices=sorted(VOLUME_CODES))
    kp.add_argument("chapter", type=int)
    kp.add_argument("section", type=int)
    kp.add_argument("point", type=int)

    hw = sub.add_parser("homework", help="生成 homework ID")
    hw.add_argument("--seq", type=int, default=1)

    ck = sub.add_parser("check", help="校验一个 ID 是否合法，输出类型")
    ck.add_argument("value")

    args = p.parse_args(argv)

    if args.cmd == "student":
        for _ in range(args.count):
            print(new_student_id())
    elif args.cmd == "evidence":
        print(new_evidence_id(args.student_id, args.seq))
    elif args.cmd == "knowledge-point":
        print(new_knowledge_point_id(args.volume, args.chapter, args.section, args.point))
    elif args.cmd == "homework":
        print(new_homework_id(seq=args.seq))
    elif args.cmd == "check":
        v = args.value
        kinds = []
        if is_student_id(v):
            kinds.append("student")
        if is_evidence_id(v):
            kinds.append("evidence")
        if is_knowledge_point_id(v):
            kinds.append("knowledge-point")
            kinds.append(f"parts={knowledge_point_parts(v)}")
        if _HOMEWORK_RE.match(v):
            kinds.append("homework")
        if _PLAN_RE.match(v):
            kinds.append("plan")
        if _SESSION_RE.match(v):
            kinds.append("session")
        if kinds:
            print(", ".join(kinds))
            return 0
        print(f"INVALID: {v}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
