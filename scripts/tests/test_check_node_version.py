from pathlib import Path

import pytest

import check_node_version as guard


@pytest.mark.parametrize(
    ("text", "major"),
    [("24.22.0", 24), ("v24.22.0\n", 24), ("22", 22), ("lts/*", None), ("", None)],
)
def test_the_major_is_read_from_a_version(text: str, major: int | None) -> None:
    assert guard.major_of(text) == major


def test_the_same_major_passes_whatever_the_minor() -> None:
    assert guard.check("24.22.0", "v24.12.0") is None


def test_another_major_names_both_versions_and_the_fix() -> None:
    message = guard.check("24.22.0", "v20.10.0")

    assert message is not None
    assert "v20.10.0 is active" in message
    assert "24.22.0" in message
    assert "nvm use" in message


def test_a_missing_node_is_explained() -> None:
    message = guard.check("24.22.0", None)

    assert message is not None
    assert "`node` was not found" in message


def test_an_nvmrc_that_is_not_a_version_is_reported() -> None:
    message = guard.check("lts/*", "v24.22.0")

    assert message is not None
    assert "does not hold a Node version" in message


def test_main_exits_zero_when_the_majors_match(tmp_path: Path) -> None:
    nvmrc = tmp_path / ".nvmrc"
    nvmrc.write_text("24.22.0\n")

    assert guard.main([str(nvmrc), "v24.1.0"]) == 0


def test_main_prints_the_problem_and_fails_when_they_differ(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    nvmrc = tmp_path / ".nvmrc"
    nvmrc.write_text("24.22.0\n")

    assert guard.main([str(nvmrc), "v20.10.0"]) == 1
    assert capsys.readouterr().err.startswith("error: Node v20.10.0 is active")


def test_the_repository_nvmrc_is_a_version() -> None:
    assert guard.major_of(guard.NVMRC.read_text()) is not None
