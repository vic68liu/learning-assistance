"""知识库校验脚本的测试：重点验证**失败分支**真的会被抓到。

覆盖 ADR-0006 要求的四项：ID 唯一/文法、章节一致性、PREREQUISITE 无环、关系引用完整性，
以及 ADR-0004 的"推断关系未审不得当作结论依据"。
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

import validate_knowledge_base as vkb

BASE_DOC: dict[str, Any] = {
    "schema_version": "1.0.0",
    "subject": "math",
    "grade": "g07",
    "textbook_version": "人教版 2024 秋版 七年级上册（待实体书核对）",
    "curriculum_standard_version": "2022",
    "review_status": "pending_review",
    "reviewed_by": None,
    "reviewed_at": None,
    "scope": {
        "volumes": ["七上"],
        "chapters": [
            {"code": "a02", "title": "第二章 有理数的运算", "volume": "七上", "source_pages": None},
            {"code": "a04", "title": "第四章 整式的加减", "volume": "七上", "source_pages": None},
        ],
        "excluded": [
            {
                "code": "a06",
                "title": "第六章 几何图形初步",
                "reason": "符号验算不适用且图像输入未验证",
                "revisit_condition": "OCR spike 通过后再建模",
            }
        ],
    },
    "knowledge_points": [
        {
            "id": "g7.math.a04.02.01",
            "chapter_code": "a04",
            "section_code": "02",
            "section_title": "4.2 整式的加法与减法",
            "subsection_title": None,
            "title": "同类项的判定",
            "origin": "human_outline",
            "review_status": "pending_review",
            "reviewed_by": None,
            "reviewed_at": None,
            "deprecated": False,
            "deprecated_at": None,
            "deprecated_reason": None,
            "replacement_ids": [],
            "source_pages": None,
            "expected_error_patterns": ["只看字母不看相同指数"],
        },
        {
            "id": "g7.math.a04.02.02",
            "chapter_code": "a04",
            "section_code": "02",
            "section_title": "4.2 整式的加法与减法",
            "subsection_title": None,
            "title": "合并同类项法则",
            "origin": "human_outline",
            "review_status": "pending_review",
            "reviewed_by": None,
            "reviewed_at": None,
            "deprecated": False,
            "deprecated_at": None,
            "deprecated_reason": None,
            "replacement_ids": [],
            "source_pages": None,
            "expected_error_patterns": ["指数也被相加"],
        },
        {
            "id": "g7.math.a02.01.01",
            "chapter_code": "a02",
            "section_code": "01",
            "section_title": "2.1 有理数的加法与减法",
            "subsection_title": "2.1.1 有理数的加法",
            "title": "有理数加法法则",
            "origin": "human_outline",
            "review_status": "pending_review",
            "reviewed_by": None,
            "reviewed_at": None,
            "deprecated": False,
            "deprecated_at": None,
            "deprecated_reason": None,
            "replacement_ids": [],
            "source_pages": None,
            "expected_error_patterns": ["异号相加取错符号"],
        },
    ],
}

BASE_RELATIONS: dict[str, Any] = {
    "schema_version": "1.0.0",
    "relations": [
        {
            "from": "g7.math.a04.02.02",
            "to": "g7.math.a04.02.01",
            "type": "PREREQUISITE",
            "origin": "human",
            "review_status": "pending_review",
            "confidence": 1.0,
        },
        {
            "from": "g7.math.a04.02.02",
            "to": "g7.math.a02.01.01",
            "type": "PREREQUISITE",
            "origin": "inferred",
            "review_status": "pending_review",
            "confidence": 0.6,
        },
    ],
}


def write_pair(tmp_path: Path, points: dict, relations: dict) -> tuple[Path, Path]:
    p_file = tmp_path / "grade-7-math.json"
    r_file = tmp_path / "knowledge-relations.json"
    p_file.write_text(json.dumps(points, ensure_ascii=False), encoding="utf-8")
    r_file.write_text(json.dumps(relations, ensure_ascii=False), encoding="utf-8")
    return p_file, r_file


def test_valid_baseline_passes(tmp_path: Path):
    p_file, r_file = write_pair(tmp_path, BASE_DOC, BASE_RELATIONS)
    pending, problems, stats = vkb.run(strict=True, points_file=p_file, relations_file=r_file, require_outline=False)
    assert problems == [], problems
    assert stats["total"] == 3 and stats["active"] == 3
    assert stats["prerequisite_edges"] == 2
    assert pending is True, "存在未审的推断关系时应报告待办"
    assert any("REVIEW-REQUIRED" in p for p in stats["review_required"])


def test_duplicate_id_is_caught(tmp_path: Path):
    points = copy.deepcopy(BASE_DOC)
    points["knowledge_points"].append(copy.deepcopy(points["knowledge_points"][0]))
    p_file, r_file = write_pair(tmp_path, points, BASE_RELATIONS)
    _, problems, _ = vkb.run(strict=True, points_file=p_file, relations_file=r_file, require_outline=False)
    assert any("ID 重复" in p for p in problems)


def test_malformed_id_is_caught(tmp_path: Path):
    points = copy.deepcopy(BASE_DOC)
    points["knowledge_points"][0]["id"] = "g7.math.4.2.1"
    p_file, r_file = write_pair(tmp_path, points, BASE_RELATIONS)
    _, problems, _ = vkb.run(strict=True, points_file=p_file, relations_file=r_file, require_outline=False)
    assert any("ID 文法非法" in p for p in problems)


def test_chapter_section_mismatch_is_caught(tmp_path: Path):
    points = copy.deepcopy(BASE_DOC)
    points["knowledge_points"][0]["section_code"] = "03"
    p_file, r_file = write_pair(tmp_path, points, BASE_RELATIONS)
    _, problems, _ = vkb.run(strict=True, points_file=p_file, relations_file=r_file, require_outline=False)
    assert any("与 ID 中的 02 不一致" in p for p in problems)


def test_chapter_not_declared_in_scope_is_caught(tmp_path: Path):
    points = copy.deepcopy(BASE_DOC)
    points["scope"]["chapters"] = [c for c in points["scope"]["chapters"] if c["code"] != "a02"]
    p_file, r_file = write_pair(tmp_path, points, BASE_RELATIONS)
    _, problems, _ = vkb.run(strict=True, points_file=p_file, relations_file=r_file, require_outline=False)
    assert any("未在 scope.chapters 中声明" in p for p in problems)


def test_relation_to_unknown_id_is_caught(tmp_path: Path):
    relations = copy.deepcopy(BASE_RELATIONS)
    relations["relations"][0]["to"] = "g7.math.a09.01.01"
    p_file, r_file = write_pair(tmp_path, BASE_DOC, relations)
    _, problems, _ = vkb.run(strict=True, points_file=p_file, relations_file=r_file, require_outline=False)
    assert any("to 不存在或已废弃" in p for p in problems)


def test_relation_type_outside_vocab_is_caught(tmp_path: Path):
    relations = copy.deepcopy(BASE_RELATIONS)
    relations["relations"][0]["type"] = "LEADS_TO"
    p_file, r_file = write_pair(tmp_path, BASE_DOC, relations)
    _, problems, _ = vkb.run(strict=True, points_file=p_file, relations_file=r_file, require_outline=False)
    assert any("不在统一词表" in p for p in problems)


def test_self_loop_is_caught(tmp_path: Path):
    relations = copy.deepcopy(BASE_RELATIONS)
    relations["relations"][0]["to"] = relations["relations"][0]["from"]
    p_file, r_file = write_pair(tmp_path, BASE_DOC, relations)
    _, problems, _ = vkb.run(strict=True, points_file=p_file, relations_file=r_file, require_outline=False)
    assert any("自环" in p for p in problems)


def test_prerequisite_cycle_is_caught(tmp_path: Path):
    edges = [
        ("g7.math.a04.02.01", "g7.math.a04.02.02"),
        ("g7.math.a04.02.02", "g7.math.a04.02.01"),
    ]
    problems = vkb.check_prerequisite_dag(edges)
    assert any("存在环" in p for p in problems)


def test_prerequisite_chain_without_cycle_passes():
    edges = [
        ("g7.math.a04.02.02", "g7.math.a04.02.01"),
        ("g7.math.a04.02.01", "g7.math.a02.01.01"),
    ]
    assert vkb.check_prerequisite_dag(edges) == []


def test_reviewed_top_status_requires_credentials(tmp_path: Path):
    """声称 reviewed 却没有审核人 —— Schema 层就必须拒绝（R25）。"""
    points = copy.deepcopy(BASE_DOC)
    points["review_status"] = "reviewed"
    points["reviewed_by"] = None
    p_file, r_file = write_pair(tmp_path, points, BASE_RELATIONS)
    _, problems, _ = vkb.run(strict=True, points_file=p_file, relations_file=r_file, require_outline=False)
    assert any("reviewed_by" in p or "缺" in p for p in problems)


def test_reviewed_top_status_with_unreviewed_children_is_caught(tmp_path: Path):
    points = copy.deepcopy(BASE_DOC)
    points["review_status"] = "reviewed"
    points["reviewed_by"] = "张老师"
    points["reviewed_at"] = "2026-11-01"
    p_file, r_file = write_pair(tmp_path, points, BASE_RELATIONS)
    _, problems, _ = vkb.run(strict=True, points_file=p_file, relations_file=r_file, require_outline=False)
    assert any("仍未审" in p for p in problems)


def test_missing_files_default_skip_but_strict_fails(tmp_path: Path):
    missing = tmp_path / "nope.json"
    pending, problems, stats = vkb.run(strict=False, points_file=missing, relations_file=missing, require_outline=False)
    assert stats == {"missing": True} and problems == [] and pending is False
    _, problems_strict, _ = vkb.run(strict=True, points_file=missing, relations_file=missing, require_outline=False)
    assert problems_strict


def test_repo_csv_and_json_are_aligned():
    """真实仓库的 outline-t1.csv 必须与 JSON 完全同步，否则"人工大纲来源"这个声称不成立。"""
    pending, problems, stats = vkb.run(strict=True)
    assert problems == [], problems
    assert stats["active"] == 26
    assert pending is True, "全量 inferred 未审时必须有待办"


def test_csv_title_drift_is_caught(tmp_path: Path):
    """CSV 与 JSON 标题漂移必须被抓到 —— 这是本次开发实际发现过的缺陷形态。"""
    kb = Path(vkb.KB_DIR)
    points = json.loads((kb / "grade-7-math.json").read_text(encoding="utf-8"))
    relations = json.loads((kb / "knowledge-relations.json").read_text(encoding="utf-8"))
    csv_text = (kb / "outline-t1.csv").read_text(encoding="utf-8")
    drifted = csv_text.replace("有理数减法法则（减法转加法）", "减法法则（改了名字）", 1)

    p_file = tmp_path / "grade-7-math.json"
    r_file = tmp_path / "knowledge-relations.json"
    c_file = tmp_path / "outline-t1.csv"
    p_file.write_text(json.dumps(points, ensure_ascii=False), encoding="utf-8")
    r_file.write_text(json.dumps(relations, ensure_ascii=False), encoding="utf-8")
    c_file.write_text(drifted, encoding="utf-8")

    _, problems, _ = vkb.run(strict=True, points_file=p_file, relations_file=r_file, outline_csv=c_file)
    assert any("在 JSON 中不存在" in p for p in problems), problems
    assert any("PREREQUISITE 边与 CSV 不一致" in p for p in problems), problems


def test_missing_outline_csv_is_caught(tmp_path: Path):
    """JSON 存在但没有大纲凭据文件时，必须报缺失而不是静默通过（R13 溯源）。"""
    p_file = tmp_path / "grade-7-math.json"
    r_file = tmp_path / "knowledge-relations.json"
    write_pair(tmp_path, BASE_DOC, BASE_RELATIONS)
    _, problems, _ = vkb.run(
        strict=True, points_file=p_file, relations_file=r_file, outline_csv=tmp_path / "absent.csv"
    )
    assert any("缺少大纲凭据文件" in p for p in problems)


def test_shared_enum_is_single_source():
    """关系类型必须从 common.defs.json 取，脚本内不得有第二份字面量（R8）。"""
    values = vkb.shared_enum("relation_type")
    text = Path(vkb.__file__).read_text(encoding="utf-8")
    assert "EASILY_CONFUSED" in values
    assert "EASILY_CONFUSED" not in text, "脚本里出现了第二份枚举字面量"


def test_shared_enum_missing_raises(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(vkb, "_COMMON_DEFS_PATH", tmp_path / "absent.json")
    with pytest.raises(RuntimeError):
        vkb.shared_enum("relation_type")


def test_deprecated_kp_cannot_be_relation_endpoint(tmp_path: Path):
    """废弃知识点仍可被历史 evidence 解析，但不得再作为关系边端点（ADR-0006）。"""
    points = copy.deepcopy(BASE_DOC)
    entry = points["knowledge_points"][2]
    entry["deprecated"] = True
    entry["deprecated_at"] = "2026-11-20"
    entry["deprecated_reason"] = "并入 2.1 加法法则"
    p_file, r_file = write_pair(tmp_path, points, BASE_RELATIONS)
    _, problems, stats = vkb.run(strict=True, points_file=p_file, relations_file=r_file, require_outline=False)
    assert stats["deprecated"] == 1 and stats["active"] == 2
    assert any("不存在或已废弃" in p for p in problems)
