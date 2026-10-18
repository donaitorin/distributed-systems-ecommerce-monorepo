import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from check_comments import (
    CHECKERS,
    DEFAULT_ROOTS,
    GENERATED_FILES,
    TYPESCRIPT_SCANNER,
    Finding,
    ToolchainError,
    check,
    check_typescript,
    main,
    source_files,
)


def write(directory: Path, name: str, content: str) -> Path:
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def kinds(path: Path) -> list[tuple[int, str]]:
    return [(finding.line, finding.kind) for finding in check([path])]


def test_clean_code_has_no_findings(tmp_path: Path) -> None:
    path = write(
        tmp_path, "clean.py", "VALUE = '# not a comment'\n\n\ndef run() -> int:\n    return 1\n"
    )

    assert check([path]) == []


def test_a_line_comment_and_a_trailing_comment_are_found(tmp_path: Path) -> None:
    path = write(tmp_path, "commented.py", "# top\nVALUE = 1  # trailing\n")

    assert kinds(path) == [(1, "comment"), (2, "comment")]


@pytest.mark.parametrize(
    "line",
    [
        "import os  # noqa: F401",
        "value: int = 'x'  # type: ignore[assignment]",
        "value = 1  # type: ignore",
        "raise SystemExit  # pragma: no cover",
        "while value:  # pragma: no branch\n    break",
        "value = 1  # noqa",
        "value = 1  # pyright: ignore",
        "value = 1  # fmt: skip",
    ],
)
def test_tool_pragmas_are_allowed(tmp_path: Path, line: str) -> None:
    path = write(tmp_path, "pragma.py", f"value = 1\n{line}\n")

    assert check([path]) == []


def test_a_shebang_is_allowed_only_on_the_first_line(tmp_path: Path) -> None:
    allowed = write(tmp_path, "script.py", "#!/usr/bin/env python3\nVALUE = 1\n")
    misplaced = write(tmp_path, "late.py", "VALUE = 1\n#!/usr/bin/env python3\n")

    assert check([allowed]) == []
    assert kinds(misplaced) == [(2, "comment")]


def test_a_pragma_word_inside_a_longer_comment_is_still_a_comment(tmp_path: Path) -> None:
    path = write(tmp_path, "mixed.py", "value = 1  # explain why, then noqa\n")

    assert kinds(path) == [(1, "comment")]


def test_module_class_and_function_docstrings_are_found(tmp_path: Path) -> None:
    path = write(
        tmp_path,
        "docs.py",
        '"""module"""\n\n\nclass A:\n    """class"""\n\n    def run(self) -> None:\n'
        '        """method"""\n\n\nasync def go() -> None:\n    """async"""\n',
    )

    assert kinds(path) == [(1, "docstring"), (5, "docstring"), (8, "docstring"), (12, "docstring")]


def test_a_string_statement_that_is_not_first_is_not_a_docstring(tmp_path: Path) -> None:
    path = write(tmp_path, "later.py", "VALUE = 1\n'not a docstring'\n")

    assert check([path]) == []


def test_empty_bodies_and_empty_files_are_fine(tmp_path: Path) -> None:
    path = write(tmp_path, "empty.py", "")

    assert check([path]) == []


def test_ignored_directories_and_other_extensions_are_skipped(tmp_path: Path) -> None:
    write(tmp_path, ".venv/lib/x.py", "# ignored\n")
    write(tmp_path, "node_modules/x.py", "# ignored\n")
    write(tmp_path, "notes.txt", "# not python\n")
    kept = write(tmp_path, "pkg/a.py", "VALUE = 1\n")

    assert list(source_files([tmp_path])) == [kept]


def test_a_single_file_can_be_checked_directly(tmp_path: Path) -> None:
    path = write(tmp_path, "one.py", "# note\n")

    assert len(check([path])) == 1


