import { ApiError } from "@ecommerce/api-client";
import { createAuthRuntime, type AuthRuntime } from "../src";
import {
  authorizationHeaders,
  authRuntime,
  getSession,
  registerAccount,
  requireSession,
  resetAuthRuntime,
  signIn,
  signOut,
} from "../src/next";
import { CONFIG, createTestKeys, jsonResponse, problemResponse, tokensBody } from "./support/tokens";

const cookieJar = new Map<string, string>();
const cookieWrites: { name: string; value: string; options: Record<string, unknown> }[] = [];
let requestHeaders = new Headers();

jest.mock("next/headers", () => ({
  cookies: () =>
    Promise.resolve({
      get: (name: string) => (cookieJar.has(name) ? { name, value: cookieJar.get(name) } : undefined),
      set: (name: string, value: string, options: Record<string, unknown>) => {
        cookieWrites.push({ name, value, options });
        cookieJar.set(name, value);
      },
    }),
  headers: () => Promise.resolve(requestHeaders),
}));

jest.mock("next/navigation", () => ({
  redirect: (path: string) => {
    throw new Error(`NEXT_REDIRECT ${path}`);
  },
}));

async function install(handler: (url: string, init: RequestInit) => Promise<Response>) {
  const keys = await createTestKeys();
  const fetchMock = jest.fn(handler);
  const runtime = createAuthRuntime(CONFIG, { fetch: fetchMock as unknown as typeof fetch, keySet: keys.keySet });
  resetAuthRuntime(runtime);
  return { keys, fetchMock, runtime };
}

beforeEach(() => {
  cookieJar.clear();
  cookieWrites.length = 0;
  requestHeaders = new Headers({ "x-forwarded-for": "203.0.113.9" });
});

afterEach(() => {
  resetAuthRuntime();
});

describe("getSession", () => {
  it("is null without a cookie", async () => {
    await install(() => Promise.reject(new Error("unused")));

    expect(await getSession()).toBeNull();
  });

  it("reads the verified session from the access cookie", async () => {
    const { keys } = await install(() => Promise.reject(new Error("unused")));
    cookieJar.set("ecommerce_access", await keys.sign({ role: "admin" }));

    expect(await getSession()).toMatchObject({ userId: "user-1", role: "admin" });
  });

  it("is null for an invalid cookie", async () => {
    await install(() => Promise.reject(new Error("unused")));
    cookieJar.set("ecommerce_access", "garbage");

    expect(await getSession()).toBeNull();
  });

  it("is null, not a crash, when the key set is unreachable", async () => {
    const keys = await createTestKeys();
    const runtime = createAuthRuntime(CONFIG, {
      fetch: jest.fn() as unknown as typeof fetch,
      keySet: () => Promise.reject(new TypeError("offline")),
    });
    resetAuthRuntime(runtime);
    cookieJar.set("ecommerce_access", await keys.sign());

    expect(await getSession()).toBeNull();
  });

  it("rethrows unexpected verifier errors", async () => {
    const { runtime } = await install(() => Promise.reject(new Error("unused")));
    resetAuthRuntime({ ...runtime, verify: () => Promise.reject(new Error("bug")) } satisfies AuthRuntime);
    cookieJar.set("ecommerce_access", "x");

    await expect(getSession()).rejects.toThrow("bug");
  });
});

describe("requireSession", () => {
  it("returns the session", async () => {
    const { keys } = await install(() => Promise.reject(new Error("unused")));
    cookieJar.set("ecommerce_access", await keys.sign({ role: "admin" }));

    await expect(requireSession({ loginPath: "/login", role: "admin" })).resolves.toMatchObject({ role: "admin" });
  });

  it("redirects an anonymous visitor", async () => {
    await install(() => Promise.reject(new Error("unused")));

    await expect(requireSession({ loginPath: "/login" })).rejects.toThrow("NEXT_REDIRECT /login");
  });

  it("redirects a user with the wrong role", async () => {
    const { keys } = await install(() => Promise.reject(new Error("unused")));
    cookieJar.set("ecommerce_access", await keys.sign({ role: "customer" }));

    await expect(requireSession({ loginPath: "/login", role: "admin" })).rejects.toThrow("NEXT_REDIRECT /login");
  });
});

describe("authorizationHeaders", () => {
  it("carries the bearer token and the visitor's address", async () => {
    await install(() => Promise.reject(new Error("unused")));
    cookieJar.set("ecommerce_access", "token-1");

    expect(await authorizationHeaders()).toEqual({
      authorization: "Bearer token-1",
      "x-forwarded-for": "203.0.113.9",
    });
  });

  it("omits what is not there", async () => {
    await install(() => Promise.reject(new Error("unused")));
    requestHeaders = new Headers();

    expect(await authorizationHeaders()).toEqual({});
  });
});

