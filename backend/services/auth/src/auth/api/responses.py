from typing import Any

from auth.api.schemas import ProblemOut

DESCRIPTIONS = {
    401: "Invalid credentials or refresh token",
    409: "The email is already registered",
    422: "Invalid request data",
}


def problem_responses(*codes: int) -> dict[int | str, dict[str, Any]]:
    return {code: {"model": ProblemOut, "description": DESCRIPTIONS[code]} for code in codes}
