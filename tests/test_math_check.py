"""math_check 的单元测试（ADR-0002 验证小节要求的 4 类 + 边界）。

调的是**确定性**：同一输入必须永远给同一结论，且任何不确定情况一律降级，
绝不允许"猜一个答案"当作已验证（R21 / R25）。
"""

from __future__ import annotations

import pytest

import math_check
from math_check import (
    MathParseError,
    parse,
    solve_equation,
    verify_equivalence,
    verify_solution,
)


# ---------------------------------------------------------------- 类 1：去括号漏变号


def test_bracket_negative_distributes_over_all_terms():
    """正确化简必须判等，且是 program_verified。"""
    r = verify_equivalence("-(2*x-3)+x", "-x+3")
    assert r.status == "program_verified"
    assert r.equal is True


def test_bracket_negative_missing_sign_change_is_detected():
    """学生的 -x-3（常数项漏变号）必须判不等，并给出可复核的反例。"""
    r = verify_equivalence("-(2*x-3)+x", "-x-3")
    assert r.status == "program_verified"
    assert r.equal is False
    assert r.witness, "判不等时必须提供数值反例，否则结论不可复核"


def test_implicit_multiplication_is_accepted():
    """学生手写常写 2x 而非 2*x，必须能解析。"""
    assert verify_equivalence("-(2x-3)+x", "-x+3").equal is True


def test_fullwidth_and_unicode_operators_normalize():
    r = verify_equivalence("－（２ｘ－３）＋ｘ", "-x+3")
    # 全角数字不在白名单文法内（避免把"2"的两种字形都当作同一数字）
    assert r.status == "needs_human_check"
    assert "parse_failed" in (r.reason or "")


def test_sqrt_equivalence():
    assert verify_equivalence("sqrt(4)", "2").equal is True
    assert verify_equivalence("sqrt(9)", "4").equal is False


# ---------------------------------------------------------------- 类 2：负数乘方括号


def test_power_with_parenthesized_negative_base():
    assert verify_equivalence("(-2)**4", "16").equal is True


def test_power_without_parentheses_binds_looser_than_unary_minus():
    """-2^4 在数学记法里是 -(2^4) = -16，与 (-2)^4 = 16 不同。这是七年级高频错误。"""
    assert verify_equivalence("-2**4", "-16").equal is True
    assert verify_equivalence("-2**4", "16").equal is False
    assert verify_equivalence("(-2)**4", "-16").equal is False


def test_odd_exponent_negative_base():
    assert verify_equivalence("(-2)**3", "-8").equal is True


def test_caret_is_normalized_to_double_star():
    assert verify_equivalence("(-2)^4", "16").equal is True


# ---------------------------------------------------------------- 类 3：注入与非法输入


@pytest.mark.parametrize(
    "text,expected_reason",
    [
        ('__import__("os")', "illegal_character"),
        ("lambda: 1", "unknown_identifier"),
        ("x = 1; y = 2", "illegal_character"),
        ("[1, 2]", "illegal_character"),
        ("z + 1", "unknown_identifier"),  # 只允许 x / y
        ("abs(-3)", "unknown_identifier"),  # 不支持的函数
        ("2 1/2", "mixed_number_unsupported"),  # 带分数：拒绝猜（R11）
        ("", "empty_input"),
        ("2 +", "unexpected_end"),
        ("(1+2", "unexpected_end"),
        ("1)", "trailing_tokens"),
    ],
)
def test_adversarial_inputs_are_rejected(text, expected_reason):
    with pytest.raises(MathParseError) as excinfo:
        parse(text)
    assert excinfo.value.reason == expected_reason


@pytest.mark.parametrize(
    "text,expected_status",
    [
        ('__import__("os")', "needs_human_check"),
        ("2 1/2", "needs_human_check"),
        ("", "needs_human_check"),
    ],
)
def test_rejected_input_degrades_instead_of_raising(text, expected_status):
    """解析失败必须转成降级结论，不能把异常抛到 Skill 输出层（ADR-0002）。"""
    r = verify_equivalence(text, "0")
    assert r.status == expected_status
    assert r.equal is None


def test_no_eval_and_no_sympify_of_raw_text():
    """本模块的 AST 里不得出现 eval/exec 调用，也不得把归一化后的原文交给 sympify。

    只检查真实代码节点，避免被"禁止 eval()"这类注释文字误判。
    """
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(math_check))
    calls: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                calls.append(func.id)
            elif isinstance(func, ast.Attribute):
                calls.append(func.attr)
    assert "eval" not in calls and "exec" not in calls
    assert "sympify" not in calls
    assert any("Rational" in c or "Symbol" in c for c in calls), "应通过构造而非解析文本建立 sympy 表达式"


