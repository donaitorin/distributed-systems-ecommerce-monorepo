/**
 * @jest-environment node
 */
import { NextRequest } from "next/server";
import { isProtectedPath, LOGIN_PATH } from "../src/lib/paths";
import { config, proxy } from "../src/proxy";

const handle = jest.fn();
const createProxy = jest.fn((options: unknown) => {
  void options;
  return handle;
});

jest.mock("@ecommerce/auth/next", () => ({
  authRuntime: () => ({ runtime: true }),
  createProxy: (options: unknown) => createProxy(options) as unknown,
}));

describe("isProtectedPath", () => {
  it.each(["/account", "/account/addresses", "/checkout", "/checkout/pay", "/orders/42"])(
    "protects %s",
    (path) => {
      expect(isProtectedPath(path)).toBe(true);
    },
  );

  it.each(["/", "/products", "/login", "/register", "/accounting", "/account-help"])(
    "leaves %s public",
    (path) => {
      expect(isProtectedPath(path)).toBe(false);
    },
  );
});

describe("store proxy", () => {
  it("is built once, with the store guard, and delegates every request", async () => {
    handle.mockResolvedValue("response");

    await proxy(new NextRequest("http://store.test/products"));
    await proxy(new NextRequest("http://store.test/account"));

    expect(createProxy).toHaveBeenCalledTimes(1);
    const options = createProxy.mock.calls[0]?.[0] as {
      guard: { loginPath: string; isProtected: typeof isProtectedPath };
      runtime: unknown;
      development: boolean;
    };
    expect(options.runtime).toEqual({ runtime: true });
    expect(options.guard.loginPath).toBe(LOGIN_PATH);
    expect(options.guard.isProtected).toBe(isProtectedPath);
    expect(options.development).toBe(false);
    expect(handle).toHaveBeenCalledTimes(2);
  });

  it("runs on the site root and on pages, but not on static assets", () => {
    const patterns = config.matcher.map((source) => new RegExp(`^${source}$`));
    const matches = (path: string) => patterns.some((pattern) => pattern.test(path));

    expect(matches("/")).toBe(true);
    expect(matches("/account")).toBe(true);
    expect(matches("/_next/static/chunks/app.js")).toBe(false);
    expect(matches("/favicon.ico")).toBe(false);
  });
});
