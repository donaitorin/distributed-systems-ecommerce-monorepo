from typing import Any

from cart.api.schemas import ProblemOut

DESCRIPTIONS = {
    401: "Missing, invalid or expired access token",
    404: "Unknown or retired product",
    409: "The cart is full or the accepted price is not the current price",
    422: "Invalid request data",
    503: "The cart store or the catalog is unavailable",
}


def problem_responses(*codes: int) -> dict[int | str, dict[str, Any]]:
    return {code: {"model": ProblemOut, "description": DESCRIPTIONS[code]} for code in codes}
