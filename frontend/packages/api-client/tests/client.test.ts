import { ApiError, ApiNetworkError, buildPath, buildQuery, createApiClient } from "../src";
import type { GatewayPaths } from "../src";

type FetchMock = jest.Mock<Promise<Response>, [string, RequestInit]>;

function jsonResponse(body: unknown, status = 200, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", ...headers },
  });
}

function mockFetch(implementation: () => Promise<Response>): FetchMock {
  return jest.fn<Promise<Response>, [string, RequestInit]>(implementation);
}

function setup(response: Response | (() => Promise<Response>)) {
  const fetchMock = mockFetch(() => (typeof response === "function" ? response() : Promise.resolve(response)));
  const client = createApiClient<GatewayPaths>({
    baseUrl: "http://gateway.test/",
    fetch: fetchMock as unknown as typeof fetch,
  });
  return { client, fetchMock };
}

function lastCall(fetchMock: FetchMock) {
  const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
  return { url, init, headers: init.headers as Record<string, string> };
}

describe("buildQuery", () => {
  it("skips null and undefined and encodes values", () => {
    expect(buildQuery({ q: "running shoes", min_price: undefined, category: null })).toBe(
      "?q=running+shoes",
    );
  });

  it("repeats array values and stringifies booleans", () => {
    expect(buildQuery({ tag: ["a", "b"], in_stock: true })).toBe("?tag=a&tag=b&in_stock=true");
  });

  it("returns an empty string without parameters", () => {
    expect(buildQuery(undefined)).toBe("");
    expect(buildQuery({})).toBe("");
  });
});

describe("buildPath", () => {
  it("fills and encodes path parameters", () => {
    expect(buildPath("/api/v1/products/{sku}", { sku: "A B/1" })).toBe("/api/v1/products/A%20B%2F1");
  });

  it("returns a path without parameters unchanged", () => {
    expect(buildPath("/api/v1/products", undefined)).toBe("/api/v1/products");
  });

  it("rejects a missing parameter", () => {
    expect(() => buildPath("/api/v1/products/{sku}", {})).toThrow('Missing path parameter "sku"');
  });
});

