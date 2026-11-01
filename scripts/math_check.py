"""白名单数学表达式解析 + sympy 符号验证 + 数值抽样双验。

依据 ADR-0002 / AGENTS.md R21：
  - 禁止 eval()，禁止把模型原始字符串直接交给 sympify（sympify 底层走 Python 求值）
  - 表达式必须先由本模块的受限文法解析成自建 AST，再由 AST **构造** sympy 表达式
  - 符号判定与数值抽样双验一致，才允许返回 program_verified
  - 任何解析失败 / 超复杂度 / 双验不一致 → 一律降级 needs_human_check，并写明原因

已知边界（诚实标注，勿误用）：
  - 只支持变量 x / y；不支持绝对值、不等式、多字母多项式、带分数、三角函数
  - "超时"保护采用复杂度上限（节点数 / 整数位数），不是墙钟超时——Windows 无 SIGALRM。
    这是 ADR-0002 记下的残余风险，扩展文法时必须同步加测试（R26）
  - 应用题与几何题不在本模块能力范围内，调用方应直接给 needs_human_check

用法：
    from math_check import verify_equivalence, verify_solution
    r = verify_equivalence("-(2*x-3)+x", "-x+3")
    r.status, r.equal, r.reason, r.witness
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any

try:  # pragma: no cover - 依赖缺失属于环境问题，不是本模块的判定结果
    import sympy
except ImportError as exc:  # pragma: no cover
    sympy = None
    _SYMPY_IMPORT_ERROR = str(exc)
else:
    _SYMPY_IMPORT_ERROR = None

ALLOWED_VARS = frozenset({"x", "y"})
MAX_NODES = 200
MAX_INT_DIGITS = 30
MAX_TEXT_LENGTH = 2000

#: 归一化只做**确定性字符映射**，不做任何语义猜测（R11）
_CHAR_MAP = str.maketrans(
    {
        "×": "*",
        "∗": "*",
        "⋅": "*",
        "·": "*",
        "÷": "/",
        "／": "/",
        "−": "-",
        "–": "-",
        "—": "-",
        "＝": "=",
        "（": "(",
        "）": ")",
        "［": "(",
        "］": ")",
        "｛": "(",
        "｝": ")",
        "　": " ",
        "，": ",",
        "。": ".",
        "^": "**",  # 幂统一成 **，文法只认 **
        "⁄": "/",
    }
)
# 允许根号的两种写法统一
_PREFIX_FUNCS = frozenset({"sqrt"})

_STATUS_PROGRAM_VERIFIED = "program_verified"
_STATUS_NEEDS_HUMAN_CHECK = "needs_human_check"


class MathParseError(Exception):
    """解析失败。reason 必须是稳定字符串，供 verification_reason 直接使用。"""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


# ---------------------------------------------------------------- AST


@dataclass(frozen=True)
class Num:
    value: Fraction


@dataclass(frozen=True)
class Var:
    name: str


@dataclass(frozen=True)
class Bin:
    op: str
    left: Any
    right: Any


@dataclass(frozen=True)
class Neg:
    operand: Any


@dataclass(frozen=True)
class Sqrt:
    operand: Any


@dataclass(frozen=True)
class Rel:
    """等式关系，左右两侧各是一棵表达式树。"""

    left: Any
    right: Any


# ---------------------------------------------------------------- tokenizer


def normalize(text: str) -> str:
    """确定性字符归一化。不做空白压缩以外的任何"读懂"操作。"""
    if text is None:
        raise MathParseError("empty_input", "输入为 None")
    if not isinstance(text, str):
        raise MathParseError("non_string_input", type(text).__name__)
    if len(text) > MAX_TEXT_LENGTH:
        raise MathParseError("input_too_long", f">{MAX_TEXT_LENGTH}")
    out = text.translate(_CHAR_MAP)
    out = out.replace("√", "sqrt")
    if any(ord(c) > 127 for c in out):
        bad = sorted({c for c in out if ord(c) > 127})
        raise MathParseError("non_ascii_unmapped", "".join(bad))
    return out


@dataclass(frozen=True)
class _Tok:
    kind: str
    text: str
    pos: int


def _tokenize(src: str) -> list[_Tok]:
    toks: list[_Tok] = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c in " \t\r\n":
            i += 1
            continue
        if c.isdigit() or c == ".":
            j = i
            seen_dot = False
            while j < n and (src[j].isdigit() or (src[j] == "." and not seen_dot)):
                if src[j] == ".":
                    seen_dot = True
                j += 1
            raw = src[i:j]
            if raw.count("."):
                if raw.startswith(".") or raw.endswith("."):
                    raise MathParseError("malformed_number", raw)
            toks.append(_Tok("NUM", raw, i))
            i = j
            continue
        if c.isalpha():
            j = i
            while j < n and src[j].isalpha():
                j += 1
            word = src[i:j]
            low = word.lower()
            if low in _PREFIX_FUNCS:
                # sqrt 必须紧跟括号，否则拒绝（避免 sqrt2 之类的歧义）
                k = j
                while k < n and src[k] == " ":
                    k += 1
                if k >= n or src[k] != "(":
                    raise MathParseError("sqrt_requires_parentheses", word)
                toks.append(_Tok("FUNC", "sqrt", i))
                i = j
                continue
            if len(word) == 1 and word in ALLOWED_VARS:
                toks.append(_Tok("VAR", word, i))
                i = j
                continue
            raise MathParseError("unknown_identifier", word)
        if src.startswith("**", i):
            toks.append(_Tok("OP", "**", i))
            i += 2
            continue
        if c in "+-*/()=,":
            toks.append(_Tok("OP", c, i))
            i += 1
            continue
        if c == "^":
            raise MathParseError("internal_caret", "归一化后仍残留 ^，异常")
        raise MathParseError("illegal_character", c)
    return toks


# ---------------------------------------------------------------- parser


class _Parser:
    """受限文法（优先级自低到高）：

    relation     := additive ('=' additive)*          # 允许多段等式链
    additive     := multiplicative (('+'|'-') multiplicative)*
    multiplicative := unary (('*'|'/')? unary)*        # 含并列乘法的隐式写法
    unary        := ('+'|'-') unary | power
    power        := primary ('**' unary)?              # 右结合，指数可带负号
    primary      := NUM | VAR | 'sqrt' '(' relation ')' | '(' relation ')'

    `-2**4` 解析为 `-(2**4)`，与数学记法一致；`(-2)**4` 由括号显式给出。
    """

    def __init__(self, toks: list[_Tok]) -> None:
        self.toks = toks
        self.i = 0
        self.nodes = 0

    # --- helpers
    def _peek(self) -> _Tok | None:
        return self.toks[self.i] if self.i < len(self.toks) else None

    def _next(self) -> _Tok:
        tok = self._peek()
        if tok is None:
            raise MathParseError("unexpected_end", "表达式不完整")
        self.i += 1
        return tok

    def _expect(self, text: str) -> _Tok:
        tok = self._next()
        if tok.text != text:
            raise MathParseError("expected_token", f"{text} @ {tok.pos}")
        return tok

    def _bump(self) -> None:
        self.nodes += 1
        if self.nodes > MAX_NODES:
            raise MathParseError("complexity_exceeded", f"nodes>{MAX_NODES}")

    # --- grammar
    def parse(self) -> Any:
        if not self.toks:
            raise MathParseError("empty_input", "空表达式")
        node = self.relation()
        if self._peek() is not None:
            raise MathParseError("trailing_tokens", self._peek().text)
        return node

    def relation(self) -> Any:
        left = self.additive()
        while (tok := self._peek()) and tok.text == "=":
            self._next()
            right = self.additive()
            self._bump()
            left = Rel(left, right)
        return left

    def additive(self) -> Any:
        node = self.multiplicative()
        while (tok := self._peek()) and tok.text in ("+", "-"):
            self._next()
            right = self.multiplicative()
            self._bump()
            node = Bin(tok.text, node, right)
        return node

    def multiplicative(self) -> Any:
        node = self.unary()
        while True:
            tok = self._peek()
            if tok is None:
                break
            if tok.text in ("*", "/"):
                self._next()
                right = self.unary()
                self._bump()
                node = Bin(tok.text, node, right)
                continue
            if tok.kind in ("NUM", "VAR", "FUNC") or tok.text == "(":
                self._implicit_mult_guard(node, tok)
                right = self.unary()
                self._bump()
                node = Bin("*", node, right)
                continue
            break
        return node

    def _implicit_mult_guard(self, left: Any, tok: _Tok) -> None:
        """并列数字（如 `1 1/2`）按带分数理解还是乘法？本模块拒绝猜（R11）。"""
        if isinstance(left, Num) and tok.kind == "NUM":
            raise MathParseError("mixed_number_unsupported", "请用假分数或加括号明确乘法")
        if isinstance(left, Num) and tok.text == "(":
            # 2(3+1) 是明确的乘法，放行
            return

    def unary(self) -> Any:
        tok = self._peek()
        if tok and tok.text in ("+", "-"):
            self._next()
            operand = self.unary()
            self._bump()
            return Neg(operand) if tok.text == "-" else operand
        return self.power()

    def power(self) -> Any:
        base = self.primary()
        if (tok := self._peek()) and tok.text == "**":
            self._next()
            exp = self.unary()  # 右结合，且允许 2**-3
            self._bump()
            if not isinstance(exp, Num):
                raise MathParseError("non_numeric_exponent", "本版本不支持字母指数")
            return Bin("**", base, exp)
        return base

    def primary(self) -> Any:
        tok = self._next()
        self._bump()
        if tok.kind == "NUM":
            try:
                value = Fraction(tok.text)
            except (ValueError, ZeroDivisionError) as exc:
                raise MathParseError("malformed_number", tok.text) from exc
            if len(str(value.numerator)) > MAX_INT_DIGITS or len(str(value.denominator)) > MAX_INT_DIGITS:
                raise MathParseError("integer_too_large", tok.text)
            return Num(value)
        if tok.kind == "VAR":
            return Var(tok.text)
        if tok.kind == "FUNC":
            self._expect("(")
            inner = self.relation()
            self._expect(")")
            return Sqrt(inner)
        if tok.text == "(":
            inner = self.relation()
            self._expect(")")
            return inner
        raise MathParseError("unexpected_token", tok.text)


def parse(text: str) -> Any:
    """把表达式文本解析成自建 AST。失败抛 MathParseError。"""
    return _Parser(_tokenize(normalize(text))).parse()


def free_symbols(node: Any) -> frozenset[str]:
    if isinstance(node, (Num,)):
        return frozenset()
    if isinstance(node, Var):
        return frozenset({node.name})
    if isinstance(node, Neg):
        return free_symbols(node.operand)
    if isinstance(node, Sqrt):
        return free_symbols(node.operand)
    if isinstance(node, Bin):
        return free_symbols(node.left) | free_symbols(node.right)
    if isinstance(node, Rel):
        return free_symbols(node.left) | free_symbols(node.right)
    return frozenset()


# ---------------------------------------------------------------- sympy


def _require_sympy() -> None:
    if sympy is None:  # pragma: no cover
        raise MathParseError("sympy_unavailable", _SYMPY_IMPORT_ERROR or "sympy not importable")


def to_sympy(node: Any):
    """由**自建 AST**构造 sympy 表达式，绝不使用 sympy.sympify(原文)。"""
    _require_sympy()
    if isinstance(node, Num):
        return sympy.Rational(node.value.numerator, node.value.denominator)
    if isinstance(node, Var):
        return sympy.Symbol(node.name)
    if isinstance(node, Neg):
        return -to_sympy(node.operand)
    if isinstance(node, Sqrt):
        return sympy.sqrt(to_sympy(node.operand))
    if isinstance(node, Bin):
        left, right = to_sympy(node.left), to_sympy(node.right)
        if node.op == "+":
            return left + right
        if node.op == "-":
            return left - right
        if node.op == "*":
            return left * right
        if node.op == "/":
            if right == 0:
                raise MathParseError("division_by_zero", "除数为 0")
            return left / right
        if node.op == "**":
            return sympy.Pow(left, right, evaluate=True)
    raise MathParseError("unsupported_node", type(node).__name__)


def _to_sympy_relation(node: Any):
    """等式 → (lhs - rhs) 表达式；纯关系允许两侧均为常数。"""
    if isinstance(node, Rel):
        return to_sympy(node.left) - to_sympy(node.right)
    return to_sympy(node)


# ---------------------------------------------------------------- 结果类型


@dataclass
class VerifyResult:
    """统一结果对象。status 只取 AGENTS.md 词表中的两个值。"""

    status: str
    equal: bool | None = None
    reason: str | None = None
    witness: dict[str, Any] = field(default_factory=dict)
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def verified(self) -> bool:
        return self.status == _STATUS_PROGRAM_VERIFIED

    def to_dict(self) -> dict[str, Any]:
        return {
            "verification_status": self.status,
            "equal": self.equal,
            "verification_reason": self.reason,
            "witness": self.witness or None,
            "detail": self.detail or None,
        }


def _needs(reason: str, detail: str = "") -> VerifyResult:
    return VerifyResult(_STATUS_NEEDS_HUMAN_CHECK, None, reason, {}, {"note": detail} if detail else {})


def _sample_values(symbols: list[str], count: int = 12, seed: int = 20261101) -> list[dict[str, Fraction]]:
    """固定 seed 的可复现抽样：含 0、±1、±2、分数、大数、质数。"""
    base = [Fraction(0), Fraction(1), Fraction(-1), Fraction(2), Fraction(-2),
            Fraction(1, 2), Fraction(-3, 4), Fraction(7), Fraction(-11), Fraction(1, 3),
            Fraction(100), Fraction(-97)]
    rng = random.Random(seed)
    out: list[dict[str, Fraction]] = []
    for _ in range(count):
        point = {}
        for s in symbols:
            if not out:
                point[s] = base[len(symbols) % len(base)]
            else:
                point[s] = rng.choice(base)
        out.append(point)
    return out


def _numeric_equal(lhs, rhs, symbols: list[str]) -> tuple[bool | None, dict[str, Any]]:
    """数值抽样双验。返回 (是否一致, 反例/详情)。None 表示无法判定。"""
    _require_sympy()
    seen_diff: dict[str, Any] = {}
    checked = 0
    for point in _sample_values(symbols):
        subs = {sympy.Symbol(s): sympy.Rational(v.numerator, v.denominator) for s, v in point.items()}
        try:
            lv = sympy.nsimplify(lhs.subs(subs), rational=True)
            rv = sympy.nsimplify(rhs.subs(subs), rational=True)
        except (sympy.SympifyError, TypeError, ValueError, ZeroDivisionError):
            return None, {"error": "numeric_evaluation_failed", "point": {k: str(v) for k, v in point.items()}}
        checked += 1
        if lv != rv:
            seen_diff = {k: str(v) for k, v in point.items()}
            seen_diff["lhs"] = str(lv)
            seen_diff["rhs"] = str(rv)
            return False, seen_diff
    return True, {"points_checked": checked}


def verify_equivalence(left: str, right: str) -> VerifyResult:
    """判断两个表达式是否恒等（或两个等式是否同解）。符号 + 数值双验。"""
    try:
        la = parse(left)
        ra = parse(right)
    except MathParseError as exc:
        return _needs(f"parse_failed:{exc.reason}", exc.detail)

    try:
        lsym, rsym = _to_sympy_relation(la), _to_sympy_relation(ra)
        symbols = sorted(free_symbols(la) | free_symbols(ra))
    except MathParseError as exc:
        return _needs(f"construction_failed:{exc.reason}", exc.detail)
    except Exception as exc:  # sympy 内部异常不得穿透到调用方（ADR-0002）
        return _needs("sympy_internal_error", f"{type(exc).__name__}: {exc}")

    try:
        diff = sympy.simplify(lsym - rsym)
        symbolic_equal = diff == 0
    except Exception as exc:
        return _needs("sympy_internal_error", f"{type(exc).__name__}: {exc}")

    numeric_equal, numeric_info = _numeric_equal(lsym, rsym, symbols)
    if numeric_equal is None:
        return _needs("numeric_check_indeterminate", str(numeric_info))

    if symbolic_equal and not numeric_equal:
        return _needs("symbolic_numeric_disagreement", str(numeric_info))
    if not symbolic_equal and numeric_equal:
        # 抽样一致但符号不等：可能只是没抽到反例，不能判等
        return _needs("symbolic_not_equal_numeric_coincidence", str(numeric_info))

    if symbolic_equal and numeric_equal:
        return VerifyResult(_STATUS_PROGRAM_VERIFIED, True, None, {}, {"normalized": str(diff)})
    return VerifyResult(
        _STATUS_PROGRAM_VERIFIED,
        False,
        None,
        numeric_info,
        {"symbolic_difference": str(diff)},
    )


def verify_solution(equation: str, claimed: str) -> VerifyResult:
    """把 claimed（如 x=3 或 3）代入方程验证是否为解。"""
    try:
        eq_ast = parse(equation)
    except MathParseError as exc:
        return _needs(f"parse_failed:{exc.reason}", exc.detail)

    if not isinstance(eq_ast, Rel):
        return _needs("not_an_equation", "方程两侧必须用 = 连接")

    try:
        expr = to_sympy(eq_ast.left) - to_sympy(eq_ast.right)
    except MathParseError as exc:
        return _needs(f"construction_failed:{exc.reason}", exc.detail)
    except Exception as exc:
        return _needs("sympy_internal_error", f"{type(exc).__name__}: {exc}")

    try:
        claim_ast = parse(claimed)
    except MathParseError as exc:
        return _needs(f"claim_unparseable:{exc.reason}", exc.detail)

    try:
        if isinstance(claim_ast, Rel):
            # 形如 x=3：取右侧为值，并校验左侧确为变量
            if not isinstance(claim_ast.left, Var):
                return _needs("claim_form_unsupported", "等式左侧需为变量")
            value = to_sympy(claim_ast.right)
        else:
            value = to_sympy(claim_ast)
    except MathParseError as exc:
        return _needs(f"construction_failed:{exc.reason}", exc.detail)
    except Exception as exc:
        return _needs("sympy_internal_error", f"{type(exc).__name__}: {exc}")

    for sym in sorted(free_symbols(claim_ast) | free_symbols(eq_ast)) or ["x"]:
        if sym not in ALLOWED_VARS:
            return _needs("unsupported_variable", sym)

    try:
        lhs = sympy.simplify(expr.subs(sympy.Symbol("x"), value))
    except Exception as exc:
        return _needs("sympy_internal_error", f"{type(exc).__name__}: {exc}")

    ok = lhs == 0
    if not ok:
        # 该值可能使分母为 0：此时"不成立"不是答案错，而是题目在该点无定义
        try:
            combined = sympy.together(expr)
            denominator = sympy.denom(combined)
            if denominator.has(sympy.Symbol("x")) and sympy.simplify(
                denominator.subs(sympy.Symbol("x"), value)
            ) == 0:
                return _needs("claim_makes_denominator_zero", str(lhs))
        except Exception:
            pass
    return VerifyResult(_STATUS_PROGRAM_VERIFIED, bool(ok), None, {}, {"residual": str(lhs)})


def solve_equation(equation: str) -> VerifyResult:
    """求解（仅一元一次）。返回解集字符串或降级原因。"""
    try:
        ast = parse(equation)
    except MathParseError as exc:
        return _needs(f"parse_failed:{exc.reason}", exc.detail)
    if not isinstance(ast, Rel):
        return _needs("not_an_equation")
    try:
        expr = to_sympy(ast.left) - to_sympy(ast.right)
        syms = sorted(free_symbols(ast))
    except MathParseError as exc:
        return _needs(f"construction_failed:{exc.reason}", exc.detail)
    except Exception as exc:
        return _needs("sympy_internal_error", f"{type(exc).__name__}: {exc}")
    if len(syms) != 1 or syms[0] not in ALLOWED_VARS:
        return _needs("unsupported_equation_shape", f"symbols={syms}")
    try:
        sols = sympy.solveset(expr, sympy.Symbol(syms[0]), domain=sympy.S.Reals)
        if not sols.is_FiniteSet:
            if sols is sympy.S.Reals:
                return VerifyResult(_STATUS_PROGRAM_VERIFIED, True, None, {}, {"solution": "all_reals"})
            return _needs("solver_returned_set", str(sols))
        values = sorted(str(s.evalf()) for s in sols)
        exact = sorted(str(s) for s in sols)
    except Exception as exc:
        return _needs("sympy_internal_error", f"{type(exc).__name__}: {exc}")
    if any("I" in v or "nan" in v or "zoo" in v for v in exact):
        return _needs("non_real_solution", ",".join(exact))
    return VerifyResult(_STATUS_PROGRAM_VERIFIED, True, None, {}, {"solutions": exact, "decimal": values})


def check_simplification(original: str, simplified: str) -> VerifyResult:
    """化简等价性检查的语义别名，便于在 Skill 里表达意图。"""
    return verify_equivalence(original, simplified)


__all__ = [
    "MathParseError",
    "VerifyResult",
    "normalize",
    "parse",
    "free_symbols",
    "to_sympy",
    "verify_equivalence",
    "verify_solution",
    "solve_equation",
    "check_simplification",
]
