/**
 * @jest-environment node
 */
import { ApiError, ApiNetworkError } from "@ecommerce/api-client";
import { failureFromError, failureFromProblem, failureFromResponse, isSessionFailure } from "../src";

function problem(status: number, title: string, extra: Record<string, unknown> = {}, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify({ type: "about:blank", title, status, ...extra }), {
    status,
    headers: { "content-type": "application/problem+json", ...headers },
  });
}

describe("failures", () => {
  it("reads body and query field errors and keeps the first per field", () => {
    const failure = failureFromProblem(
      {
        type: "about:blank",
        title: "Validation failed",
        status: 422,
        detail: "bad",
        errors: [
          { location: "body.price", message: "first", type: "a" },
          { location: "body.price", message: "second", type: "a" },
          { location: "query.min_price", message: "q", type: "a" },
          { location: "header.if-match", message: "no", type: "a" },
        ],
      },
      7,
    );

    expect(failure).toEqual({
      ok: false,
      status: 422,
      title: "Validation failed",
      detail: "bad",
      fieldErrors: { price: "first", min_price: "q" },
      retryAfterSeconds: 7,
    });
  });

  it("converts API and network errors and rethrows the rest", () => {
    const response = problem(503, "Down", {}, { "retry-after": "3" });
    const apiError = new ApiError({ type: "about:blank", title: "Down", status: 503 }, response);

    expect(failureFromError(apiError)).toMatchObject({ status: 503, retryAfterSeconds: 3 });
    expect(failureFromError(new ApiNetworkError(new Error("x")))).toMatchObject({ status: null });
    expect(() => failureFromError(new Error("bug"))).toThrow("bug");
  });

  it("reads a failed response, with or without Retry-After", async () => {
    expect(await failureFromResponse(problem(413, "Too large"))).toMatchObject({ status: 413 });
    expect(await failureFromResponse(problem(503, "Down", {}, { "retry-after": "9" }))).toMatchObject({
      retryAfterSeconds: 9,
    });
    expect(await failureFromResponse(new Response("Bad gateway", { status: 502 }))).toMatchObject({ status: 502 });
  });

  it("recognises session failures", () => {
    expect(isSessionFailure({ ok: false, status: 401, title: "", fieldErrors: {} })).toBe(true);
    expect(isSessionFailure({ ok: false, status: 403, title: "", fieldErrors: {} })).toBe(true);
    expect(isSessionFailure({ ok: false, status: 404, title: "", fieldErrors: {} })).toBe(false);
  });
});