def test_main_reports_findings_with_location_and_a_failing_exit_code(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write(tmp_path, "bad.py", "VALUE = 1  # why\n")

    code = main([str(path)])

    assert code == 1
    assert f"{path}:1: comment: # why" in capsys.readouterr().out


def test_main_succeeds_on_clean_files(tmp_path: Path) -> None:
    write(tmp_path, "good.py", "VALUE = 1\n")

    assert main([str(tmp_path)]) == 0


def test_checkers_are_registered_by_extension() -> None:
    assert ".py" in CHECKERS


TYPESCRIPT_TOOLCHAIN_AVAILABLE = (
    shutil.which("node") is not None
    and (TYPESCRIPT_SCANNER.parent.parent / "node_modules" / "typescript").exists()
)
requires_typescript = pytest.mark.skipif(
    not TYPESCRIPT_TOOLCHAIN_AVAILABLE,
    reason="run 'pnpm install' in frontend/ to enable the TypeScript checker tests",
)


def test_default_roots_include_the_frontend_and_the_scripts() -> None:
    assert {"backend", "frontend", "scripts"} <= set(DEFAULT_ROOTS)


def test_typescript_extensions_share_one_batch_checker() -> None:
    assert CHECKERS[".ts"] is CHECKERS[".tsx"] is check_typescript


def test_typescript_scanner_output_becomes_findings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = write(tmp_path, "a.ts", "export const a = 1;\n")
    calls: list[str] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(kwargs["input"])
        output = json.dumps([{"path": str(path), "line": 3, "text": "note"}])
        return subprocess.CompletedProcess(command, 0, output, "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert check([path, path]) == [Finding(path, 3, "comment", "note")]
    assert calls == [f"{path}\n{path}"]


def test_the_scanner_runs_once_for_all_typescript_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(tmp_path, "a.ts", "export const a = 1;\n")
    write(tmp_path, "b.tsx", "export const b = 1;\n")
    runs: list[int] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        runs.append(1)
        return subprocess.CompletedProcess(command, 0, "[]", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert check([tmp_path]) == []
    assert runs == [1]


def test_the_scanner_is_not_started_without_typescript_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(tmp_path, "a.py", "VALUE = 1\n")

    def fail(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("scanner must not run")

    monkeypatch.setattr(subprocess, "run", fail)

    assert check([tmp_path]) == []


def test_a_failing_scanner_is_a_toolchain_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = write(tmp_path, "a.ts", "export const a = 1;\n")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(command, 1, "", "Cannot find module"),
    )

    with pytest.raises(ToolchainError, match="pnpm install"):
        check([path])


def test_missing_node_is_a_toolchain_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = write(tmp_path, "a.ts", "export const a = 1;\n")
    monkeypatch.setattr(shutil, "which", lambda name: None)

    with pytest.raises(ToolchainError, match="node is required"):
        check([path])


def test_main_exits_with_two_when_the_toolchain_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write(tmp_path, "a.ts", "export const a = 1;\n")
    monkeypatch.setattr(shutil, "which", lambda name: None)

    assert main([str(path)]) == 2
    assert "node is required" in capsys.readouterr().err


def test_generated_next_env_declarations_are_skipped(tmp_path: Path) -> None:
    write(tmp_path, "next-env.d.ts", "// NOTE: generated\n")
    kept = write(tmp_path, "page.ts", "export const a = 1;\n")

    assert list(source_files([tmp_path])) == [kept]


@pytest.mark.parametrize("directory", [".next", ".turbo", "storybook-static", "coverage"])
def test_frontend_build_output_is_skipped(tmp_path: Path, directory: str) -> None:
    write(tmp_path, f"{directory}/generated.ts", "// generated\n")
    kept = write(tmp_path, "src/page.ts", "export const a = 1;\n")

    assert list(source_files([tmp_path])) == [kept]


@requires_typescript
@pytest.mark.parametrize(
    ("name", "source"),
    [
        ("string.ts", "const a = 'not // a comment';\nconst b = \"nor /* this */\";\n"),
        ("url.ts", "const a = 'https://example.com/path';\n"),
        (
            "template.ts",
            "const a = `// text ${1 + 1} /* still text */`;\nconst b = `${'x'}//${'y'}`;\n",
        ),
        ("regex.ts", "const a = /\\/\\//;\nconst b = /https?:\\/\\/[a-z]+/;\n"),
        ("jsx-text.tsx", "export const A = () => <p>// not a comment</p>;\n"),
        (
            "pragmas.ts",
            "// eslint-disable-next-line no-console\n"
            "/* eslint-disable no-console */\n"
            "// @ts-expect-error legacy typing gap\n"
            "const a: number = 'x';\n",
        ),
    ],
)
def test_real_scanner_ignores_comment_lookalikes_and_pragmas(
    tmp_path: Path, name: str, source: str
) -> None:
    assert check([write(tmp_path, name, source)]) == []


@requires_typescript
@pytest.mark.parametrize(
    ("name", "source", "line"),
    [
        ("line.ts", "const a = 1;\n// note\n", 2),
        ("block.ts", "/* note */\nconst a = 1;\n", 1),
        ("doc.ts", "const a = 1;\n/** doc */\nexport const b = 2;\n", 2),
        ("jsx.tsx", "export const A = () => (\n  <div>\n    {/* note */}\n  </div>\n);\n", 3),
        ("template-substitution.ts", "const a = `${1 /* note */}`;\n", 1),
        ("ts-expect-error.ts", "// @ts-expect-error\nconst a: number = 'x';\n", 1),
        ("ts-ignore.ts", "// @ts-ignore\nconst a: number = 'x';\n", 1),
    ],
)
def test_real_scanner_reports_real_comments(
    tmp_path: Path, name: str, source: str, line: int
) -> None:
    path = write(tmp_path, name, source)

    assert [(finding.path, finding.line) for finding in check([path])] == [(path, line)]


def test_generated_api_client_files_are_excluded_one_by_one() -> None:
    names = sorted(path.name for path in GENERATED_FILES)

    assert names == ["accounts.ts", "auth.ts", "cart.ts", "catalog.ts", "orders.ts", "payments.ts"]
    assert not set(source_files(list(GENERATED_FILES))) & GENERATED_FILES


def test_other_files_next_to_the_generated_ones_are_still_checked() -> None:
    generated_directory = next(iter(GENERATED_FILES)).parent
    sibling = generated_directory / "hand-written.ts"
    sibling.write_text("export const a = 1;\n", encoding="utf-8")
    try:
        assert sibling in set(source_files([generated_directory]))
    finally:
        sibling.unlink()
