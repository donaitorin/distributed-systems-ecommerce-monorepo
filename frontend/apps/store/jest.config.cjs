const preset = require("@ecommerce/config/jest");

module.exports = {
  ...preset,
  rootDir: __dirname,
  collectCoverageFrom: ["<rootDir>/src/**/*.{ts,tsx}", "!<rootDir>/src/app/layout.tsx", "!<rootDir>/src/app/globals.css"],
};
