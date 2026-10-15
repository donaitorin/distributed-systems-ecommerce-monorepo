from typing import Any

from auth.api.schemas import ProblemOut

DESCRIPTIONS = {
    401: "Invalid credentials or refresh token",
    403: "The token does not carry the admin role",
    404: "No user with that id",
    409: "The email is already registered, or an admin tried to change their own role",
    422: "Invalid request data",
}


def problem_responses(*codes: int) -> dict[int | str, dict[str, Any]]:
    return {code: {"model": ProblemOut, "description": DESCRIPTIONS[code]} for code in codes}
