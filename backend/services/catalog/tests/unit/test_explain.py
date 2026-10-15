from catalog.infra.explain import parse_plan


def test_the_plan_is_read_from_a_json_string() -> None:
    assert parse_plan('[{"Plan": {"Node Type": "Seq Scan", "Plan Rows": 7}}]') == {
        "Node Type": "Seq Scan",
        "Plan Rows": 7,
    }


def test_the_plan_is_read_from_an_already_decoded_document() -> None:
    assert parse_plan([{"Plan": {"Plan Rows": 3}}]) == {"Plan Rows": 3}
