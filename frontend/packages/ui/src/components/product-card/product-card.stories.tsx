import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { SAMPLE_IMAGE, SAMPLE_THUMBNAIL } from "../../stories/sample-images";
import { ProductCard, ProductCardSkeleton } from "./product-card";

const meta = {
  title: "Components/ProductCard",
  component: ProductCard,
  decorators: [
    (Story) => (
      <div className="w-64">
        <Story />
      </div>
    ),
  ],
  args: {
    name: "Running shoes",
    href: "/products/RS-001",
    price: "59.00",
    stock: 24,
    currency: "USD",
    headingLevel: 2,
    priority: false,
    thumbnailUrl: SAMPLE_THUMBNAIL,
    imageUrl: SAMPLE_IMAGE,
  },
} satisfies Meta<typeof ProductCard>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const LowStock: Story = { args: { stock: 2 } };

export const OutOfStock: Story = { args: { stock: 0 } };

export const NoImage: Story = { args: { thumbnailUrl: null, imageUrl: null } };

export const LongName: Story = {
  args: { name: "Ultra lightweight trail running shoes with reinforced toe cap and breathable mesh" },
};

export const Loading: Story = { render: () => <ProductCardSkeleton /> };

export const ResponsiveGrid: Story = {
  parameters: { layout: "padded" },
  decorators: [
    (Story) => (
      <div className="w-full">
        <Story />
      </div>
    ),
  ],
  render: (args) => (
    <ul className="grid list-none grid-cols-1 gap-4 p-0 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {["RS-001", "RS-002", "RS-003", "RS-004"].map((sku, index) => (
        <li key={sku}>
          <ProductCard {...args} name={`Running shoes ${index + 1}`} href={`/products/${sku}`} />
        </li>
      ))}
    </ul>
  ),
};