def test_complexity_guard_trips():
    big = "+".join(["1"] * 250)
    with pytest.raises(MathParseError) as excinfo:
        parse(big)
    assert excinfo.value.reason == "complexity_exceeded"


def test_integer_digit_guard():
    with pytest.raises(MathParseError) as excinfo:
        parse("1" * 40)
    assert excinfo.value.reason == "integer_too_large"


def test_division_by_zero_rejected_at_construction():
    r = verify_equivalence("1/0", "0")
    assert r.status == "needs_human_check"
    assert "division_by_zero" in (r.reason or "")


# ---------------------------------------------------------------- 类 4：双验不一致的降级


def test_symbolic_true_numeric_false_degrades(monkeypatch):
    monkeypatch.setattr(math_check, "_numeric_equal", lambda l, r, s: (False, {"point": "x=1"}))
    r = verify_equivalence("x+x", "2*x")
    assert r.status == "needs_human_check"
    assert r.reason == "symbolic_numeric_disagreement"


def test_symbolic_false_numeric_true_degrades(monkeypatch):
    """抽样恰好一致但符号不等 —— 绝不能判成相等（假阳性是教育场景最危险的错误）。"""
    monkeypatch.setattr(math_check, "_numeric_equal", lambda l, r, s: (True, {"points_checked": 12}))
    r = verify_equivalence("x+1", "x+2")
    assert r.status == "needs_human_check"
    assert r.reason == "symbolic_not_equal_numeric_coincidence"


def test_sympy_internal_error_degrades(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("simplify blew up")

    monkeypatch.setattr(math_check.sympy, "simplify", boom)
    r = verify_equivalence("x+1", "x+1")
    assert r.status == "needs_human_check"
    assert r.reason == "sympy_internal_error"


def test_numeric_indeterminate_degrades(monkeypatch):
    monkeypatch.setattr(math_check, "_numeric_equal", lambda l, r, s: (None, {"error": "x"}))
    r = verify_equivalence("x+1", "x+1")
    assert r.status == "needs_human_check"
    assert r.reason == "numeric_check_indeterminate"


# ---------------------------------------------------------------- 方程求解与验证解


def test_solve_linear_one_step():
    r = solve_equation("2*x+3=7")
    assert r.status == "program_verified"
    assert r.detail["solutions"] == ["2"]


def test_solve_linear_variables_both_sides():
    r = solve_equation("5x-3=2x+6")
    assert r.status == "program_verified"
    assert r.detail["solutions"] == ["3"]


def test_solve_rejects_two_unknowns():
    assert solve_equation("x+y=1").reason == "unsupported_equation_shape"


def test_solve_identity_is_all_reals():
    r = solve_equation("2*(x+1)=2x+2")
    assert r.status == "program_verified"
    assert r.detail.get("solution") == "all_reals"


def test_verify_solution_accepts_correct_root():
    r = verify_solution("2*x+3=7", "x=2")
    assert r.status == "program_verified"
    assert r.equal is True


def test_verify_solution_rejects_wrong_root():
    r = verify_solution("2*x+3=7", "x=3")
    assert r.status == "program_verified"
    assert r.equal is False


def test_verify_solution_bare_number_claim():
    assert verify_solution("2*x+3=7", "2").equal is True


def test_verify_solution_rejects_value_making_denominator_zero():
    r = verify_solution("x/(x-2)=1", "x=2")
    assert r.status == "needs_human_check"
    assert r.reason == "claim_makes_denominator_zero"


def test_verify_solution_rejects_non_equation():
    assert verify_solution("2*x+3", "x=2").reason == "not_an_equation"


# ---------------------------------------------------------------- 确定性与可复现


def test_results_are_deterministic():
    a = verify_equivalence("-(2x-3)+x", "-x-3")
    b = verify_equivalence("-(2x-3)+x", "-x-3")
    assert a.equal == b.equal
    assert a.witness == b.witness, "反例必须可复现，否则回归对比没有意义（ADR-0004）"


def test_fractions_are_exact():
    """0.1+0.2 之类的浮点陷阱不得判等错误。"""
    assert verify_equivalence("0.1+0.2", "0.3").equal is True
    assert verify_equivalence("1/3+1/6", "1/2").equal is True
    assert verify_equivalence("1/3+1/3", "2/5").equal is False
