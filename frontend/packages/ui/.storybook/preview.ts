import type { Preview } from "@storybook/nextjs-vite";
import "./preview.css";

const preview: Preview = {
  parameters: {
    layout: "centered",
    controls: { matchers: { date: /Date$/ } },
    a11y: { test: "error" },
    viewport: {
      options: {
        mobile: { name: "Mobile 320", styles: { width: "320px", height: "640px" }, type: "mobile" },
        tablet: { name: "Tablet 768", styles: { width: "768px", height: "1024px" }, type: "tablet" },
        desktop: { name: "Desktop 1280", styles: { width: "1280px", height: "800px" }, type: "desktop" },
      },
    },
  },
};

export default preview;
