const preset = require("@ecommerce/config/jest");

module.exports = {
  ...preset,
  rootDir: __dirname,
  testEnvironment: "node",
  transformIgnorePatterns: ["node_modules/(?!\\.pnpm/jose@|jose/)"],
  setupFilesAfterEnv: [],
  collectCoverageFrom: ["<rootDir>/src/**/*.ts", "!<rootDir>/src/index.ts", "!<rootDir>/src/next/index.ts"],
};
