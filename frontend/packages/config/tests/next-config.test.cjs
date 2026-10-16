const { createNextConfig, STATIC_SECURITY_HEADERS } = require("../next/index.cjs");

describe("createNextConfig", () => {
  const appDirectory = "/repo/frontend/apps/store";

  it("builds a standalone app that traces the whole workspace", () => {
    const config = createNextConfig({ appDirectory });

    expect(config.output).toBe("standalone");
    expect(config.outputFileTracingRoot).toBe("/repo/frontend");
    expect(config.poweredByHeader).toBe(false);
  });

  it("transpiles the shared workspace packages", () => {
    expect(createNextConfig({ appDirectory }).transpilePackages).toEqual([
      "@ecommerce/ui",
      "@ecommerce/auth",
      "@ecommerce/api-client",
      "@ecommerce/web-core",
    ]);
  });

  it("leaves the root zone without a base path or asset prefix", () => {
    const config = createNextConfig({ appDirectory });

    expect(config).not.toHaveProperty("basePath");
    expect(config).not.toHaveProperty("assetPrefix");
  });

  it("sets the base path and asset prefix of a sub path zone", () => {
    const config = createNextConfig({ appDirectory, zonePath: "/admin" });

    expect(config.basePath).toBe("/admin");
    expect(config.assetPrefix).toBe("/admin");
  });

  it("sends the static security headers on every route", async () => {
    const [rule] = await createNextConfig({ appDirectory }).headers();

    expect(rule.source).toBe("/:path*");
    expect(Object.fromEntries(rule.headers.map(({ key, value }) => [key, value]))).toMatchObject({
      "X-Content-Type-Options": "nosniff",
      "Referrer-Policy": "strict-origin-when-cross-origin",
    });
  });

  it("denies framing", () => {
    expect(STATIC_SECURITY_HEADERS).toContainEqual({ key: "X-Frame-Options", value: "DENY" });
  });
});
