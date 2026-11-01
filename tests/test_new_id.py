"""ID 生成与校验规则（R23 / ADR-0006）。"""

from __future__ import annotations

import re
from datetime import date

import pytest

import new_id


def test_student_id_shape_and_entropy_source():
    ids = {new_id.new_student_id() for _ in range(300)}
    assert all(re.match(r"^stu_[0-9a-f]{4}$", s) for s in ids)
    assert len(ids) > 250, "300 次生成出现大量重复说明熵不足"
    assert new_id.is_student_id("stu_7a1f")
    assert not new_id.is_student_id("stu_7A1F")  # 大写不合法，避免同一 ID 两种写法
    assert not new_id.is_student_id("student_7a1f")
    assert not new_id.is_student_id("stu_李明")


def test_evidence_id_requires_valid_student_and_seq():
    assert new_id.new_evidence_id("stu_7a1f", 7) == "ev_stu_7a1f_0007"
    assert new_id.new_evidence_id("stu_7a1f", 12345) == "ev_stu_7a1f_12345"
    assert new_id.is_evidence_id("ev_stu_7a1f_0007")
    with pytest.raises(ValueError):
        new_id.new_evidence_id("stu_ZZZZ", 1)
    with pytest.raises(ValueError):
        new_id.new_evidence_id("stu_7a1f", 0)


def test_knowledge_point_id_grammar_and_roundtrip():
    value = new_id.new_knowledge_point_id("七上", 4, 2, 4)
    assert value == "g7.math.a04.02.04"
    parts = new_id.knowledge_point_parts(value)
    assert parts == {
        "volume": "七上",
        "chapter_code": "a04",
        "chapter": 4,
        "section": 2,
        "point": 4,
    }
    assert new_id.new_knowledge_point_id("七下", 1, 1, 1).startswith("g7.math.b01")


@pytest.mark.parametrize("bad", ["g7.math.04.02.04", "g7.math.a4.02.04", "g7.math.a04.2.04", "g7.math.a04.02", "math.a04.02.04"])
def test_knowledge_point_id_rejects_malformed(bad):
    assert not new_id.is_knowledge_point_id(bad)
    with pytest.raises(ValueError):
        new_id.knowledge_point_parts(bad)


def test_knowledge_point_id_range_guards():
    with pytest.raises(ValueError):
        new_id.new_knowledge_point_id("七上", 0, 1, 1)
    with pytest.raises(ValueError):
        new_id.new_knowledge_point_id("七上", 13, 1, 1)
    with pytest.raises(ValueError):
        new_id.new_knowledge_point_id("八上", 1, 1, 1)
    with pytest.raises(ValueError):
        new_id.new_knowledge_point_id("七上", 1, 1, 100)


def test_dated_ids_use_explicit_day_and_seq():
    day = date(2026, 11, 1)
    assert new_id.new_homework_id(day, 1) == "hw_20261101_001"
    assert new_id.new_plan_id(day, 12) == "plan_20261101_012"
    assert new_id.new_session_id(day, 999) == "ts_20261101_999"
    with pytest.raises(ValueError):
        new_id.new_homework_id(day, 1000)
    with pytest.raises(ValueError):
        new_id.dated_id("bogus", day)


def test_check_cli_reports_types(capsys):
    assert new_id._main(["check", "g7.math.a04.02.04"]) == 0
    assert new_id._main(["check", "hw_20261101_001"]) == 0
    assert new_id._main(["check", "不是ID"]) == 1
