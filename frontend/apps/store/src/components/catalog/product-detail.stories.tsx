import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { ProductDetail } from "./product-detail";
import { STORY_ADD, STORY_PRODUCT } from "../story-support";

const meta = {
  title: "Store/ProductDetail",
  component: ProductDetail,
  parameters: { layout: "padded" },
  args: { product: STORY_PRODUCT, addToCart: STORY_ADD },
} satisfies Meta<typeof ProductDetail>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const LowStock: Story = { args: { product: { ...STORY_PRODUCT, stock: 2 } } };

export const OutOfStock: Story = { args: { product: { ...STORY_PRODUCT, stock: 0 } } };

export const NoImage: Story = { args: { product: { ...STORY_PRODUCT, image_url: null, thumbnail_url: null } } };

export const Minimal: Story = {
  args: { product: { ...STORY_PRODUCT, description: null, category: null, weight_kg: null, image_url: null, thumbnail_url: null } },
};

export const LongName: Story = {
  args: {
    product: {
      ...STORY_PRODUCT,
      name: "Ultra lightweight trail running shoes with reinforced toe cap and breathable mesh upper",
    },
  },
};

export const Mobile: Story = {
  globals: { viewport: { value: "mobile", isRotated: false } },
};
