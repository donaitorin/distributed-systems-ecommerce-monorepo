import xml.etree.ElementTree as ElementTree
from pathlib import Path

import check_package_coverage as guard
import pytest


def report(*classes: tuple[str, int, int, tuple[int, int]]) -> ElementTree.Element:
    body = ""
    for filename, lines, covered, (branches_covered, branches) in classes:
        rows = "".join(
            f'<line number="{number}" hits="{1 if number <= covered else 0}"/>'
            for number in range(1, lines + 1)
        )
        if branches:
            rows += (
                f'<line number="999" hits="1" branch="true" '
                f'condition-coverage="50% ({branches_covered}/{branches})"/>'
            )
        body += f'<class filename="{filename}"><lines>{rows}</lines></class>'
    return ElementTree.fromstring(f"<coverage><packages><package>{body}</package></packages></coverage>")


@pytest.mark.parametrize(
    ("filename", "package"),
    [
        ("messaging/src/ecommerce_messaging/consumer.py", "libs/messaging"),
        ("auth/src/ecommerce_auth/jwks.py", "libs/auth"),
        ("auth/src/auth/api/users.py", "services/auth"),
        ("cart/migrations/versions/0001_x.py", "services/cart"),
        ("dump_openapi.py", None),
        ("orders/alembic.ini", None),
    ],
)
def test_a_file_belongs_to_a_lib_or_a_service(filename: str, package: str | None) -> None:
    assert guard.package_of(filename) == package


def test_a_lib_and_a_service_with_the_same_directory_name_are_kept_apart() -> None:
    document = report(
        ("auth/src/ecommerce_auth/a.py", 10, 10, (0, 0)),
        ("auth/src/auth/b.py", 10, 5, (0, 0)),
    )

    totals = guard.totals_by_package(document)

    assert totals["libs/auth"].percent == 100.0
    assert totals["services/auth"].percent == 50.0


def test_branches_count_like_coverage_py_does() -> None:
    document = report(("cart/src/cart/x.py", 8, 8, (1, 2)))

    totals = guard.totals_by_package(document)["services/cart"]

    assert (totals.lines, totals.lines_covered, totals.branches, totals.branches_covered) == (
        9,
        9,
        2,
        1,
    )
    assert totals.percent == pytest.approx(100 * 10 / 11)


def test_every_package_at_or_above_the_threshold_passes() -> None:
    document = report(
        ("cart/src/cart/x.py", 100, 85, (0, 0)),
        ("web/src/ecommerce_web/y.py", 10, 10, (0, 0)),
    )

    lines, failures = guard.check(document)

    assert failures == []
    assert [line.split()[0] for line in lines] == ["ok", "ok"]


def test_a_package_below_the_threshold_fails_even_when_the_total_is_high() -> None:
    document = report(
        ("cart/src/cart/x.py", 100, 84, (0, 0)),
        ("orders/src/orders/big.py", 5000, 5000, (0, 0)),
    )

    lines, failures = guard.check(document)

    assert failures == ["services/cart is at 84.00%, below 85%"]
    assert any(line.startswith("FAIL services/cart") for line in lines)


def test_a_report_without_libs_or_services_fails() -> None:
    _, failures = guard.check(report(("dump_openapi.py", 5, 5, (0, 0))))

    assert failures == ["no libs or services found in the coverage report"]


def test_main_reports_a_missing_file(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    assert guard.main([str(tmp_path / "missing.xml")]) == 2
    assert "not found" in capsys.readouterr().err


def test_main_exit_codes_follow_the_check(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    good = tmp_path / "good.xml"
    good.write_text('<coverage><class filename="cart/src/cart/x.py"><lines><line number="1" hits="1"/></lines></class></coverage>')
    bad = tmp_path / "bad.xml"
    bad.write_text('<coverage><class filename="cart/src/cart/x.py"><lines><line number="1" hits="0"/></lines></class></coverage>')

    assert guard.main([str(good)]) == 0
    assert guard.main([str(bad)]) == 1
    assert "below 85%" in capsys.readouterr().err
