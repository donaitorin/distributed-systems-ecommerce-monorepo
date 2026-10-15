import { createRemoteKeySet, createSessionVerifier, SessionUnavailableError } from "../src";
import { CONFIG, createTestKeys, jsonResponse } from "./support/tokens";

describe("createSessionVerifier", () => {
  it("returns the session of a valid token", async () => {
    const keys = await createTestKeys();
    const verify = createSessionVerifier(CONFIG, keys.keySet);

    const session = await verify(await keys.sign({ role: "admin" }));

    expect(session).toMatchObject({ userId: "user-1", role: "admin", email: "ada@example.com" });
    expect(session?.expiresAt.getTime()).toBeGreaterThan(Date.now());
  });

  it("omits the email when the token has none", async () => {
    const keys = await createTestKeys();
    const verify = createSessionVerifier(CONFIG, keys.keySet);

    const session = await verify(await keys.sign({ email: undefined }));

    expect(session).not.toHaveProperty("email");
  });

  it.each([
    ["expired", { expiresIn: "-1m" }],
    ["wrong issuer", { issuer: "someone-else" }],
    ["wrong audience", { audience: "another-api" }],
  ])("rejects a token that is %s", async (_name, options) => {
    const keys = await createTestKeys();
    const verify = createSessionVerifier(CONFIG, keys.keySet);

    expect(await verify(await keys.sign({}, options))).toBeNull();
  });

  it("rejects a token signed by another key", async () => {
    const trusted = await createTestKeys("same-kid");
    const attacker = await createTestKeys("same-kid");
    const verify = createSessionVerifier(CONFIG, trusted.keySet);

    expect(await verify(await attacker.sign())).toBeNull();
  });

  it("rejects a token whose key id is unknown", async () => {
    const trusted = await createTestKeys("known");
    const other = await createTestKeys("unknown");

    expect(await createSessionVerifier(CONFIG, trusted.keySet)(await other.sign())).toBeNull();
  });

  it("rejects garbage and unsigned tokens", async () => {
    const keys = await createTestKeys();
    const verify = createSessionVerifier(CONFIG, keys.keySet);
    const unsigned = `${btoa('{"alg":"none"}')}.${btoa('{"sub":"x","role":"admin"}')}.`;

    expect(await verify("not-a-jwt")).toBeNull();
    expect(await verify(unsigned)).toBeNull();
  });

  it("rejects a token without the role claim", async () => {
    const keys = await createTestKeys();
    const verify = createSessionVerifier(CONFIG, keys.keySet);

    expect(await verify(await keys.sign({ role: 42 }))).toBeNull();
  });

  it("reports an unreachable key set as unavailable, not as an anonymous user", async () => {
    const keys = await createTestKeys();
    const failing = createRemoteKeySet(
      CONFIG,
      jest.fn(() => Promise.reject(new TypeError("fetch failed"))),
    );

    await expect(createSessionVerifier(CONFIG, failing)(await keys.sign())).rejects.toBeInstanceOf(
      SessionUnavailableError,
    );
  });
});

describe("createRemoteKeySet", () => {
  it("fetches the JWKS once and serves later tokens from its cache", async () => {
    const keys = await createTestKeys();
    const fetchMock = jest.fn(() => Promise.resolve(jsonResponse(keys.jwks)));
    const verify = createSessionVerifier(
      CONFIG,
      createRemoteKeySet(CONFIG, fetchMock),
    );

    expect(await verify(await keys.sign())).not.toBeNull();
    expect(await verify(await keys.sign())).not.toBeNull();
    expect(await verify(await keys.sign())).not.toBeNull();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const calls = fetchMock.mock.calls as unknown as [string][];
    expect(String(calls[0]?.[0])).toBe(CONFIG.jwksUrl);
  });

  it("builds a key set against the configured URL without an injected fetch", () => {
    expect(typeof createRemoteKeySet(CONFIG)).toBe("function");
  });
});
