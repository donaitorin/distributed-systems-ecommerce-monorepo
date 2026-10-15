from pathlib import Path

import pytest
from check_comments import CHECKERS, check, main, source_files


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
