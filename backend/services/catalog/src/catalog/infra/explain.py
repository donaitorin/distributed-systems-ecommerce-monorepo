import json
from typing import Any

from sqlalchemy import Executable
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.compiler import SQLCompiler
from sqlalchemy.sql.expression import ClauseElement


class ExplainJson(Executable, ClauseElement):
    inherit_cache = False

    def __init__(self, statement: ClauseElement) -> None:
        self.statement = statement


@compiles(ExplainJson, "postgresql")
def compile_explain_json(element: ExplainJson, compiler: SQLCompiler, **kw: Any) -> str:
    return "EXPLAIN (FORMAT JSON) " + compiler.process(element.statement, **kw)


def parse_plan(raw: object) -> dict[str, Any]:
    document: Any = json.loads(raw) if isinstance(raw, str) else raw
    plan: dict[str, Any] = document[0]["Plan"]
    return plan
