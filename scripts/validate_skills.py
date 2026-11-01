"""Skill 目录合规检查（面向 OpenClaw 加载前置检查）。

检查项：
  1. skills/*/SKILL.md 存在
  2. YAML frontmatter 含 name / description / user-invocable（R2）
  3. name 与目录名一致，且全局唯一（R4 / 部署前检查）
  4. name 形态合法（小写短横线）
  5. 正文引用的相对路径（references/*.md、scripts/*.py、../../knowledge-base/*）确实存在
  6. 凭证与危险命令扫描（R24、部署前检查）

`skills/` 为空是本阶段的正常状态：此时打印 SKIP 并返回 0，**不得**报错，
否则会在 P3 就把"尚未开发 Skill"误判成"工程有问题"。

YAML 解析用内置极简实现（不引入 PyYAML，见 ADR-0007 的标准库优先项）。
它只支持 `key: value` 标量与注释行；若 SKILL.md 使用复杂 YAML（嵌套、多行块），
本脚本会明确报"frontmatter 含不支持的结构"而不是静默误判。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = ROOT / "skills"

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")
REF_PATH_RE = re.compile(r"(?:references/|scripts/|assets/|templates/|tests/)[A-Za-z0-9_.\-/]+\.[A-Za-z0-9]+")
LOCAL_REF_RE = re.compile(r"\.\./[A-Za-z0-9_.\-/]+\.[A-Za-z0-9]+")

#: 常见凭证形态。宁可多报（人工可加白名单），不可漏报（R24）
SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("openai-style key", re.compile(r"\bsk-[A-Za-z0-9]{16,}")),
    ("anthropic key", re.compile(r"\bsk-ant-[A-Za-z0-9-]{12,}")),
    ("aws access key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("jwt-like", re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}")),
    ("bearer secret", re.compile(r"[Aa]uthorization\s*[:=]\s*Bearer\s+[A-Za-z0-9._\-]{12,}")),
    ("assignment of secret", re.compile(r"(?i)\b(api[_-]?key|secret|password|passwd|access[_-]?token)\b\s*[:=]\s*['\"][^'\"]{8,}['\"]")),
]

DANGEROUS_COMMANDS: list[tuple[str, re.Pattern[str]]] = [
    ("recursive rm of home", re.compile(r"rm\s+-rf\s+~")),
    ("curl piped to shell", re.compile(r"\b(curl|wget)[^\n|]*\|\s*(sudo\s+)?(ba)?sh\b")),
    ("chmod 777", re.compile(r"chmod\s+(-[a-z]+\s+)*777\b")),
    ("eval", re.compile(r"(?<![\w.])eval\s*\(")),
    ("python -c with eval/exec", re.compile(r"\b(exec|eval)\s*\(")),
    ("force push", re.compile(r"git\s+push\s+.*--force(\s|$)")),
    ("git add force", re.compile(r"git\s+add\s+(-[a-zA-Z]*f[a-zA-Z]*\s+|--force)")),
]


class SkillProblem(Exception):
    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems[:10]))
        self.problems = problems


def parse_frontmatter(text: str) -> tuple[dict[str, Any], list[str]]:
    """返回 (字段, 问题)。只处理简单标量，遇到无法确定的结构就报问题。"""
    problems: list[str] = []
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, ["缺少 YAML frontmatter 起始 '---'"]

    end = None
    for index in range(1, min(len(lines), 200)):
        if lines[index].strip() in ("---", "..."):
            end = index
            break
    if end is None:
        return {}, ["frontmatter 未闭合（缺少第二个 '---'）"]

    fields: dict[str, Any] = {}
    for raw in lines[1:end]:
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith((" ", "\t", "-", "*")):
            problems.append(f"frontmatter 含不支持的结构（缩进/列表）: {line.strip()[:40]}")
            continue
        if ":" not in line:
            problems.append(f"frontmatter 行缺少冒号: {line[:40]}")
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if (value.startswith('"') and value.endswith('"') and len(value) >= 2) or (
            value.startswith("'") and value.endswith("'") and len(value) >= 2
        ):
            parsed: Any = value[1:-1]
        elif value.lower() in ("true", "false"):
            parsed = value.lower() == "true"
        elif value == "":
            parsed = ""
        else:
            parsed = value
        fields[key] = parsed
    return fields, problems


#: 只有可执行文件才做危险命令扫描。Markdown/JSON 里"禁止使用 eval()"这类规范表述
#: 属于文档内容，扫它会产生大量误报，反而掩盖真实问题。
EXECUTABLE_SUFFIXES = {".py", ".sh", ".bash", ".ps1", ".cmd", ".bat"}


def scan_secrets(text: str, origin: str) -> list[str]:
    problems: list[str] = []
    for label, pattern in SECRET_PATTERNS:
        if pattern.search(text):
            problems.append(f"{origin}: 疑似凭证（{label}），R24 禁止写入源码")
    return problems


def scan_dangerous(text: str, origin: str) -> list[str]:
    problems: list[str] = []
    for label, pattern in DANGEROUS_COMMANDS:
        if pattern.search(text):
            problems.append(f"{origin}: 含危险命令用法（{label}）")
    return problems


def scan_text(text: str, origin: str, *, executable: bool = True) -> list[str]:
    problems = scan_secrets(text, origin)
    if executable:
        problems.extend(scan_dangerous(text, origin))
    return problems


def check_skill_dir(skill_dir: Path, seen_names: dict[str, str]) -> list[str]:
    problems: list[str] = []
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return [f"{skill_dir.name}: 缺 SKILL.md"]

    text = skill_md.read_text(encoding="utf-8", errors="replace")
    fields, fm_problems = parse_frontmatter(text)
    problems.extend(f"{skill_dir.name}/SKILL.md: {p}" for p in fm_problems)

    for required in ("name", "description", "user-invocable"):
        if required not in fields:
            problems.append(f"{skill_dir.name}: frontmatter 缺 {required}（R2）")

    name = fields.get("name")
    if isinstance(name, str) and name:
        if not NAME_RE.match(name):
            problems.append(f"{skill_dir.name}: name 形态非法 {name!r}")
        if name != skill_dir.name:
            problems.append(f"{skill_dir.name}: name({name}) 与目录名不一致（部署前检查项）")
        if name in seen_names:
            problems.append(f"{skill_dir.name}: name 与 {seen_names[name]} 重复")
        else:
            seen_names[name] = skill_dir.name

    description = fields.get("description")
    if isinstance(description, str):
        if not description.strip():
            problems.append(f"{skill_dir.name}: description 为空")
        elif len(description) > 1024:
            problems.append(f"{skill_dir.name}: description 过长（{len(description)} > 1024）")

    # 相对路径引用存在性
    body = text.split("---", 2)[-1] if text.count("---") >= 2 else text
    for match in set(REF_PATH_RE.findall(body)):
        if (skill_dir / match).exists():
            continue
        # 允许引用仓库级资源：knowledge-base/、schemas/
        if (ROOT / match).exists() or match.startswith(("knowledge-base/", "schemas/")):
            continue
        problems.append(f"{skill_dir.name}: 引用路径不存在 → {match}")
    for match in set(LOCAL_REF_RE.findall(body)):
        if (skill_dir / match).resolve().exists():
            continue
        problems.append(f"{skill_dir.name}: 相对引用不存在 → {match}")

    for path in sorted(skill_dir.rglob("*")):
        if path.is_dir() or path.suffix not in {".md", ".py", ".sh", ".json", ".yaml", ".yml", ".txt"}:
            continue
        problems.extend(
            scan_text(
                path.read_text(encoding="utf-8", errors="replace"),
                f"{skill_dir.name}/{path.name}",
                executable=path.suffix in EXECUTABLE_SUFFIXES,
            )
        )

    for script in (skill_dir / "scripts").glob("*.py") if (skill_dir / "scripts").is_dir() else []:
        source = script.read_text(encoding="utf-8", errors="replace")
        if re.search(r"\brequests?\b|\burllib\b|socket\.", source):
            problems.append(f"{skill_dir.name}/{script.name}: 脚本含网络访问，需人工审核（部署前检查项）")
    return problems


def run(skills_dir: Path = SKILLS_DIR) -> tuple[int, list[str], bool]:
    """返回 (Skill 数, 问题列表, 是否为空目录)。"""
    if not skills_dir.exists():
        return 0, [f"skills 目录不存在: {skills_dir}"], False
    candidates = sorted(p for p in skills_dir.iterdir() if p.is_dir() and not p.name.startswith((".", "_")))
    if not candidates:
        return 0, [], True

    seen: dict[str, str] = {}
    problems: list[str] = []
    for skill_dir in candidates:
        problems.extend(check_skill_dir(skill_dir, seen))
    return len(candidates), problems, False


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    strict = "--strict" in argv  # CI 模式：skills 为空也返回失败

    count, problems, empty = run()
    if empty:
        print("SKIP: skills/ 下暂无 Skill（P3 阶段的正常状态）。未做加载检查。")
        if strict:
            print("  --strict 模式要求至少存在一个 Skill", file=sys.stderr)
            return 1
        return 0
    if problems:
        print(f"FAIL: {count} 个 Skill 中 {len(problems)} 项不合规", file=sys.stderr)
        for item in problems:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print(f"OK: {count} 个 Skill 的 frontmatter、命名、引用路径与凭证扫描均合规")
    print("  注意：本脚本不验证运行时行为。部署成功与否仍需 `openclaw skills list` 确认（R25）")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
