import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, waitFor, within } from "storybook/test";
import { BROKEN_IMAGE, SAMPLE_IMAGE, SAMPLE_THUMBNAIL } from "../../stories/sample-images";
import { ProductImage } from "./product-image";

const meta = {
  title: "Components/ProductImage",
  component: ProductImage,
  decorators: [
    (Story) => (
      <div className="w-64">
        <Story />
      </div>
    ),
  ],
  args: {
    thumbnailUrl: SAMPLE_THUMBNAIL,
    imageUrl: SAMPLE_IMAGE,
    alt: "Running shoes",
  },
} satisfies Meta<typeof ProductImage>;

export default meta;
type Story = StoryObj<typeof meta>;

export const WithImages: Story = {};

export const ThumbnailOnly: Story = { args: { imageUrl: null } };

export const NoImage: Story = {
  args: { thumbnailUrl: null, imageUrl: null },
  play: async ({ canvasElement }) => {
    await expect(within(canvasElement).getByRole("img", { name: "Running shoes" })).toBeVisible();
  },
};

export const LoadError: Story = {
  args: { thumbnailUrl: BROKEN_IMAGE, imageUrl: BROKEN_IMAGE },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await waitFor(async () => {
      await expect(canvas.getByRole("img", { name: "Running shoes" }).tagName.toLowerCase()).toBe("svg");
    });
  },
};
