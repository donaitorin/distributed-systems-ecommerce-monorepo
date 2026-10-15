from typing import Any

from catalog.api.schemas import ProblemOut

DESCRIPTIONS = {
    401: "Missing or invalid access token",
    403: "The token does not carry the admin role",
    404: "Unknown or deleted SKU",
    409: "Conflict with an existing resource",
    412: "If-Match does not match the current version",
    422: "Invalid request data",
    428: "If-Match header is required",
    503: "The search exceeded its time limit; retry after the Retry-After delay",
}


def problem_responses(*codes: int) -> dict[int | str, dict[str, Any]]:
    return {code: {"model": ProblemOut, "description": DESCRIPTIONS[code]} for code in codes}
