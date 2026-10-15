from typing import Any

from accounts.api.schemas import ProblemOut

DESCRIPTIONS = {
    401: "Missing, invalid or expired access token",
    403: "The token does not carry the admin role",
    404: "No such address on this account",
    409: "The account already has the maximum number of addresses",
    422: "Invalid request data",
}


def problem_responses(*codes: int) -> dict[int | str, dict[str, Any]]:
    return {code: {"model": ProblemOut, "description": DESCRIPTIONS[code]} for code in codes}
