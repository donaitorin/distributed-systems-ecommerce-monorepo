import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
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


export const withQueries: Decorator = function WithQueries(Story) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
  return (
    <QueryClientProvider client={client}>
      <Story />
    </QueryClientProvider>
  );
};

export const STORY_IMPORT = {
  id: "9f0c1d2e-3a4b-4c5d-8e6f-7a8b9c0d1e2f",
  filename: "sample-products.csv",
  sha256: "a".repeat(64),
  size_bytes: 14_336,
  status: "validated",
  created_by: "admin",
  created_at: "2026-10-16T10:00:00Z",
  updated_at: "2026-10-16T10:00:05Z",
  validated_at: "2026-10-16T10:00:05Z",
  confirmed_at: null,
  finished_at: null,
  failure_reason: null,
  problems: [],
  progress: { processed_rows: 0, created_rows: 0, updated_rows: 0, restored_rows: 0, unchanged_rows: 0 },
  links: { self: "", problems: "", problems_csv: "", confirm: "x" },
  summary: {
    rejected: false,
    rows_read: 97,
    blank_rows: 2,
    error_rows: 4,
    error_count: 4,
    warning_count: 3,
    duplicate_rows: 1,
    superseded_rows: 2,
    importable_rows: 88,
    to_create: 88,
    to_update: 0,
    to_restore: 0,
    unchanged: 0,
    truncated: false,
    unknown_categories: [{ value: "Gardening", rows: 2, suggestion: "Garden" }],
  },
};

export const STORY_PROBLEMS = {
  items: [
    { severity: "error", row: 7, column: "category", value: "Gardening", code: "unknown_category", reason: "unknown category Gardening" },
    { severity: "error", row: 16, column: "price", value: "free", code: "not_a_number", reason: "price must be a number" },
    { severity: "warning", row: 2, column: "sku", value: "RS-001", code: "superseded", reason: "superseded by row 36" },
  ],
  next_cursor: null,
};
