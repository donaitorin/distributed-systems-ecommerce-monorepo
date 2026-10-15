import ast
import io
import re
import sys
import tokenize
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOTS = ("backend",)
IGNORED_DIRECTORIES = frozenset(
    {
        ".venv",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        "__pycache__",
        "htmlcov",
        "node_modules",
    }
)
PYTHON_PRAGMA = re.compile(
    r"#\s*(noqa\b|type:\s*ignore\b|pragma:\s*no\s+(cover|branch)\b|pyright:|mypy:|fmt:\s*(off|on|skip)\b)"
)
SHEBANG = re.compile(r"#!")


@dataclass(frozen=True, slots=True)
class Finding:
    path: Path
    line: int
    kind: str
    text: str

    def render(self) -> str:
        return f"{self.path}:{self.line}: {self.kind}: {self.text}"


def python_comments(source: str) -> Iterable[tuple[int, str]]:
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type != tokenize.COMMENT:
            continue
        line, column = token.start
        if line == 1 and column == 0 and SHEBANG.match(token.string):
            continue
        if PYTHON_PRAGMA.match(token.string):
            continue
        yield line, token.string


def python_docstrings(source: str) -> Iterable[tuple[int, str]]:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        first = node.body[0] if node.body else None
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            yield (
                first.lineno,
                first.value.value.strip().splitlines()[0] if first.value.value.strip() else "",
            )


def check_python(path: Path) -> list[Finding]:
    source = path.read_text(encoding="utf-8")
    comments = [Finding(path, line, "comment", text) for line, text in python_comments(source)]
    docstrings = [
        Finding(path, line, "docstring", text) for line, text in python_docstrings(source)
    ]
    return sorted(comments + docstrings, key=lambda finding: finding.line)


CHECKERS: dict[str, Callable[[Path], list[Finding]]] = {
    ".py": check_python,
}


def source_files(roots: Sequence[Path]) -> Iterable[Path]:
    for root in roots:
        candidates = [root] if root.is_file() else sorted(root.rglob("*"))
        for path in candidates:
            if not path.is_file() or path.suffix not in CHECKERS:
                continue
            if IGNORED_DIRECTORIES.intersection(path.parts):
                continue
            yield path


def check(roots: Sequence[Path]) -> list[Finding]:
    findings: list[Finding] = []
    for path in source_files(roots):
        findings.extend(CHECKERS[path.suffix](path))
    return findings


def main(argv: Sequence[str]) -> int:
    roots = [Path(arg) for arg in argv] or [REPO_ROOT / name for name in DEFAULT_ROOTS]
    findings = check(roots)
    for finding in findings:
        sys.stdout.write(finding.render() + "\n")
    if findings:
        sys.stderr.write(f"{len(findings)} comment(s) or docstring(s) found\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
