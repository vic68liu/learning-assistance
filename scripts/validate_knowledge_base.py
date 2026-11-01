"""知识库结构校验：ID 文法/唯一性、章节一致性、PREREQUISITE 无环、关系引用完整性、审核状态。

依据 AGENTS.md R13/R14 与 ADR-0006。关系文件 `knowledge-relations.json` 的结构
没有独立 Schema（避免为两个文件维护六份 Schema），由本脚本承担校验——这是有意取舍，
记录在 docs/development-roadmap.md 的 P5 待办里。

退出码：0 通过 / 1 有失败 / 2 依赖缺失（不视为通过，R25）
知识库文件不存在时：默认打印 SKIP 返回 0（P3 阶段尚未建立），
`--strict` 时返回 1（供 P3.5 之后的 CI 使用）。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from graphlib import CycleError, TopologicalSorter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
KB_DIR = ROOT / "knowledge-base"
POINTS_FILE = KB_DIR / "grade-7-math.json"
RELATIONS_FILE = KB_DIR / "knowledge-relations.json"

ID_RE = re.compile(r"^g7\.math\.[ab][0-9]{2}\.[0-9]{2}\.[0-9]{2}$")

#: 枚举一律从 schemas/common.defs.json 读取，脚本内不保留第二份字面量。
#: 这样"关系类型"只可能有一个真相来源，加枚举时脚本自动跟随（R8）。
_COMMON_DEFS_PATH = ROOT / "schemas" / "common.defs.json"


def shared_enum(name: str) -> set[str]:
    """读取统一词表。缺失即抛错，不回退到硬编码默认值。"""
    try:
        with _COMMON_DEFS_PATH.open(encoding="utf-8") as fh:
            defs = json.load(fh).get("$defs", {})
    except FileNotFoundError as exc:
        raise RuntimeError(f"缺少 {_COMMON_DEFS_PATH}，无法确定 {name} 词表") from exc
    definition = defs.get(name)
    if not isinstance(definition, dict) or not isinstance(definition.get("enum"), list):
        raise RuntimeError(f"common.defs.json 的 $defs.{name} 不是枚举定义")
    return {v for v in definition["enum"] if isinstance(v, str)}


class KBProblem(Exception):
    def __init__(self, problems: list[str], stats: dict[str, Any] | None = None) -> None:
        super().__init__("; ".join(problems[:10]))
        self.problems = problems
        self.stats = stats or {}


def _load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _schema_problems(points: dict[str, Any]) -> list[str]:
    """用 knowledge-point.schema.json 校验整份文件。缺依赖时抛 ImportError。"""
    from jsonschema import Draft202012Validator, SchemaError
    from referencing import Registry, Resource
    from referencing.jsonschema import DRAFT202012

    schema_dir = ROOT / "schemas"
    resources = []
    for path in sorted(schema_dir.glob("*.json")):
        contents = _load(path)
        resources.append((contents["$id"], Resource.from_contents(contents, default_specification=DRAFT202012)))
    registry = Registry().with_resources(resources)

    schema = _load(schema_dir / "knowledge-point.schema.json")
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        return [f"knowledge-point.schema.json 元校验失败: {exc.message}"]

    validator = Draft202012Validator(schema, registry=registry)
    problems = []
    for error in sorted(validator.iter_errors(points), key=lambda e: list(e.absolute_path))[:25]:
        location = "/".join(str(p) for p in error.absolute_path) or "<root>"
        problems.append(f"Schema: {location}: {error.message}")
    return problems


def check_points(points: dict[str, Any]) -> tuple[list[str], dict[str, Any], set[str]]:
    problems: list[str] = []
    entries = points.get("knowledge_points")
    if not isinstance(entries, list):
        return [f"knowledge_points 必须是数组，收到 {type(entries).__name__}"], {}, set()

    ids = [e.get("id") for e in entries if isinstance(e, dict)]
    bad_format = [i for i in ids if not (isinstance(i, str) and ID_RE.match(i))]
    if bad_format:
        problems.append(f"ID 文法非法: {bad_format[:5]}")

    duplicates = [i for i, c in Counter(ids).items() if c > 1]
    if duplicates:
        problems.append(f"ID 重复: {duplicates[:5]}（点序永不复用，ADR-0006）")

    chapter_codes = {c["code"] for c in (points.get("scope", {}).get("chapters") or [])}

    # 逐条一致性
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            continue
        kp_id = entry["id"]
        if not ID_RE.match(kp_id):
            continue
        _, tail = kp_id.split("g7.math.", 1)
        id_chapter, id_section, id_point = tail.split(".")
        if entry.get("chapter_code") != id_chapter:
            problems.append(f"{kp_id}: chapter_code({entry.get('chapter_code')}) 与 ID 中的 {id_chapter} 不一致")
        if entry.get("section_code") != id_section:
            problems.append(f"{kp_id}: section_code({entry.get('section_code')}) 与 ID 中的 {id_section} 不一致")
        if id_chapter not in chapter_codes:
            problems.append(f"{kp_id}: 所属章 {id_chapter} 未在 scope.chapters 中声明")
        # origin / review_status 的取值合法性由 knowledge-point.schema.json 负责，
        # 脚本不重复维护第二份枚举字面量（R8）；此处只做 Schema 无法表达的语义检查。
        if entry.get("deprecated") is True and not entry.get("replacement_ids"):
            # 废弃而不给替代：允许，但必须能解释（Schema 已要求 reason），此处只提示
            pass

    active_ids = {e["id"] for e in entries if isinstance(e, dict) and isinstance(e.get("id"), str) and not e.get("deprecated")}
    stats = {
        "total": len(entries),
        "active": len(active_ids),
        "deprecated": len(entries) - len(active_ids),
        "pending_review": sum(1 for e in entries if isinstance(e, dict) and e.get("review_status") == "pending_review"),
        "inferred": sum(1 for e in entries if isinstance(e, dict) and e.get("origin") == "inferred"),
        "by_chapter": dict(Counter(i.split("g7.math.")[1][:3] for i in ids if isinstance(i, str) and "g7.math." in i)),
    }
    return problems, stats, active_ids


def check_relations(relations: dict[str, Any], known_ids: set[str]) -> tuple[list[str], list[str]]:
    """关系文件没有独立 Schema，其结构与取值校验全部在此（ADR-0004 的 Layer 2 补充）。"""
    problems: list[str] = []
    edges = relations.get("relations")
    if not isinstance(edges, list):
        return [f"relations 必须是数组，收到 {type(edges).__name__}"], []

    relation_types = shared_enum("relation_type")
    relation_origins = shared_enum("relation_origin")
    review_statuses = shared_enum("review_status")

    prereq_edges: list[tuple[str, str]] = []
    for index, edge in enumerate(edges):
        if not isinstance(edge, dict):
            problems.append(f"relations[{index}]: 必须是对象")
            continue
        missing = [key for key in ("from", "to", "type", "origin", "review_status") if key not in edge]
        if missing:
            problems.append(f"relations[{index}]: 缺必填字段 {missing}")
            continue
        src, dst, rtype = edge.get("from"), edge.get("to"), edge.get("type")
        tag = f"relations[{index}]({src}->{dst}/{rtype})"
        if rtype not in relation_types:
            problems.append(f"{tag}: type 不在统一词表内（R8）")
        if edge.get("origin") not in relation_origins:
            problems.append(f"{tag}: origin 取值非法 {edge.get('origin')!r}")
        if edge.get("review_status") not in review_statuses:
            problems.append(f"{tag}: review_status 取值非法 {edge.get('review_status')!r}")
        if src not in known_ids:
            problems.append(f"{tag}: from 不存在或已废弃（R14）")
        if dst not in known_ids:
            problems.append(f"{tag}: to 不存在或已废弃（R14）")
        if src == dst:
            problems.append(f"{tag}: 自环")
        if rtype == "PREREQUISITE" and src in known_ids and dst in known_ids:
            prereq_edges.append((dst, src))  # dst 需要 src 先掌握：图边 = 依赖方向

    return problems, prereq_edges


def check_prerequisite_dag(edges: list[tuple[str, str]]) -> list[str]:
    """PREREQUISITE 必须是有向无环图，否则"前置优先"排序无法收敛。"""
    if not edges:
        return []
    graph: dict[str, set[str]] = {}
    for src, dst in edges:
        graph.setdefault(src, set()).add(dst)
        graph.setdefault(dst, set())
    try:
        list(TopologicalSorter(graph).static_order())
    except CycleError as exc:
        cycle = [str(v) for v in getattr(exc, "args", [])[1:2]]
        detail = cycle[0] if cycle else "见 knowledge-relations.json"
        return [f"PREREQUISITE 存在环，无法做前置优先排序: {detail}"]
    return []


def check_review_gate(points: dict[str, Any], relations: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    top_status = points.get("review_status")
    if top_status == "reviewed":
        unreviewed = [e.get("id") for e in points.get("knowledge_points", []) if e.get("review_status") != "reviewed"]
        if unreviewed:
            problems.append(f"顶层 review_status=reviewed，但 {len(unreviewed)} 个知识点仍未审: {unreviewed[:5]}")
        if not points.get("reviewed_by") or not points.get("reviewed_at"):
            problems.append("顶层 review_status=reviewed 缺 reviewed_by / reviewed_at（状态无凭据，R25）")
    inferred_unreviewed = [
        f"{e.get('from')}->{e.get('to')}"
        for e in relations.get("relations", [])
        if isinstance(e, dict) and e.get("origin") == "inferred" and e.get("review_status") != "reviewed"
    ]
    if inferred_unreviewed:
        problems.append(
            f"[REVIEW-REQUIRED] {len(inferred_unreviewed)} 条推断关系未经人工确认，禁止用于掌握度结论"
            f"（可在 REVIEW-QUEUE.md 处理）: {inferred_unreviewed[:3]}"
        )
    return problems


def run(
    strict: bool = False,
    points_file: Path = POINTS_FILE,
    relations_file: Path = RELATIONS_FILE,
) -> tuple[bool, list[str], dict[str, Any]]:
    """返回 (是否有待人工确认项, 问题列表, 统计)。路径可注入以便单测覆盖失败分支。"""
    if not points_file.exists():
        message = f"知识库尚未建立: {points_file}（P3.5 交付）"
        return (strict, [message], {"missing": True}) if strict else (False, [], {"missing": True})

    try:
        from jsonschema import Draft202012Validator  # noqa: F401
    except ImportError as exc:
        raise ImportError(str(exc))

    points = _load(points_file)
    relations = _load(relations_file) if relations_file.exists() else {"relations": []}

    problems = _schema_problems(points)
    point_problems, stats, active_ids = check_points(points)
    problems.extend(point_problems)

    if not relations_file.exists():
        problems.append(f"缺少关系文件: {relations_file}")

    rel_problems, prereq_edges = check_relations(relations, active_ids)
    problems.extend(rel_problems)
    problems.extend(check_prerequisite_dag(prereq_edges))
    review_problems = check_review_gate(points, relations)
    # 推断关系未审不是结构错误，单独作为"待办"返回，便于 REVIEW-QUEUE 对齐
    problems.extend(p for p in review_problems if not p.startswith("[REVIEW-REQUIRED]"))
    pending = [p for p in review_problems if p.startswith("[REVIEW-REQUIRED]")]

    stats["relation_edges"] = len(relations.get("relations", []))
    stats["prerequisite_edges"] = len(prereq_edges)
    stats["review_required"] = pending
    return bool(pending), problems, stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="校验 knowledge-base/（R13/R14、ADR-0006）")
    parser.add_argument("--strict", action="store_true", help="知识库文件缺失时也判失败（CI 用）")
    parser.add_argument("--json", action="store_true", help="输出机器可读结果")
    args = parser.parse_args(argv)

    try:
        pending, problems, stats = run(strict=args.strict)
    except ImportError as exc:
        print(f"SKIP: 缺少 jsonschema 依赖 → {exc}", file=sys.stderr)
        print("依赖缺失不得视为通过（R25 / ADR-0007 规则 5）", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    if stats.get("missing"):
        print("SKIP: knowledge-base/grade-7-math.json 尚不存在（P3.5 交付，当前为 P3）")
        return 1 if args.strict else 0

    if args.json:
        print(json.dumps({"problems": problems, "pending": pending, "stats": stats}, ensure_ascii=False, indent=2))
    if problems:
        print(f"FAIL: 知识库 {len(problems)} 项不合规", file=sys.stderr)
        for item in problems:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print(
        "OK: 知识库结构合规 —— "
        f"{stats.get('active', 0)} 个有效知识点 / {stats.get('total', 0)} 总数 / "
        f"{stats.get('relation_edges', 0)} 条关系边（其中 PREREQUISITE {stats.get('prerequisite_edges', 0)} 条，DAG 通过）"
    )
    print(f"  按章分布: {stats.get('by_chapter')}")
    if stats.get("pending_review", 0) or stats.get("review_required"):
        print(f"  ⚠ 仍有 {stats.get('pending_review', 0)} 个知识点未人工审核；"
              f"{len(stats.get('review_required', []))} 组待确认推断关系见 knowledge-base/REVIEW-QUEUE.md")
        print("  ⚠ 顶层 review_status 非 reviewed 时，Skill 不得输出面向用户的掌握度结论（AGENTS.md 第 2 节）")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