describe("createApiClient", () => {
  it("sends a typed GET with a query string and returns the JSON body", async () => {
    const page = { items: [], next_cursor: null, prev_cursor: null, total: 0, total_exact: true };
    const { client, fetchMock } = setup(jsonResponse(page));

    const result = await client.get("/api/v1/products", { query: { q: "shoes", limit: 12 } });

    const { url, init, headers } = lastCall(fetchMock);
    expect(url).toBe("http://gateway.test/api/v1/products?q=shoes&limit=12");
    expect(init.method).toBe("GET");
    expect(headers.accept).toContain("application/problem+json");
    expect(result.data).toEqual(page);
    expect(result.response.status).toBe(200);
  });

  it("sends a JSON body with a content type", async () => {
    const { client, fetchMock } = setup(
      jsonResponse({ id: "1", email: "a@example.com", role: "customer" }, 201),
    );

    await client.post("/api/v1/auth/register", { body: { email: "a@example.com", password: "long enough pw" } });

    const { init, headers } = lastCall(fetchMock);
    expect(init.method).toBe("POST");
    expect(headers["content-type"]).toBe("application/json");
    expect(init.body).toBe('{"email":"a@example.com","password":"long enough pw"}');
  });

  it("passes FormData through without forcing a content type", async () => {
    const product = { sku: "A" };
    const { client, fetchMock } = setup(jsonResponse(product));
    const form = new FormData();
    form.append("file", new Blob(["x"]), "a.png");

    await client.put("/api/v1/products/{sku}/image", {
      params: { sku: "A" },
      body: form,
      headers: { "if-match": '"1"' },
    });

    const { url, init, headers } = lastCall(fetchMock);
    expect(url).toBe("http://gateway.test/api/v1/products/A/image");
    expect(init.body).toBe(form);
    expect(headers["content-type"]).toBeUndefined();
    expect(headers["if-match"]).toBe('"1"');
  });

  it("returns undefined data for 204", async () => {
    const { client } = setup(new Response(null, { status: 204 }));

    const result = await client.post("/api/v1/auth/logout", { body: { refresh_token: "x" } });

    expect(result.data).toBeUndefined();
  });

  it("applies default headers from the client", async () => {
    const fetchMock = mockFetch(() => Promise.resolve(jsonResponse({})));
    const client = createApiClient<GatewayPaths>({
      baseUrl: "http://gateway.test",
      fetch: fetchMock as unknown as typeof fetch,
      headers: () => Promise.resolve({ authorization: "Bearer token", "x-forwarded-for": "203.0.113.9" }),
    });

    await client.get("/api/v1/accounts/me");

    expect(lastCall(fetchMock).headers).toMatchObject({
      authorization: "Bearer token",
      "x-forwarded-for": "203.0.113.9",
    });
  });

  it("lets per-request headers override the defaults", async () => {
    const fetchMock = mockFetch(() => Promise.resolve(jsonResponse({})));
    const client = createApiClient<GatewayPaths>({
      baseUrl: "http://gateway.test",
      fetch: fetchMock as unknown as typeof fetch,
      headers: () => ({ authorization: "Bearer one" }),
    });

    await client.get("/api/v1/accounts/me", { headers: { authorization: "Bearer two" } });

    expect(lastCall(fetchMock).headers.authorization).toBe("Bearer two");
  });

  it("throws ApiError with the problem for a problem+json response", async () => {
    const { client } = setup(
      new Response(
        JSON.stringify({ type: "about:blank", title: "Conflict", status: 409, detail: "SKU exists" }),
        { status: 409, headers: { "content-type": "application/problem+json" } },
      ),
    );

    const failure = await client
      .post("/api/v1/products", { body: { sku: "A", name: "n", price: "1.00", stock: 1 } })
      .catch((error: unknown) => error);

    expect(failure).toBeInstanceOf(ApiError);
    expect((failure as ApiError).status).toBe(409);
    expect((failure as ApiError).problem.detail).toBe("SKU exists");
  });

  it("throws ApiError for a plain text 429 from the gateway", async () => {
    const { client } = setup(
      new Response("Too Many Requests", {
        status: 429,
        headers: { "content-type": "text/plain", "retry-after": "7" },
      }),
    );

    const failure = (await client
      .post("/api/v1/auth/login", { body: { email: "a@example.com", password: "x" } })
      .catch((error: unknown) => error)) as ApiError;

    expect(failure.status).toBe(429);
    expect(failure.retryAfterSeconds).toBe(7);
  });

  it("wraps connection failures in ApiNetworkError", async () => {
    const { client } = setup(() => Promise.reject(new TypeError("fetch failed")));

    await expect(client.get("/api/v1/products")).rejects.toBeInstanceOf(ApiNetworkError);
  });

  it("rethrows the caller's own abort", async () => {
    const controller = new AbortController();
    const { client } = setup(() => {
      controller.abort();
      return Promise.reject(new DOMException("aborted", "AbortError"));
    });

    await expect(client.get("/api/v1/products", { signal: controller.signal })).rejects.toMatchObject({
      name: "AbortError",
    });
  });

  it("passes a timeout signal to fetch", async () => {
    const { client, fetchMock } = setup(jsonResponse({}));

    await client.get("/api/v1/products", { timeoutMs: 50 });

    expect(lastCall(fetchMock).init.signal).toBeInstanceOf(AbortSignal);
  });

  it("aborts when the timeout elapses", async () => {
    const fetchMock = jest.fn(
      (_url: string, init: RequestInit) =>
        new Promise<Response>((_resolve, reject) => {
          init.signal?.addEventListener("abort", () => {
            reject(new DOMException("timed out", "TimeoutError"));
          });
        }),
    );
    const client = createApiClient<GatewayPaths>({
      baseUrl: "http://gateway.test",
      fetch: fetchMock as unknown as typeof fetch,
      timeoutMs: 10,
    });

    await expect(client.get("/api/v1/products")).rejects.toBeInstanceOf(ApiNetworkError);
  });

  it("uses the global fetch when none is injected", async () => {
    const original = globalThis.fetch;
    globalThis.fetch = jest.fn(() => Promise.resolve(jsonResponse({ ok: true })));
    try {
      const client = createApiClient<GatewayPaths>({ baseUrl: "http://gateway.test" });

      const result = await client.get("/api/v1/accounts/me");

      expect(result.data).toEqual({ ok: true });
    } finally {
      globalThis.fetch = original;
    }
  });

  it("requires path parameters at runtime", async () => {
    const { client } = setup(jsonResponse({}));

    await expect(
      client.get("/api/v1/products/{sku}", { params: {} as { sku: string } }),
    ).rejects.toThrow("Missing path parameter");
  });
});

describe("compile time contracts", () => {
  it("rejects calls that do not match the OpenAPI document", () => {
    const { client } = setup(jsonResponse({}));

    const rejected = [
      // @ts-expect-error unknown path
      () => client.get("/api/v1/nope"),
      // @ts-expect-error GET is not defined for the login path
      () => client.get("/api/v1/auth/login"),
      // @ts-expect-error path parameters are required
      () => client.get("/api/v1/products/{sku}"),
      // @ts-expect-error unknown query parameter
      () => client.get("/api/v1/products", { query: { nope: 1 } }),
      // @ts-expect-error body is required for login
      () => client.post("/api/v1/auth/login"),
      // @ts-expect-error password must be a string
      () => client.post("/api/v1/auth/login", { body: { email: "a@example.com", password: 1 } }),
    ];

    expect(rejected).toHaveLength(6);
  });

  it("infers the response body", async () => {
    const { client } = setup(jsonResponse({ access_token: "a", refresh_token: "r", token_type: "bearer", expires_in: 900 }));

    const { data } = await client.post("/api/v1/auth/login", {
      body: { email: "a@example.com", password: "pw" },
    });
    const token: string = data.access_token;

    expect(token).toBe("a");
  });
});
