import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, userEvent, within } from "storybook/test";
import type { UploadResult } from "../../lib/upload-client";
import type { SaveResult } from "../../server/product-actions";
import { ProductImageEditor } from "./product-image-editor";
import { STORY_IMAGE, STORY_PRODUCT, withAppProviders } from "../story-support";

const WITH_IMAGE = { ...STORY_PRODUCT, image_url: STORY_IMAGE, thumbnail_url: STORY_IMAGE };

const meta = {
  title: "Backoffice/ProductImageEditor",
  component: ProductImageEditor,
  parameters: { layout: "padded" },
  decorators: [withAppProviders()],
  args: {
    product: STORY_PRODUCT,
    etag: '"3"',
    uploadImage: (): Promise<UploadResult> => Promise.resolve({ ok: true, product: { ...WITH_IMAGE, version: 4 }, etag: '"4"' }),
    removeImage: (): Promise<SaveResult> => Promise.resolve({ ok: true, product: { ...STORY_PRODUCT, version: 5 }, etag: '"5"' }),
    onChanged: () => undefined,
  },
} satisfies Meta<typeof ProductImageEditor>;

export default meta;
type Story = StoryObj<typeof meta>;

export const NoImage: Story = {};

export const WithImage: Story = { args: { product: WITH_IMAGE } };

export const FileTooLarge: Story = {
  play: async ({ canvasElement }) => {
    const input = within(canvasElement).getByLabelText("Upload an image");
    const big = new File([new Uint8Array(5 * 1024 * 1024 + 1)], "big.png", { type: "image/png" });
    await userEvent.upload(input, big);
    await expect(await within(canvasElement).findByRole("alert")).toHaveTextContent("larger than 5 MB");
  },
};

export const UploadRejected: Story = {
  args: {
    uploadImage: () =>
      Promise.resolve({ ok: false, status: 415, title: "Unsupported media type", fieldErrors: {} }),
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.upload(canvas.getByLabelText("Upload an image"), new File(["x"], "a.png", { type: "image/png" }));
    await userEvent.click(canvas.getByRole("button", { name: "Upload image" }));
    await expect(await canvas.findByRole("alert")).toHaveTextContent("JPEG, PNG or WebP");
  },
};

export const StorageUnavailable: Story = {
  args: {
    uploadImage: () =>
      Promise.resolve({ ok: false, status: 503, title: "Storage down", fieldErrors: {}, retryAfterSeconds: 5 }),
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.upload(canvas.getByLabelText("Upload an image"), new File(["x"], "a.png", { type: "image/png" }));
    await userEvent.click(canvas.getByRole("button", { name: "Upload image" }));
    await expect(await canvas.findByRole("alert")).toHaveTextContent("Try again in 5 seconds");
  },
};
