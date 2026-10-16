/**
 * @jest-environment node
 */
import { NextRequest } from "next/server";
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

describe("backoffice proxy", () => {
  it("requires the admin role everywhere except the login page", async () => {
    handle.mockResolvedValue("response");

    await proxy(new NextRequest("http://backoffice.test/"));
    await proxy(new NextRequest("http://backoffice.test/products"));

    expect(createProxy).toHaveBeenCalledTimes(1);
    expect(createProxy.mock.calls[0]?.[0]).toMatchObject({
      runtime: { runtime: true },
      guard: { loginPath: "/login", requiredRole: "admin" },
      development: false,
    });
    expect(handle).toHaveBeenCalledTimes(2);
  });

  it("also runs on the zone root, which the catch-all pattern alone would miss", () => {
    const patterns = config.matcher.map((source) => new RegExp(`^${source}$`));
    const matches = (path: string) => patterns.some((pattern) => pattern.test(path));

    expect(config.matcher).toContain("/");
    expect(matches("/")).toBe(true);
    expect(matches("/products")).toBe(true);
    expect(matches("/_next/static/chunks/app.js")).toBe(false);
  });

  it("leaves the streaming upload routes to their own guard, because the proxy buffers request bodies", () => {
    const patterns = config.matcher.map((source) => new RegExp(`^${source}$`));
    const matches = (path: string) => patterns.some((pattern) => pattern.test(path));

    expect(matches("/api/stream/products/RS-001/image")).toBe(false);
    expect(matches("/api/stream/imports")).toBe(false);
    expect(matches("/api/other")).toBe(true);
    expect(matches("/products/api/stream/x")).toBe(true);
  });
});
