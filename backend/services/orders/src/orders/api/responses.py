from typing import Any

from orders.api.schemas import ProblemOut

DESCRIPTIONS = {
    400: "The Idempotency-Key header is missing or malformed",
    401: "Missing, invalid or expired access token",
    403: "The token does not carry the admin role",
    404: "No such order",
    422: "Invalid request data, or an idempotency key reused with a different body",
}


def problem_responses(*codes: int) -> dict[int | str, dict[str, Any]]:
    return {code: {"model": ProblemOut, "description": DESCRIPTIONS[code]} for code in codes}
