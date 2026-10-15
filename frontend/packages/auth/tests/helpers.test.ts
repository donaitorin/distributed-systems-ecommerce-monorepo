import { clientIpFrom, forwardingHeaders, safeRedirectPath } from "../src";

describe("clientIpFrom", () => {
  it("takes the last forwarded address, the one added by our own gateway", () => {
    const headers = new Headers({ "x-forwarded-for": "6.6.6.6, 203.0.113.9" });

    expect(clientIpFrom(headers)).toBe("203.0.113.9");
  });

  it("handles a single address and IPv6", () => {
    expect(clientIpFrom(new Headers({ "x-forwarded-for": "198.51.100.4" }))).toBe("198.51.100.4");
    expect(clientIpFrom(new Headers({ "x-forwarded-for": "2001:db8::1" }))).toBe("2001:db8::1");
  });

  it("falls back to x-real-ip", () => {
    expect(clientIpFrom(new Headers({ "x-real-ip": "192.0.2.7" }))).toBe("192.0.2.7");
  });

  it.each(["", "garbage", "1.2.3.4; drop", "<script>"])("ignores the value %p", (value) => {
    expect(clientIpFrom(new Headers({ "x-forwarded-for": value }))).toBeUndefined();
  });

  it("returns nothing without headers", () => {
    expect(clientIpFrom(new Headers())).toBeUndefined();
  });
});

describe("forwardingHeaders", () => {
  it("sets x-forwarded-for from the client address", () => {
    expect(forwardingHeaders("203.0.113.9")).toEqual({ "x-forwarded-for": "203.0.113.9" });
  });

  it("sends nothing when the address is unknown", () => {
    expect(forwardingHeaders(undefined)).toEqual({});
  });
});

describe("safeRedirectPath", () => {
  it.each(["/account", "/products?q=a&page=2", "/"])("keeps the local path %s", (path) => {
    expect(safeRedirectPath(path)).toBe(path);
  });

  it.each([
    "https://evil.example",
    "//evil.example",
    "/\\evil.example",
    "javascript:alert(1)",
    "account",
    "/a\nb",
    "",
    null,
    undefined,
  ])("falls back for %p", (candidate) => {
    expect(safeRedirectPath(candidate)).toBe("/");
    expect(safeRedirectPath(candidate, "/login")).toBe("/login");
  });
});
