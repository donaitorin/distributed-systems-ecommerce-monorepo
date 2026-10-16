const { join } = require("node:path");

const SHARED_PACKAGES = ["@ecommerce/ui", "@ecommerce/auth", "@ecommerce/api-client"];

const STATIC_SECURITY_HEADERS = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
];

function createNextConfig({ appDirectory, zonePath }) {
  return {
    output: "standalone",
    reactStrictMode: true,
    poweredByHeader: false,
    outputFileTracingRoot: join(appDirectory, "..", ".."),
    transpilePackages: SHARED_PACKAGES,
    ...(zonePath ? { basePath: zonePath, assetPrefix: zonePath } : {}),
    headers() {
      return Promise.resolve([{ source: "/:path*", headers: STATIC_SECURITY_HEADERS }]);
    },
  };
}

module.exports = { createNextConfig, STATIC_SECURITY_HEADERS, SHARED_PACKAGES };
