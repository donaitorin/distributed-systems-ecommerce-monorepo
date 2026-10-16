import { ApiError } from "@ecommerce/api-client";
import { createAuthApi } from "../src";
import { CONFIG, jsonResponse, problemResponse, tokensBody } from "./support/tokens";

function setup(response: Response) {
  const fetchMock = jest.fn<Promise<Response>, [string, RequestInit]>(() => Promise.resolve(response));
  return { api: createAuthApi(CONFIG, fetchMock as unknown as typeof fetch), fetchMock };
}

function lastRequest(fetchMock: jest.Mock) {
  const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
  return { url, init, headers: init.headers as Record<string, string> };
}

describe("createAuthApi", () => {
  it("logs in through the gateway and forwards the client address", async () => {
    const { api, fetchMock } = setup(jsonResponse(tokensBody("a", "r")));

    const tokens = await api.login({ email: "ada@example.com", password: "pw" }, "203.0.113.9");

    const { url, init, headers } = lastRequest(fetchMock);
    expect(url).toBe("http://gateway.test/api/v1/auth/login");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ email: "ada@example.com", password: "pw" });
    expect(headers["x-forwarded-for"]).toBe("203.0.113.9");
    expect(tokens).toEqual({ accessToken: "a", refreshToken: "r", expiresInSeconds: 900 });
  });

  it("registers through the gateway and forwards the client address", async () => {
    const { api, fetchMock } = setup(jsonResponse({ id: "1", email: "ada@example.com", role: "customer" }, 201));

    const user = await api.register({ email: "ada@example.com", password: "pw" }, "198.51.100.4");

    expect(lastRequest(fetchMock).url).toBe("http://gateway.test/api/v1/auth/register");
    expect(lastRequest(fetchMock).headers["x-forwarded-for"]).toBe("198.51.100.4");
    expect(user.role).toBe("customer");
  });

  it("sends no forwarding header when the address is unknown", async () => {
    const { api, fetchMock } = setup(jsonResponse(tokensBody("a", "r")));

    await api.login({ email: "a@example.com", password: "pw" });

    expect(lastRequest(fetchMock).headers).not.toHaveProperty("x-forwarded-for");
  });

  it("refreshes with the refresh token in the body", async () => {
    const { api, fetchMock } = setup(jsonResponse(tokensBody("a2", "r2")));

    const tokens = await api.refresh("r1", "203.0.113.9");

    expect(JSON.parse(lastRequest(fetchMock).init.body as string)).toEqual({ refresh_token: "r1" });
    expect(tokens.refreshToken).toBe("r2");
  });

  it("surfaces a failed login as an ApiError with the problem", async () => {
    const { api } = setup(problemResponse(401, "Invalid credentials"));

    const failure = (await api.login({ email: "a@example.com", password: "x" }).catch((error: unknown) => error)) as ApiError;

    expect(failure).toBeInstanceOf(ApiError);
    expect(failure.problem.title).toBe("Invalid credentials");
  });

  it("logs out and ignores API errors because logout must always succeed locally", async () => {
    const { api, fetchMock } = setup(problemResponse(500, "Boom"));

    await expect(api.logout("r1", "203.0.113.9")).resolves.toBeUndefined();
    expect(lastRequest(fetchMock).url).toBe("http://gateway.test/api/v1/auth/logout");
  });

  it("still reports a network failure on logout", async () => {
    const fetchMock = jest.fn(() => Promise.reject(new TypeError("fetch failed")));
    const api = createAuthApi(CONFIG, fetchMock);

    await expect(api.logout("r1")).rejects.toThrow("could not be reached");
  });
});
