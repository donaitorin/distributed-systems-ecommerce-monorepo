import { ApiError, ApiNetworkError, readProblem } from "../src/problem";

function problemResponse(body: unknown, status = 422, headers: Record<string, string> = {}) {
  return new Response(typeof body === "string" ? body : JSON.stringify(body), {
    status,
    headers: { "content-type": "application/problem+json", ...headers },
  });
}

describe("readProblem", () => {
  it("returns an application/problem+json body as is", async () => {
    const body = { type: "about:blank", title: "Unprocessable Entity", status: 422, request_id: "r1" };

    expect(await readProblem(problemResponse(body))).toEqual(body);
  });

  it("keeps extension members such as field errors", async () => {
    const errors = [{ location: "body.price", message: "bad", type: "value_error" }];
    const problem = await readProblem(
      problemResponse({ type: "about:blank", title: "Validation", status: 422, errors }),
    );

    expect(problem.errors).toEqual(errors);
  });

  it("builds a problem from a plain text rate limit response", async () => {
    const response = new Response("Too Many Requests", {
      status: 429,
      statusText: "Too Many Requests",
      headers: { "content-type": "text/plain", "retry-after": "12" },
    });

    expect(await readProblem(response)).toEqual({
      type: "about:blank",
      title: "Too Many Requests",
      status: 429,
      detail: "Too Many Requests",
    });
  });

  it("falls back when the problem body is not valid JSON", async () => {
    const problem = await readProblem(problemResponse("<html>oops</html>", 502));

    expect(problem).toMatchObject({ status: 502, title: "HTTP 502", detail: "<html>oops</html>" });
  });

  it("falls back when the JSON is not a problem document", async () => {
    const problem = await readProblem(problemResponse({ message: "nope" }, 500));

    expect(problem.status).toBe(500);
    expect(problem.title).toBe("HTTP 500");
  });

  it("truncates long fallback details", async () => {
    const response = new Response("x".repeat(500), { status: 500 });

    expect((await readProblem(response)).detail).toHaveLength(200);
  });

  it("omits the detail for an empty body", async () => {
    const problem = await readProblem(new Response(null, { status: 503 }));

    expect(problem).toEqual({ type: "about:blank", title: "HTTP 503", status: 503 });
  });

  it("tolerates a body that cannot be read", async () => {
    const response = new Response("done", { status: 500 });
    await response.text();

    expect((await readProblem(response)).status).toBe(500);
  });
});

describe("ApiError", () => {
  const problem = { type: "about:blank", title: "Conflict", status: 409, detail: "SKU exists" };

  it("exposes the status, problem and a readable message", () => {
    const error = new ApiError(problem, new Response(null, { status: 409 }));

    expect(error).toBeInstanceOf(Error);
    expect(error.name).toBe("ApiError");
    expect(error.status).toBe(409);
    expect(error.message).toBe("Conflict: SKU exists");
  });

  it("uses the title alone when there is no detail", () => {
    const error = new ApiError({ ...problem, detail: undefined }, new Response(null));

    expect(error.message).toBe("Conflict");
  });

  it("prefers the request id from the body, then the header", () => {
    const fromBody = new ApiError({ ...problem, request_id: "body" }, new Response(null));
    const fromHeader = new ApiError(problem, new Response(null, { headers: { "x-request-id": "hdr" } }));

    expect(fromBody.requestId).toBe("body");
    expect(fromHeader.requestId).toBe("hdr");
    expect(new ApiError(problem, new Response(null)).requestId).toBeUndefined();
  });

  it("reads Retry-After in seconds", () => {
    const limited = new ApiError(problem, new Response(null, { headers: { "retry-after": "30" } }));

    expect(limited.retryAfterSeconds).toBe(30);
    expect(new ApiError(problem, new Response(null)).retryAfterSeconds).toBeUndefined();
    expect(
      new ApiError(problem, new Response(null, { headers: { "retry-after": "soon" } })).retryAfterSeconds,
    ).toBeUndefined();
  });

  it("lists field errors", () => {
    const errors = [{ location: "body.sku", message: "required", type: "missing" }];

    expect(new ApiError({ ...problem, errors }, new Response(null)).fieldErrors()).toEqual(errors);
    expect(new ApiError(problem, new Response(null)).fieldErrors()).toEqual([]);
  });
});

describe("ApiNetworkError", () => {
  it("keeps the original cause", () => {
    const cause = new TypeError("fetch failed");
    const error = new ApiNetworkError(cause);

    expect(error.cause).toBe(cause);
    expect(error.name).toBe("ApiNetworkError");
  });
});
