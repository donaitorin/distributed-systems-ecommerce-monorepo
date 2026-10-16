import { ApiError } from "@ecommerce/api-client";
import { createRefreshCoordinator, RefreshRejectedError, type TokenPair } from "../src";

const pair = (name: string): TokenPair => ({ accessToken: `a-${name}`, refreshToken: `r-${name}`, expiresInSeconds: 900 });

function rejection(status = 401): ApiError {
  return new ApiError(
    { type: "about:blank", title: "Unauthorized", status },
    new Response(null, { status }),
  );
}

describe("createRefreshCoordinator", () => {
  it("refreshes once for concurrent requests that carry the same token", async () => {
    const refresh = jest.fn(() => Promise.resolve(pair("new")));
    const coordinate = createRefreshCoordinator(refresh);

    const results = await Promise.all([coordinate("old"), coordinate("old"), coordinate("old")]);

    expect(refresh).toHaveBeenCalledTimes(1);
    expect(results.every((result) => result === results[0])).toBe(true);
  });

  it("serves a request that arrives just after the winner from the same result", async () => {
    const refresh = jest.fn(() => Promise.resolve(pair("new")));
    const coordinate = createRefreshCoordinator(refresh);

    await coordinate("old");
    const late = await coordinate("old");

    expect(refresh).toHaveBeenCalledTimes(1);
    expect(late).toEqual(pair("new"));
  });

  it("calls the API again after the reuse window", async () => {
    let now = 0;
    const refresh = jest.fn(() => Promise.resolve(pair("new")));
    const coordinate = createRefreshCoordinator(refresh, () => now);

    await coordinate("old");
    now = 10_001;
    await coordinate("old");

    expect(refresh).toHaveBeenCalledTimes(2);
  });

  it("keeps different tokens apart", async () => {
    const refresh = jest.fn((token: string) => Promise.resolve(pair(token)));
    const coordinate = createRefreshCoordinator(refresh);

    await coordinate("one");
    await coordinate("two");

    expect(refresh).toHaveBeenCalledTimes(2);
  });

  it("forwards the client address", async () => {
    const refresh = jest.fn(() => Promise.resolve(pair("new")));

    await createRefreshCoordinator(refresh)("old", { clientIp: "203.0.113.9" });

    expect(refresh).toHaveBeenCalledWith("old", "203.0.113.9");
  });

  it("retries once with the cookie that won the race", async () => {
    const refresh = jest.fn((token: string) =>
      token === "old" ? Promise.reject(rejection()) : Promise.resolve(pair("winner")),
    );
    const coordinate = createRefreshCoordinator(refresh);

    const result = await coordinate("old", { readLatestRefreshToken: () => "rotated" });

    expect(result).toEqual(pair("winner"));
    expect(refresh.mock.calls.map(([token]) => token)).toEqual(["old", "rotated"]);
  });

  it("does not retry when the cookie did not change", async () => {
    const refresh = jest.fn(() => Promise.reject(rejection()));
    const coordinate = createRefreshCoordinator(refresh);

    await expect(coordinate("old", { readLatestRefreshToken: () => "old" })).rejects.toBeInstanceOf(
      RefreshRejectedError,
    );
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it("does not retry without a newer cookie", async () => {
    const refresh = jest.fn(() => Promise.reject(rejection()));

    await expect(
      createRefreshCoordinator(refresh)("old", { readLatestRefreshToken: () => undefined }),
    ).rejects.toBeInstanceOf(RefreshRejectedError);
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it("gives up after a single retry", async () => {
    const refresh = jest.fn(() => Promise.reject(rejection()));
    const coordinate = createRefreshCoordinator(refresh);

    await expect(coordinate("old", { readLatestRefreshToken: () => "rotated" })).rejects.toBeInstanceOf(
      RefreshRejectedError,
    );
    expect(refresh).toHaveBeenCalledTimes(2);
  });

  it("does not remember failures", async () => {
    const refresh = jest
      .fn<Promise<TokenPair>, [string]>()
      .mockRejectedValueOnce(rejection())
      .mockResolvedValueOnce(pair("new"));
    const coordinate = createRefreshCoordinator(refresh);

    await expect(coordinate("old")).rejects.toBeInstanceOf(RefreshRejectedError);

    expect(await coordinate("old")).toEqual(pair("new"));
  });

  it("passes server and network failures through untouched", async () => {
    const outage = rejection(503);
    const refresh = jest.fn(() => Promise.reject(outage));

    await expect(createRefreshCoordinator(refresh)("old")).rejects.toBe(outage);
  });

  it("passes a retry failure that is not a rejection through untouched", async () => {
    const outage = new Error("down");
    const refresh = jest.fn((token: string) =>
      token === "old" ? Promise.reject(rejection()) : Promise.reject(outage),
    );

    await expect(
      createRefreshCoordinator(refresh)("old", { readLatestRefreshToken: () => "rotated" }),
    ).rejects.toBe(outage);
  });
});
