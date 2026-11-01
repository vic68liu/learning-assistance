"""Schema 自检脚本的测试，含 ADR-0004 要求的"故意破坏必须失败"分支。

一个只会在好数据上通过的校验脚本没有价值：它必须能抓到坏数据。
"""

from __future__ import annotations

import copy
import json
import shutil
import sys
from pathlib import Path

import pytest

import validate_schemas

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_DIR = ROOT / "schemas"


@pytest.fixture()
def schema_copy(tmp_path: Path) -> Path:
    target = tmp_path / "schemas"
    shutil.copytree(SCHEMA_DIR, target)
    return target


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_real_schemas_pass():
    """当前仓库的 Schema 必须自检通过 —— 这条失败就意味着契约本身坏了。"""
    validate_schemas.run(SCHEMA_DIR)


def test_meta_invalid_schema_is_caught(schema_copy: Path):
    path = schema_copy / "learning-plan.schema.json"
    raw = _read(path)
    raw["properties"]["grade"]["type"] = "not-a-type"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(validate_schemas.CheckFailure) as excinfo:
        validate_schemas.run(schema_copy)
    assert any("元校验失败" in p for p in excinfo.value.checks)


def test_missing_envelope_field_is_caught(schema_copy: Path):
    path = schema_copy / "student-profile.schema.json"
    raw = _read(path)
    del raw["properties"]["prompt_version"]
    raw["required"] = [r for r in raw["required"] if r != "prompt_version"]
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(validate_schemas.CheckFailure) as excinfo:
        validate_schemas.run(schema_copy)
    assert any("prompt_version" in p for p in excinfo.value.checks)


def test_open_additional_properties_is_caught():
    raw = _read(SCHEMA_DIR / "homework-analysis.schema.json")
    raw["additionalProperties"] = True
    problems = validate_schemas.check_envelope(raw, "t")
    assert any("additionalProperties" in p for p in problems)


def test_inlined_duplicate_enum_is_caught():
    raw = _read(SCHEMA_DIR / "common.defs.json")
    shared = validate_schemas._shared_enums(raw)
    host = {
        "type": "object",
        "properties": {"status": {"enum": sorted(shared["mastery_status"])}},
    }
    problems = validate_schemas.check_enum_centralization(host, "host.json", shared)
    assert any("应改用 $ref" in p for p in problems)
    # 反向确认：走 $ref 的写法不会被误报
    ok = {"type": "object", "properties": {"status": {"$ref": "common.defs.json#/$defs/mastery_status"}}}
    assert validate_schemas.check_enum_centralization(ok, "ok.json", shared) == []


def test_broken_example_is_caught(schema_copy: Path):
    """示例违反自身契约必须被抓到：错误示例会被当成合法形状抄进 Prompt。"""
    path = schema_copy / "tutor-session.schema.json"
    raw = _read(path)
    raw["examples"][0]["outcome"]["independence"] = "guessed"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(validate_schemas.CheckFailure) as excinfo:
        validate_schemas.run(schema_copy)
    assert any("examples[0]" in p for p in excinfo.value.checks)


def test_hint_level_2_forces_assisted_outcome():
    """R18 的可执行形式：提示 2 级及以上却标 independent 的输出必须不合法。"""
    raw = _read(SCHEMA_DIR / "tutor-session.schema.json")
    example = copy.deepcopy(raw["examples"][0])
    example["outcome"]["hint_level_max"] = 2
    example["outcome"]["independence"] = "independent"
    registry = validate_schemas._build_registry(sorted(SCHEMA_DIR.glob("*.json")))
    from jsonschema import Draft202012Validator

    validator = Draft202012Validator(raw, registry=registry)
    errors = list(validator.iter_errors(example))
    assert errors, "hint_level_max=2 + independent 应被 Schema 规则拒绝"


def test_answer_revealed_true_is_impossible():
    raw = _read(SCHEMA_DIR / "tutor-session.schema.json")
    example = copy.deepcopy(raw["examples"][0])
    example["outcome"]["answer_revealed"] = True
    registry = validate_schemas._build_registry(sorted(SCHEMA_DIR.glob("*.json")))
    from jsonschema import Draft202012Validator

    validator = Draft202012Validator(raw, registry=registry)
    assert list(validator.iter_errors(example)), "泄露答案必须无法被 Schema 表达"


def test_unknown_status_with_evidence_is_rejected():
    """R16 的可执行形式：unknown 却带 evidence 必须不合法。"""
    raw = _read(SCHEMA_DIR / "student-profile.schema.json")
    example = copy.deepcopy(raw["examples"][1])
    example["knowledge_points"][0]["evidence_ids"] = ["ev_stu_7a1f_0001"]
    registry = validate_schemas._build_registry(sorted(SCHEMA_DIR.glob("*.json")))
    from jsonschema import Draft202012Validator

    validator = Draft202012Validator(raw, registry=registry)
    assert list(validator.iter_errors(example))


def test_zero_evidence_metric_must_have_null_value():
    raw = _read(SCHEMA_DIR / "common.defs.json")
    definition = raw["$defs"]["metric"]
    registry = validate_schemas._build_registry(sorted(SCHEMA_DIR.glob("*.json")))
    from jsonschema import Draft202012Validator

    validator = Draft202012Validator(definition, registry=registry)
    assert validator.is_valid({"value": None, "evidence_count": 0, "basis": "no evidence"})
    assert list(validator.iter_errors({"value": 0.8, "evidence_count": 0, "basis": "x"})), "不得编造无证据的数值"


def test_dead_definition_is_caught():
    raw = dict(_read(SCHEMA_DIR / "common.defs.json"))
    raw["$defs"] = dict(raw["$defs"])
    raw["$defs"]["totally_unused_enum"] = {"enum": ["aaa", "bbb"]}
    docs = {"common.defs.json": raw}
    for name in validate_schemas.SKILL_OUTPUT_SCHEMAS + ["knowledge-point.schema.json"]:
        docs[name] = _read(SCHEMA_DIR / name)
    problems = validate_schemas.check_defs_usage(docs)
    assert any("totally_unused_enum" in p for p in problems)


def test_missing_jsonschema_returns_skip_code_2(monkeypatch, capsys):
    """依赖缺失绝不能被当成通过（R25 / ADR-0007 规则 5）。"""
    for name in list(sys.modules):
        if name.startswith("jsonschema"):
            monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.setitem(sys.modules, "jsonschema", None)
    assert validate_schemas.main([]) == 2
    err = capsys.readouterr().err
    assert "SKIP" in err


def test_every_expected_schema_file_exists():
    for name in validate_schemas.ALL_SCHEMAS:
        assert (SCHEMA_DIR / name).exists(), f"缺 {name}"