describe("signIn", () => {
  it("reports the retry time of a rate limited login", async () => {
    await install(() =>
      Promise.resolve(new Response("Too Many Requests", { status: 429, headers: { "retry-after": "42" } })),
    );

    const result = await signIn({ email: "ada@example.com", password: "pw" });

    expect(result).toMatchObject({ ok: false, problem: { status: 429 }, retryAfterSeconds: 42 });
  });

  it("logs in through the gateway with the visitor's address and stores both tokens in httpOnly cookies", async () => {
    const { keys, fetchMock } = await install(() => Promise.resolve(jsonResponse({})));
    const access = await keys.sign({ role: "customer" });
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse(tokensBody(access, "r1"))));

    const result = await signIn({ email: "ada@example.com", password: "pw" });

    expect(result).toMatchObject({ ok: true, session: { role: "customer" } });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://gateway.test/api/v1/auth/login");
    expect((init.headers as Record<string, string>)["x-forwarded-for"]).toBe("203.0.113.9");
    expect(cookieWrites.map((write) => write.name)).toEqual(["ecommerce_access", "ecommerce_refresh"]);
    expect(cookieWrites.every((write) => write.options.httpOnly === true && write.options.sameSite === "lax")).toBe(true);
  });

  it("returns the problem for bad credentials and sets no cookie", async () => {
    await install(() => Promise.resolve(problemResponse(401, "Invalid credentials")));

    const result = await signIn({ email: "ada@example.com", password: "nope" });

    expect(result).toMatchObject({ ok: false, problem: { status: 401, title: "Invalid credentials" } });
    expect(cookieWrites).toEqual([]);
  });

  it("returns the 429 problem of the gateway rate limit", async () => {
    await install(() =>
      Promise.resolve(new Response("Too Many Requests", { status: 429, headers: { "content-type": "text/plain" } })),
    );

    expect(await signIn({ email: "a@example.com", password: "x" })).toMatchObject({
      ok: false,
      problem: { status: 429 },
    });
  });

  it("does not set cookies when the issued token cannot be verified", async () => {
    await install(() => Promise.resolve(jsonResponse(tokensBody("garbage", "r1"))));

    await expect(signIn({ email: "a@example.com", password: "pw" })).rejects.toThrow("could not be verified");
    expect(cookieWrites).toEqual([]);
  });

  it("rethrows network failures", async () => {
    await install(() => Promise.reject(new TypeError("fetch failed")));

    await expect(signIn({ email: "a@example.com", password: "pw" })).rejects.toThrow("could not be reached");
  });
});

describe("registerAccount", () => {
  it("registers through the gateway with the visitor's address", async () => {
    const { fetchMock } = await install(() =>
      Promise.resolve(jsonResponse({ id: "1", email: "ada@example.com", role: "customer" }, 201)),
    );

    const result = await registerAccount({ email: "ada@example.com", password: "long enough pw" });

    expect(result).toEqual({ ok: true, user: { id: "1", email: "ada@example.com", role: "customer" } });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://gateway.test/api/v1/auth/register");
    expect((init.headers as Record<string, string>)["x-forwarded-for"]).toBe("203.0.113.9");
  });

  it("returns the problem for a taken email", async () => {
    await install(() => Promise.resolve(problemResponse(409, "Conflict")));

    expect(await registerAccount({ email: "ada@example.com", password: "long enough pw" })).toMatchObject({
      ok: false,
      problem: { status: 409 },
    });
  });

  it("passes the retry time of a rate limit on", async () => {
    await install(() =>
      Promise.resolve(
        new Response("Too Many Requests", { status: 429, headers: { "retry-after": "17", "content-type": "text/plain" } }),
      ),
    );

    expect(await registerAccount({ email: "ada@example.com", password: "long enough pw" })).toMatchObject({
      ok: false,
      problem: { status: 429 },
      retryAfterSeconds: 17,
    });
  });

  it("rethrows unexpected failures", async () => {
    await install(() => Promise.reject(new TypeError("fetch failed")));

    await expect(registerAccount({ email: "a@example.com", password: "pw" })).rejects.toThrow("could not be reached");
  });
});

describe("signOut", () => {
  it("revokes the refresh token and clears both cookies", async () => {
    const { fetchMock } = await install(() => Promise.resolve(new Response(null, { status: 204 })));
    cookieJar.set("ecommerce_refresh", "r1");

    await signOut();

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://gateway.test/api/v1/auth/logout");
    expect(JSON.parse(init.body as string)).toEqual({ refresh_token: "r1" });
    expect(cookieWrites.map((write) => [write.name, write.value, write.options.maxAge])).toEqual([
      ["ecommerce_access", "", 0],
      ["ecommerce_refresh", "", 0],
    ]);
  });

  it("clears the cookies even when the API is unreachable", async () => {
    await install(() => Promise.reject(new TypeError("fetch failed")));
    cookieJar.set("ecommerce_refresh", "r1");

    await expect(signOut()).rejects.toBeInstanceOf(Error);

    expect(cookieWrites.map((write) => write.value)).toEqual(["", ""]);
  });

  it("only clears cookies when there is no refresh token", async () => {
    const { fetchMock } = await install(() => Promise.reject(new Error("unused")));

    await signOut();

    expect(fetchMock).not.toHaveBeenCalled();
    expect(cookieWrites).toHaveLength(2);
  });
});

describe("authRuntime", () => {
  const original = process.env.API_BASE_URL;

  afterEach(() => {
    if (original === undefined) {
      delete process.env.API_BASE_URL;
    } else {
      process.env.API_BASE_URL = original;
    }
    resetAuthRuntime();
  });

  it("is built once from the environment", () => {
    process.env.API_BASE_URL = "http://gateway.env";

    const first = authRuntime();

    expect(first.config.apiBaseUrl).toBe("http://gateway.env");
    expect(authRuntime()).toBe(first);
  });

  it("fails fast when the environment is incomplete", () => {
    delete process.env.API_BASE_URL;

    expect(() => authRuntime()).toThrow("API_BASE_URL is required");
  });

  it("exposes an ApiError type for callers", () => {
    expect(new ApiError({ type: "x", title: "t", status: 400 }, new Response()).status).toBe(400);
  });
});
