const preset = require("@ecommerce/config/jest");

module.exports = {
  ...preset,
  rootDir: __dirname,
  setupFilesAfterEnv: [...preset.setupFilesAfterEnv, "<rootDir>/jest.setup.ts"],
  collectCoverageFrom: [...preset.collectCoverageFrom, "!<rootDir>/src/index.ts", "!<rootDir>/src/stories/**"],
};
