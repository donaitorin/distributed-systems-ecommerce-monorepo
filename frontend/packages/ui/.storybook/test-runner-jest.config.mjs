import { getJestConfig } from "@storybook/test-runner";
import { fileURLToPath } from "node:url";

const config = getJestConfig();

export default {
  ...config,
  setupFilesAfterEnv: [...config.setupFilesAfterEnv, fileURLToPath(new URL("./axe-setup.mjs", import.meta.url))],
};
