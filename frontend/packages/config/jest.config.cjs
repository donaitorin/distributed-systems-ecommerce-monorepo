const preset = require("./jest/preset.cjs");

module.exports = {
  ...preset,
  testEnvironment: "node",
  setupFilesAfterEnv: [],
  collectCoverageFrom: ["<rootDir>/tools/**/*.cjs"],
  transform: {},
  testMatch: ["<rootDir>/tests/**/*.test.cjs"],
};
