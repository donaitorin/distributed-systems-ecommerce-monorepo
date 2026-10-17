import CustomEnvironment from "@storybook/test-runner/playwright/custom-environment.js";

function previewIsReady() {
  return (
    globalThis.__STORYBOOK_MODULE_CORE_EVENTS__ !== undefined &&
    globalThis.__STORYBOOK_ADDONS_CHANNEL__ !== undefined &&
    globalThis.__STORYBOOK_PREVIEW__ !== undefined
  );
}

export default class PreviewReadyEnvironment extends CustomEnvironment {
  async _setNewPageInstance(context) {
    const page = await super._setNewPageInstance(context);
    const navigate = page.goto.bind(page);
    page.goto = async (...args) => {
      const response = await navigate(...args);
      await page.waitForFunction(previewIsReady);
      return response;
    };
    return page;
  }
}
