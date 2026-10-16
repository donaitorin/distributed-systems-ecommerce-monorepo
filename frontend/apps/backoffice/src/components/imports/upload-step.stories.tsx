import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, userEvent, within } from "storybook/test";
import type { ImportApi } from "./import-api";
import { UploadStep } from "./upload-step";
import { STORY_IMPORT, withAppProviders } from "../story-support";

const api = (result: Awaited<ReturnType<ImportApi["uploadImportFile"]>>): ImportApi => ({
  uploadImportFile: () => Promise.resolve(result),
  fetchImport: () => Promise.reject(new Error("unused")),
  fetchProblems: () => Promise.reject(new Error("unused")),
});

const meta = {
  title: "Backoffice/Imports/UploadStep",
  component: UploadStep,
  parameters: { layout: "padded" },
  decorators: [withAppProviders()],
  args: {
    maxBytes: 50 * 1024 * 1024,
    api: api({ ok: true, existing: false, import: STORY_IMPORT }),
    onUploaded: () => undefined,
  },
} satisfies Meta<typeof UploadStep>;

export default meta;
type Story = StoryObj<typeof meta>;

const csv = () => new File(["name,sku\\n"], "products.csv", { type: "text/csv" });

export const Default: Story = {};

export const TooLargeForTheServer: Story = {
  args: { api: api({ ok: false, status: 413, title: "Payload too large", fieldErrors: {} }) },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.upload(canvas.getByLabelText("Choose a file"), csv());
    await expect(await canvas.findByRole("alert")).toHaveTextContent("larger than the 50 MB limit");
  },
};

export const StorageUnavailable: Story = {
  args: { api: api({ ok: false, status: 503, title: "Down", fieldErrors: {}, retryAfterSeconds: 5 }) },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.upload(canvas.getByLabelText("Choose a file"), csv());
    await expect(await canvas.findByRole("alert")).toHaveTextContent("Try again in 5 seconds");
  },
};

export const Mobile: Story = {
  globals: { viewport: { value: "mobile", isRotated: false } },
};
