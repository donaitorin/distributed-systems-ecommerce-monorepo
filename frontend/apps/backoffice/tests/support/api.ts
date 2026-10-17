import type { Category, ImportView, OrderDetail, OrderRow, Payment, Product, UserProfile } from "../../src/lib/types";

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

export function profile(overrides: Partial<UserProfile> = {}): UserProfile {
  return {
    user_id: "11111111-1111-4111-8111-111111111111",
    email: "ada@example.com",
    name: "Ada Lovelace",
    phone: null,
    role: "customer",
    created_at: "2026-10-10T12:00:00Z",
    updated_at: "2026-10-11T12:00:00Z",
    ...overrides,
  };
}

export function importView(overrides: Record<string, unknown> = {}, summary: Record<string, unknown> | null = {}): ImportView {
  return {
    id: "9f0c1d2e-3a4b-4c5d-8e6f-7a8b9c0d1e2f",
    filename: "products.csv",
    sha256: "a".repeat(64),
    size_bytes: 12_345,
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
    links: {
      self: "/api/v1/imports/x",
      problems: "/api/v1/imports/x/problems",
      problems_csv: "/api/v1/imports/x/problems.csv",
      confirm: "/api/v1/imports/x/confirm",
    },
    summary:
      summary === null
        ? null
        : {
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
            unknown_categories: [],
            ...summary,
          },
    ...overrides,
  };
}

export const ORDER_ID = "6f1c2f64-3f0e-4c1a-9d52-7a1b8c9d0e21";
export const CUSTOMER_ID = "0f6c1f0e-7a52-4f33-9c2a-5d9c3b1e7a10";

export function orderRow(overrides: Partial<OrderRow> = {}): OrderRow {
  return {
    id: ORDER_ID,
    customer_id: CUSTOMER_ID,
    customer_email: "ada@example.com",
    status: "CONFIRMED",
    total: "137.50",
    currency: "USD",
    item_count: 3,
    created_at: "2026-10-17T10:00:00Z",
    updated_at: "2026-10-17T10:00:09Z",
    ...overrides,
  };
}

export function orderDetail(overrides: Partial<OrderDetail> = {}): OrderDetail {
  return {
    ...orderRow(),
    card_last4: "1111",
    shipping_address: {
      recipient_name: "Ada Lovelace",
      line1: "12 Analytical St",
      line2: "Floor 2",
      city: "London",
      region: "Greater London",
      postal_code: "N1 9GU",
      country: "GB",
      phone: "+442071234567",
    },
    cancel_reason: null,
    refunded_at: null,
    lines: [
      { sku: "RS-001", name: "Running shoes", quantity: 2, unit_price: "59.00", line_total: "118.00" },
      { sku: "TY-002", name: null, quantity: 1, unit_price: "19.50", line_total: "19.50" },
    ],
    history: [
      { from_status: null, to_status: "PENDING", reason: "order created", at: "2026-10-17T10:00:00Z" },
      { from_status: "PENDING", to_status: "STOCK_RESERVED", reason: "stock reserved", at: "2026-10-17T10:00:02Z" },
      { from_status: "STOCK_RESERVED", to_status: "CONFIRMED", reason: "order confirmed", at: "2026-10-17T10:00:09Z" },
    ],
    ...overrides,
  };
}

export function payment(overrides: Partial<Payment> = {}): Payment {
  return {
    id: "aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa",
    order_id: ORDER_ID,
    status: "SUCCEEDED",
    amount: "137.50",
    currency: "USD",
    card_last4: "1111",
    failure_reason: null,
    refunded_at: null,
    created_at: "2026-10-17T10:00:03Z",
    updated_at: "2026-10-17T10:00:08Z",
    ...overrides,
  };
}
