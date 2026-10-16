const preset = require("@ecommerce/config/jest");

module.exports = {
  ...preset,
  rootDir: __dirname,
  testEnvironment: "node",
  setupFilesAfterEnv: [],
  collectCoverageFrom: ["<rootDir>/src/**/*.ts", "!<rootDir>/src/generated/**", "!<rootDir>/src/index.ts"],
};
