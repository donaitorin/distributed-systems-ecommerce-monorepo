import { buildContentSecurityPolicy, createNonce, withCookies } from "../src/next";

describe("buildContentSecurityPolicy", () => {
  const policy = buildContentSecurityPolicy({ nonce: "abc" });
  const directives: Record<string, string> = Object.fromEntries(
    policy.split("; ").map((directive): [string, string] => {
      const [name = "", ...values] = directive.split(" ");
      return [name, values.join(" ")];
    }),
  );

  it("allows only same-origin fonts so no external font origin is needed", () => {
    expect(directives["font-src"]).toBe("'self'");
  });

  it("allows scripts only with the nonce and never unsafe-inline", () => {
    expect(directives["script-src"]).toBe("'self' 'nonce-abc' 'strict-dynamic'");
    expect(policy).not.toContain("script-src 'unsafe-inline'");
  });

  it("locks down plugins, framing, base URI and form targets", () => {
    expect(directives["object-src"]).toBe("'none'");
    expect(directives["frame-ancestors"]).toBe("'none'");
    expect(directives["base-uri"]).toBe("'self'");
    expect(directives["form-action"]).toBe("'self'");
    expect(directives["default-src"]).toBe("'self'");
  });

  it("allows same-origin images including data and blob urls", () => {
    expect(directives["img-src"]).toBe("'self' data: blob:");
  });

  it("only allows unsafe-eval and websockets in development", () => {
    const development = buildContentSecurityPolicy({ nonce: "abc", development: true });

    expect(development).toContain("'unsafe-eval'");
    expect(development).toContain("ws:");
    expect(policy).not.toContain("unsafe-eval");
    expect(policy).not.toContain("ws:");
  });
});

describe("createNonce", () => {
  it("is unique and base64", () => {
    const nonces = new Set(Array.from({ length: 50 }, createNonce));

    expect(nonces.size).toBe(50);
    expect([...nonces].every((nonce) => /^[A-Za-z0-9+/=]+$/.test(nonce))).toBe(true);
  });
});

describe("withCookies", () => {
  const spec = (name: string, value: string) => ({
    name,
    value,
    options: { httpOnly: true as const, secure: false, sameSite: "lax" as const, path: "/" as const, maxAge: 1 },
  });

  it("replaces existing cookies and keeps unrelated ones", () => {
    expect(withCookies("a=1; theme=dark; b=2", [spec("a", "9")])).toBe("a=9; theme=dark; b=2");
  });

  it("adds missing cookies", () => {
    expect(withCookies(null, [spec("a", "1")])).toBe("a=1");
  });

  it("removes cleared cookies", () => {
    expect(withCookies("a=1; b=2", [spec("a", "")])).toBe("b=2");
  });

  it("keeps values that contain equals signs", () => {
    expect(withCookies("token=abc==", [])).toBe("token=abc==");
  });

  it("ignores malformed pairs", () => {
    expect(withCookies("garbage; =x; a=1", [])).toBe("a=1");
  });
});
