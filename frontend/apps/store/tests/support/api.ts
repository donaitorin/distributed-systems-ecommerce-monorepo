import type { Category, Product, ProductPage } from "@ecommerce/web-core";

export const CATEGORY: Category = { id: "7d9f8a5e-0f1c-4b0e-9a5d-2f6a4c1b3e10", name: "Footwear", slug: "footwear" };
export const OTHER_CATEGORY: Category = { id: "5a1b2c3d-0000-4000-8000-000000000002", name: "Toys", slug: "toys" };

export function product(overrides: Partial<Product> = {}): Product {
  return {
    sku: "RS-001",
    name: "Running shoes",
    description: "Light and fast",
    category: CATEGORY,
    price: "59.00",
    stock: 24,
    weight_kg: "0.800",
    image_url: "/media/products/RS-001/a-1200.webp",
    thumbnail_url: "/media/products/RS-001/a-400.webp",
    version: 3,
    created_at: "2026-10-14T10:00:00Z",
    updated_at: "2026-10-15T10:00:00Z",
    ...overrides,
  };
}

export function productPage(overrides: Partial<ProductPage> = {}): ProductPage {
  return {
    items: [product(), product({ sku: "TY-002", name: "Toy robot", price: "19.50", stock: 0, image_url: null, thumbnail_url: null })],
    next_cursor: null,
    prev_cursor: null,
    total: 2,
    total_exact: true,
    ...overrides,
  };
}

export function json(body: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", ...headers },
  });
}

export function problem(status: number, title: string, extra: Record<string, unknown> = {}): Response {
  return new Response(JSON.stringify({ type: "about:blank", title, status, ...extra }), {
    status,
    headers: { "content-type": "application/problem+json" },
  });
}

export type Route = {
  method: string;
  path: string | RegExp;
  respond: (request: { url: URL; init: RequestInit }) => Response | Promise<Response>;
};

export function mockFetch(routes: Route[]) {
  const calls: { method: string; url: URL; init: RequestInit }[] = [];
  const implementation = jest.fn((input: string | URL | Request, init: RequestInit = {}) => {
    const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.href : input.url);
    const method = (init.method ?? "GET").toUpperCase();
    calls.push({ method, url, init });
    const route = routes.find(
      (candidate) =>
        candidate.method === method &&
        (typeof candidate.path === "string" ? candidate.path === url.pathname : candidate.path.test(url.pathname)),
    );
    if (!route) {
      return Promise.reject(new TypeError(`unexpected request ${method} ${url.pathname}`));
    }
    return Promise.resolve(route.respond({ url, init }));
  });
  global.fetch = implementation;
  return { calls, implementation };
}

export const PROFILE = {
  user_id: "0f6c1f0e-7a52-4f33-9c2a-5d9c3b1e7a10",
  email: "ada@example.com",
  role: "customer",
  name: "Ada Lovelace",
  phone: "+34600123456",
  created_at: "2026-10-14T10:00:00Z",
  updated_at: "2026-10-15T10:00:00Z",
};
