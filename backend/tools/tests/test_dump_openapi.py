import json
from pathlib import Path

import pytest
from dump_openapi import SERVICES, main, render

COMMITTED_SPECS = (
    Path(__file__).resolve().parents[3] / "frontend" / "packages" / "api-client" / "openapi"
)


def test_every_service_is_dumped_as_an_openapi_document(tmp_path: Path) -> None:
    assert main([str(tmp_path)]) == 0

    for name in SERVICES:
        document = json.loads((tmp_path / f"{name}.json").read_text(encoding="utf-8"))
        assert document["openapi"].startswith("3.")
        assert document["info"]["title"] == name
        assert document["paths"]


def test_the_output_directory_is_created(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "openapi"

    assert main([str(target)]) == 0
    assert sorted(path.name for path in target.iterdir()) == sorted(f"{n}.json" for n in SERVICES)


def test_rendering_is_deterministic() -> None:
    first = {name: render(build()) for name, build in SERVICES.items()}
    second = {name: render(build()) for name, build in SERVICES.items()}

    assert first == second


def test_rendered_files_end_with_a_newline_and_have_sorted_keys(tmp_path: Path) -> None:
    main([str(tmp_path)])
    text = (tmp_path / "auth.json").read_text(encoding="utf-8")

    assert text.endswith("}\n")
    document = json.loads(text)
    assert list(document) == sorted(document)


def test_the_gateway_paths_are_exposed() -> None:
    paths = {name: set(json.loads(render(build()))["paths"]) for name, build in SERVICES.items()}

    assert "/api/v1/auth/login" in paths["auth"]
    assert "/api/v1/products" in paths["catalog"]
    assert "/api/v1/accounts/me" in paths["accounts"]


@pytest.mark.parametrize("arguments", [[], ["a", "b"]])
def test_wrong_arguments_are_a_usage_error(
    arguments: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(arguments) == 2
    assert "usage" in capsys.readouterr().err


@pytest.mark.parametrize("name", list(SERVICES))
def test_the_committed_specs_match_the_code(name: str) -> None:
    committed = (COMMITTED_SPECS / f"{name}.json").read_text(encoding="utf-8")

    assert committed == render(SERVICES[name]()), (
        "OpenAPI spec is stale: run 'make openapi' and commit the result"
    )
