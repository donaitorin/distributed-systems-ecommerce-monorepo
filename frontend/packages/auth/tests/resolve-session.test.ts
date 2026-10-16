import { ApiError } from "@ecommerce/api-client";
import {
  createRefreshCoordinator,
  createSessionResolver,
  createSessionVerifier,
  SessionUnavailableError,
} from "../src";
import { CONFIG, createTestKeys } from "./support/tokens";

async function setup(refresh = jest.fn()) {
  const keys = await createTestKeys();
  const verify = createSessionVerifier(CONFIG, keys.keySet);
  const resolve = createSessionResolver(CONFIG, verify, createRefreshCoordinator(refresh));
  return { keys, resolve, refresh };
}

const rejected = () =>
  Promise.reject(
    new ApiError({ type: "about:blank", title: "Unauthorized", status: 401 }, new Response(null, { status: 401 })),
  );

describe("createSessionResolver", () => {
  it("accepts a valid access token without touching the API or the cookies", async () => {
    const { keys, resolve, refresh } = await setup();

    const result = await resolve({ accessToken: await keys.sign({ role: "admin" }), refreshToken: "r" });

    expect(result.session?.role).toBe("admin");
    expect(result.cookies).toEqual([]);
    expect(refresh).not.toHaveBeenCalled();
  });

  it("refreshes an expired access token and returns the new cookies", async () => {
    const { keys, resolve, refresh } = await setup();
    const fresh = await keys.sign({ role: "admin" });
    refresh.mockResolvedValue({ accessToken: fresh, refreshToken: "r2", expiresInSeconds: 900 });

    const result = await resolve({
      accessToken: await keys.sign({}, { expiresIn: "-1m" }),
      refreshToken: "r1",
      clientIp: "203.0.113.9",
    });

    expect(result.session?.role).toBe("admin");
    expect(result.cookies.map((cookie) => [cookie.name, cookie.value])).toEqual([
      ["ecommerce_access", fresh],
      ["ecommerce_refresh", "r2"],
    ]);
    expect(refresh).toHaveBeenCalledWith("r1", "203.0.113.9");
  });

  it("refreshes when only the refresh cookie is left", async () => {
    const { keys, resolve, refresh } = await setup();
    refresh.mockResolvedValue({ accessToken: await keys.sign(), refreshToken: "r2", expiresInSeconds: 900 });

    expect((await resolve({ refreshToken: "r1" })).session).not.toBeNull();
  });

  it("has no session and nothing to clear for an anonymous visitor", async () => {
    const { resolve } = await setup();

    expect(await resolve({})).toEqual({ session: null, cookies: [] });
  });

  it("clears a stale access cookie when there is nothing to refresh with", async () => {
    const { keys, resolve } = await setup();

    const result = await resolve({ accessToken: await keys.sign({}, { expiresIn: "-1m" }) });

    expect(result.session).toBeNull();
    expect(result.cookies.map((cookie) => cookie.options.maxAge)).toEqual([0, 0]);
  });

  it("clears both cookies when the refresh token is rejected", async () => {
    const { resolve, refresh } = await setup();
    refresh.mockImplementation(rejected);

    const result = await resolve({ refreshToken: "revoked" });

    expect(result.session).toBeNull();
    expect(result.cookies.map((cookie) => cookie.value)).toEqual(["", ""]);
  });

  it("clears the cookies when the API hands out a token we cannot verify", async () => {
    const { resolve, refresh } = await setup();
    refresh.mockResolvedValue({ accessToken: "garbage", refreshToken: "r2", expiresInSeconds: 900 });

    const result = await resolve({ refreshToken: "r1" });

    expect(result.session).toBeNull();
    expect(result.cookies.map((cookie) => cookie.options.maxAge)).toEqual([0, 0]);
  });

  it("keeps the cookies and reports unavailable when the API is down", async () => {
    const { resolve, refresh } = await setup();
    refresh.mockRejectedValue(new TypeError("fetch failed"));

    await expect(resolve({ refreshToken: "r1" })).rejects.toBeInstanceOf(SessionUnavailableError);
  });

  it("passes a verification outage through", async () => {
    const outage = new SessionUnavailableError();
    const resolve = createSessionResolver(
      CONFIG,
      () => Promise.reject(outage),
      createRefreshCoordinator(jest.fn()),
    );

    await expect(resolve({ accessToken: "x" })).rejects.toBe(outage);
  });
});
