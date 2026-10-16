import type { Category, Product } from "../../src/lib/types";

export function json(body: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", ...headers },
  });
}

export function problem(status: number, title: string, extra: Record<string, unknown> = {}, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify({ type: "about:blank", title, status, ...extra }), {
    status,
    headers: { "content-type": "application/problem+json", ...headers },
  });
}

export const CATEGORY: Category = { id: "7d9f8a5e-0f1c-4b0e-9a5d-2f6a4c1b3e10", name: "Sports", slug: "sports" };

export function product(overrides: Partial<Product> = {}): Product {
  return {
    sku: "RS-001",
    name: "Running shoes",
    description: "Light and fast",
    category: CATEGORY,
    price: "59.00",
    stock: 24,
    weight_kg: "0.800",
    image_url: null,
    thumbnail_url: null,
    version: 3,
    created_at: "2026-10-14T10:00:00Z",
    updated_at: "2026-10-15T10:00:00Z",
    ...overrides,
  };
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

export function headerOf(init: RequestInit, name: string): string | undefined {
  const headers = init.headers as Record<string, string> | Headers | undefined;
  if (headers instanceof Headers) {
    return headers.get(name) ?? undefined;
  }
  return headers?.[name];
}
