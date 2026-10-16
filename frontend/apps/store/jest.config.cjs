const preset = require("@ecommerce/config/jest");

module.exports = {
  ...preset,
  rootDir: __dirname,
  setupFilesAfterEnv: [...preset.setupFilesAfterEnv, "<rootDir>/tests/support/jest.setup.ts"],
  transformIgnorePatterns: ["node_modules/(?!\\.pnpm/(?:nuqs|jose)@|nuqs/|jose/)"],
  collectCoverageFrom: [
    "<rootDir>/src/**/*.{ts,tsx}",
    "!<rootDir>/src/**/*.stories.{ts,tsx}",
    "!<rootDir>/src/**/*.d.ts",
    "!<rootDir>/src/components/story-support.tsx",
    "!<rootDir>/src/app/layout.tsx",
    "!<rootDir>/src/app/globals.css",
  ],
};
