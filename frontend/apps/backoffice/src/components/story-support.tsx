import type { Decorator } from "@storybook/nextjs-vite";
import { NuqsTestingAdapter } from "nuqs/adapters/testing";
import { NavigationContext } from "./navigation";
import { NotificationsProvider } from "./notifications";

export function withAppProviders(searchParams = ""): Decorator {
  return function WithAppProviders(Story) {
    return (
      <NuqsTestingAdapter searchParams={searchParams} hasMemory>
        <NavigationContext value={{ push: () => undefined, refresh: () => undefined }}>
          <NotificationsProvider>
            <Story />
          </NotificationsProvider>
        </NavigationContext>
      </NuqsTestingAdapter>
    );
  };
}

const PLACEHOLDER_SVG =
  "<svg xmlns='http://www.w3.org/2000/svg' width='400' height='400'><rect width='400' height='400' fill='#e8dfd0'/></svg>";
export const STORY_IMAGE = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(PLACEHOLDER_SVG)}`;

export const STORY_CATEGORIES = [
  { id: "7d9f8a5e-0f1c-4b0e-9a5d-2f6a4c1b3e10", name: "Sports", slug: "sports" },
  { id: "5a1b2c3d-0000-4000-8000-000000000002", name: "Toys", slug: "toys" },
];

export const STORY_PRODUCT = {
  sku: "RS-001",
  name: "Running shoes",
  description: "Light and fast",
  category: STORY_CATEGORIES[0] ?? null,
  price: "59.00",
  stock: 24,
  weight_kg: "0.800",
  image_url: null,
  thumbnail_url: null,
  version: 3,
  created_at: "2026-10-14T10:00:00Z",
  updated_at: "2026-10-15T10:00:00Z",
};

