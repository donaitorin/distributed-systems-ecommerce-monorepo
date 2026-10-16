import type { StorybookConfig } from "@storybook/nextjs-vite";
import tailwindcss from "@tailwindcss/vite";
import { mergeConfig } from "vite";

const config: StorybookConfig = {
  framework: "@storybook/nextjs-vite",
  stories: ["../src/**/*.stories.@(ts|tsx)", "../../../apps/*/src/**/*.stories.@(ts|tsx)"],
  addons: ["@storybook/addon-a11y"],
  core: { disableTelemetry: true },
  viteFinal: (viteConfig) =>
    mergeConfig(viteConfig, {
      plugins: [tailwindcss()],
      build: {
        rolldownOptions: {
          onwarn(warning: { code?: string }, defaultHandler: (warning: unknown) => void) {
            if (warning.code !== "MODULE_LEVEL_DIRECTIVE") {
              defaultHandler(warning);
            }
          },
        },
      },
    }),
};

export default config;
