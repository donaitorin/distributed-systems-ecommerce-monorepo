import { clearedCookies, sessionCookies } from "../src";
import { CONFIG } from "./support/tokens";

const TOKENS = { accessToken: "a", refreshToken: "r", expiresInSeconds: 900 };

describe("session cookies", () => {
  it("are httpOnly, SameSite=Lax and scoped to the whole site", () => {
    for (const cookie of sessionCookies({ ...CONFIG, secureCookies: true }, TOKENS)) {
      expect(cookie.options).toMatchObject({ httpOnly: true, sameSite: "lax", path: "/", secure: true });
    }
  });

  it("follow the configurable secure flag for local http", () => {
    for (const cookie of sessionCookies(CONFIG, TOKENS)) {
      expect(cookie.options.secure).toBe(false);
    }
  });

  it("expire the access cookie with the token and the refresh cookie with the configured age", () => {
    const [access, refresh] = sessionCookies(CONFIG, TOKENS);

    expect(access).toMatchObject({ name: "ecommerce_access", value: "a" });
    expect(access?.options.maxAge).toBe(900);
    expect(refresh).toMatchObject({ name: "ecommerce_refresh", value: "r" });
    expect(refresh?.options.maxAge).toBe(CONFIG.refreshCookieMaxAgeSeconds);
  });

  it("never expire immediately even for a tiny lifetime", () => {
    const [access] = sessionCookies(CONFIG, { ...TOKENS, expiresInSeconds: 0.2 });

    expect(access?.options.maxAge).toBe(1);
  });

  it("are cleared with empty values and zero age", () => {
    expect(clearedCookies(CONFIG).map(({ name, value, options }) => [name, value, options.maxAge])).toEqual([
      ["ecommerce_access", "", 0],
      ["ecommerce_refresh", "", 0],
    ]);
  });
});
