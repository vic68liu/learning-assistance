"""Schema 层自校验：Schema 自身合法 + 信封一致 + 枚举集中 + 内置示例可通过校验。

这是 Layer 2 的基础设施（ADR-0004）。它检查的是**契约本身**的质量，
不是模型输出。模型输出的校验复用同一份 registry。

检查项：
  1. 每个 Schema 通过 Draft 2020-12 元校验
  2. 四份 Skill 输出 Schema 都含 6 个信封字段且全部 required（AGENTS.md 第 4 节）
  3. 枚举集中：除 common.defs.json 外，任何 Schema 不得内联重复统一词表（R8）
  4. 每个 `examples[]` 中的实例都能通过所属 Schema 校验
     —— 示例不合法比没有示例更危险，因为它会被当成"合法形状"抄进 Prompt

退出码：0 全部通过 / 1 有失败 / 2 依赖缺失（**明确 SKIP，绝不跳过即视为通过**，R25）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_DIR = ROOT / "schemas"

ENVELOPE_FIELDS = [
    "schema_version",
    "skill_name",
    "prompt_version",
    "generated_at",
    "student_id",
    "confidence",
    "confidence_basis",
]

#: Skill 输出契约（knowledge-point.schema.json 描述的是人工维护的文件，不适用信封）
SKILL_OUTPUT_SCHEMAS = [
    "homework-analysis.schema.json",
    "student-profile.schema.json",
    "learning-plan.schema.json",
    "tutor-session.schema.json",
]

ALL_SCHEMAS = ["common.defs.json", *SKILL_OUTPUT_SCHEMAS, "knowledge-point.schema.json"]

#: 只提供共享定义的文档：没有根类型，不适用"示例必须自校验"，
#: 改为检查"每个 $defs 都至少被引用一次"（防止死定义漂移）
DEFS_ONLY_SCHEMAS = {"common.defs.json"}


class CheckFailure(Exception):
    def __init__(self, checks: list[str]) -> None:
        super().__init__("; ".join(checks[:12]))
        self.checks = checks


def load_raw(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _build_registry(paths: list[Path]):
    """把 schemas/ 下的文件全部注册，供跨文件 $ref 解析。"""
    from referencing import Registry, Resource
    from referencing.jsonschema import DRAFT202012

    resources = []
    for p in paths:
        contents = load_raw(p)
        res = Resource.from_contents(contents, default_specification=DRAFT202012)
        uri = contents.get("$id") or p.as_uri()
        resources.append((uri, res))
    return Registry().with_resources(resources)


def _iter_nodes(node: Any):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _iter_nodes(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_nodes(item)


def _shared_enums(registry_doc: dict[str, Any]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for name, definition in (registry_doc.get("$defs") or {}).items():
        if isinstance(definition, dict) and isinstance(definition.get("enum"), list):
            values = {v for v in definition["enum"] if isinstance(v, str)}
            if values:
                out[name] = values
    return out


def check_envelope(raw: dict[str, Any], name: str) -> list[str]:
    problems: list[str] = []
    props = raw.get("properties") or {}
    required = set(raw.get("required") or [])
    for field_name in ENVELOPE_FIELDS:
        if field_name not in props:
            problems.append(f"{name}: 缺信封字段 properties.{field_name}")
        elif field_name not in required:
            problems.append(f"{name}: 信封字段 {field_name} 未列入 required")
    if raw.get("additionalProperties") is not False:
        problems.append(f"{name}: 顶层 additionalProperties 必须为 false")
    return problems


def check_enum_centralization(raw: dict[str, Any], name: str, shared: dict[str, set[str]]) -> list[str]:
    """禁止在 Skill Schema 内联重复统一词表 —— 否则改一处漏四处（R8）。"""
    problems: list[str] = []
    for node in _iter_nodes(raw):
        enum = node.get("enum")
        if not isinstance(enum, list):
            continue
        values = {v for v in enum if isinstance(v, str)}
        if len(values) < 2:
            continue
        for shared_name, shared_values in shared.items():
            if values == shared_values or (values and values < shared_values):
                # 允许"收窄子集"型约束（如 next_recommendation 只取部分动作），
                # 但完全等于或真子集于统一词表的，必须改用 $ref
                if values == shared_values:
                    problems.append(
                        f"{name}: 内联了与 $defs.{shared_name} 完全相同的枚举，应改用 $ref"
                    )
    return problems


def check_examples(raw: dict[str, Any], name: str, registry, validator_cls) -> list[str]:
    problems: list[str] = []
    examples = raw.get("examples")
    if examples is None:
        problems.append(f"{name}: 缺 examples，无法证明 Schema 可满足")
        return problems
    if not isinstance(examples, list) or not examples:
        problems.append(f"{name}: examples 必须是非空数组")
        return problems

    validator = validator_cls(raw, registry=registry)
    for index, example in enumerate(examples):
        errors = sorted(validator.iter_errors(example), key=lambda e: list(e.absolute_path))
        if errors:
            detail = "; ".join(
                f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}" for e in errors[:4]
            )
            problems.append(f"{name}: examples[{index}] 未通过自身校验 → {detail}")
    return problems


def run(schema_dir: Path = SCHEMA_DIR) -> list[str]:
    try:
        from jsonschema import Draft202012Validator  # noqa: F401
    except ImportError:  # pragma: no cover
        raise ImportError("缺少 jsonschema，请按 ADR-0007 安装后重试")

    from jsonschema import Draft202012Validator, SchemaError

    paths: list[Path] = []
    for filename in ALL_SCHEMAS:
        path = schema_dir / filename
        if not path.exists():
            raise CheckFailure([f"缺少 Schema 文件: {path}"])
        paths.append(path)

    registry = _build_registry(paths)
    problems: list[str] = []
    docs: dict[str, dict[str, Any]] = {p.name: load_raw(p) for p in paths}

    common = docs["common.defs.json"]
    shared = _shared_enums(common)
    if not shared:
        problems.append("common.defs.json 未定义任何枚举")

    for path in paths:
        raw = docs[path.name]
        try:
            Draft202012Validator.check_schema(raw)
        except SchemaError as exc:
            problems.append(f"{path.name}: 元校验失败 → {exc.message}")
            continue

        if path.name in SKILL_OUTPUT_SCHEMAS:
            problems.extend(check_envelope(raw, path.name))
            problems.extend(check_enum_centralization(raw, path.name, shared))

        if path.name in DEFS_ONLY_SCHEMAS:
            continue
        problems.extend(check_examples(raw, path.name, registry, Draft202012Validator))

    problems.extend(check_defs_usage(docs))

    if problems:
        raise CheckFailure(problems)
    return []


def check_defs_usage(docs: dict[str, dict[str, Any]]) -> list[str]:
    """统一词表若出现"定义了但没人用"，说明有 Schema 绕过 $ref 自行约束（R8 的前兆）。

    两种合法消费方式：
      1. 其它 Schema 里的 `#/$defs/<name>`（跨文件 $ref）
      2. scripts/ 下的确定性脚本按名字读取该 def（例如关系类型枚举由
         validate_knowledge_base.py 从 common.defs.json 取，而不是自己硬编码一份）
    """
    problems: list[str] = []
    common = docs["common.defs.json"]
    others = json.dumps({k: v for k, v in docs.items() if k != "common.defs.json"}, ensure_ascii=False)

    scripts_text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace") for path in sorted((ROOT / "scripts").glob("*.py"))
    )
    for def_name in (common.get("$defs") or {}):
        referenced = f"#/$defs/{def_name}" in others
        consumed_by_script = def_name in scripts_text
        if not (referenced or consumed_by_script):
            problems.append(f"common.defs.json 的 $defs.{def_name} 未被任何 Schema 或脚本消费（死定义或绕 ref 风险）")
    return problems


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        run()
    except ImportError as exc:
        print(f"SKIP: {exc}", file=sys.stderr)
        print("依赖缺失时不得视为通过（R25 / ADR-0007 规则 5）", file=sys.stderr)
        return 2
    except CheckFailure as exc:
        print(f"FAIL: {len(exc.checks)} 项检查未通过", file=sys.stderr)
        for item in exc.checks:
            print(f"  - {item}", file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover
        print(f"FAIL: 未预期异常 {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print(f"OK: {len(ALL_SCHEMAS)} 份 Schema 元校验通过，信封字段与枚举集中性一致，示例全部满足自身契约")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
