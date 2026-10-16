const preset = require("@ecommerce/config/jest");

module.exports = {
  ...preset,
  rootDir: __dirname,
  transformIgnorePatterns: ["node_modules/(?!\\.pnpm/nuqs@|nuqs/)"],
  collectCoverageFrom: ["<rootDir>/src/**/*.{ts,tsx}", "!<rootDir>/src/index.ts", "!<rootDir>/src/client.ts"],
};
