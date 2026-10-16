import type { Decorator } from "@storybook/nextjs-vite";
import { NuqsTestingAdapter } from "nuqs/adapters/testing";
import type { Product, ProductPage } from "@ecommerce/web-core";

export function withUrl(searchParams = ""): Decorator {
  return function WithUrl(Story) {
    return (
      <NuqsTestingAdapter searchParams={searchParams} hasMemory>
        <Story />
      </NuqsTestingAdapter>
    );
  };
}

const PLACEHOLDER_SVG =
  "<svg xmlns='http://www.w3.org/2000/svg' width='400' height='400'><rect width='400' height='400' fill='#e8dfd0'/></svg>";
export const STORY_IMAGE = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(PLACEHOLDER_SVG)}`;

export const STORY_CATEGORIES = [
  { id: "7d9f8a5e-0f1c-4b0e-9a5d-2f6a4c1b3e10", name: "Footwear", slug: "footwear" },
  { id: "5a1b2c3d-0000-4000-8000-000000000002", name: "Toys", slug: "toys" },
];

export const STORY_PRODUCT: Product = {
  sku: "RS-001",
  name: "Running shoes",
  description: "Light and fast. Built for long distances on road and trail.",
  category: STORY_CATEGORIES[0] ?? null,
  price: "59.00",
  stock: 24,
  weight_kg: "0.800",
  image_url: STORY_IMAGE,
  thumbnail_url: STORY_IMAGE,
  version: 3,
  created_at: "2026-10-14T10:00:00Z",
  updated_at: "2026-10-15T10:00:00Z",
};

export const STORY_PAGE: ProductPage = {
  items: [
    STORY_PRODUCT,
    { ...STORY_PRODUCT, sku: "RS-002", name: "Trail shoes", price: "89.90", stock: 3 },
    { ...STORY_PRODUCT, sku: "TY-002", name: "Toy robot", price: "19.50", stock: 0, image_url: null, thumbnail_url: null, category: STORY_CATEGORIES[1] ?? null },
    { ...STORY_PRODUCT, sku: "RS-004", name: "Ultra lightweight trail running shoes with reinforced toe cap", price: "120.00" },
  ],
  next_cursor: "NEXT",
  prev_cursor: null,
  total: 1200,
  total_exact: false,
};
