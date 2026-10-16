/**
 * @jest-environment node
 */
import {
  createProduct,
  deleteProduct,
  removeProductImage,
  updateProduct,
} from "../src/server/product-actions";
import type { ProductFormValues } from "../src/lib/product-form";
import { CATEGORY, headerOf, json, mockFetch, problem, product } from "./support/api";

jest.mock("@ecommerce/auth/next", () => ({
  authRuntime: () => ({ config: { apiBaseUrl: "http://gateway.test" } }),
  authorizationHeaders: () => Promise.resolve({ authorization: "Bearer t" }),
}));

jest.mock("next/navigation", () => ({
  redirect: (path: string) => {
    throw new Error(`NEXT_REDIRECT ${path}`);
  },
}));

const VALUES: ProductFormValues = {
  sku: " rs-001 ",
  name: "  Running shoes ",
  description: "",
  categoryId: CATEGORY.id,
  price: "59.9",
  stock: "24",
  weightKg: "",
};

describe("createProduct", () => {
  it("posts the normalized body with the price as a decimal string and returns the etag", async () => {
    const api = mockFetch([
      { method: "POST", path: "/api/v1/products", respond: () => json(product(), 201, { etag: '"1"' }) },
    ]);

    const result = await createProduct(VALUES);

    expect(result).toMatchObject({ ok: true, etag: '"1"', product: { sku: "RS-001" } });
    const call = api.calls[0];
    expect(JSON.parse(call?.init.body as string)).toEqual({
      sku: "RS-001",
      name: "Running shoes",
      description: null,
      category_id: CATEGORY.id,
      price: "59.9",
      stock: 24,
      weight_kg: null,
    });
    expect(call?.init.body).toContain('"price":"59.9"');
    expect(headerOf(call?.init ?? {}, "authorization")).toBe("Bearer t");
  });

  it("falls back to the version when the response has no etag", async () => {
    mockFetch([{ method: "POST", path: "/api/v1/products", respond: () => json(product({ version: 7 }), 201) }]);

    expect(await createProduct(VALUES)).toMatchObject({ ok: true, etag: '"7"' });
  });

  it("validates before calling the API and keys the errors by API field name", async () => {
    const api = mockFetch([]);

    const result = await createProduct({ ...VALUES, price: "abc", categoryId: "x", weightKg: "1.2345" });

    expect(result).toMatchObject({
      ok: false,
      status: 422,
      fieldErrors: {
        price: expect.stringContaining("Enter a price") as string,
        category_id: expect.any(String) as string,
        weight_kg: expect.any(String) as string,
      },
    });
    expect(api.calls).toHaveLength(0);
  });

  it("returns the 409 for a SKU in use, also when it belongs to a deleted product", async () => {
    mockFetch([
      {
        method: "POST",
        path: "/api/v1/products",
        respond: () => problem(409, "SKU already exists", { detail: "SKU RS-001 is already in use, possibly by a retired product" }),
      },
    ]);

    expect(await createProduct(VALUES)).toMatchObject({ ok: false, status: 409 });
  });

  it("maps the API's field errors", async () => {
    mockFetch([
      {
        method: "POST",
        path: "/api/v1/products",
        respond: () =>
          problem(422, "Validation failed", {
            errors: [
              { location: "body.price", message: "must not be negative", type: "negative" },
              { location: "body.category_id", message: "unknown category", type: "unknown" },
              { location: "header.if-match", message: "ignored", type: "x" },
            ],
          }),
      },
    ]);

    const result = await createProduct(VALUES);

    expect(result).toMatchObject({
      ok: false,
      status: 422,
      fieldErrors: { price: "must not be negative", category_id: "unknown category" },
    });
  });

  it("sends an expired session to the login page", async () => {
    mockFetch([{ method: "POST", path: "/api/v1/products", respond: () => problem(401, "Unauthorized") }]);

    await expect(createProduct(VALUES)).rejects.toThrow("NEXT_REDIRECT /login?reason=expired");
  });

  it("sends a non-admin to the login page as forbidden", async () => {
    mockFetch([{ method: "POST", path: "/api/v1/products", respond: () => problem(403, "Forbidden") }]);

    await expect(createProduct(VALUES)).rejects.toThrow("NEXT_REDIRECT /login?reason=forbidden");
  });

  it("reports an unreachable API as a failure without a status", async () => {
    mockFetch([]);

    expect(await createProduct(VALUES)).toMatchObject({ ok: false, status: null });
  });

  it("rethrows unexpected errors", async () => {
    mockFetch([{ method: "POST", path: "/api/v1/products", respond: () => new Response("not json", { status: 201 }) }]);

    await expect(createProduct(VALUES)).rejects.toThrow("not valid JSON");
  });
});

describe("updateProduct", () => {
  it("sends If-Match with the etag it was given and returns the new etag", async () => {
    const api = mockFetch([
      { method: "PUT", path: "/api/v1/products/RS-001", respond: () => json(product({ version: 4 }), 200, { etag: '"4"' }) },
    ]);

    const result = await updateProduct("RS-001", '"3"', VALUES);

    expect(result).toMatchObject({ ok: true, etag: '"4"' });
    expect(headerOf(api.calls[0]?.init ?? {}, "if-match")).toBe('"3"');
    expect(JSON.parse(api.calls[0]?.init.body as string)).not.toHaveProperty("sku");
  });

  it("on 412 returns the conflict together with the latest version and its etag", async () => {
    mockFetch([
      { method: "PUT", path: "/api/v1/products/RS-001", respond: () => problem(412, "Precondition failed") },
      {
        method: "GET",
        path: "/api/v1/products/RS-001",
        respond: () => json(product({ name: "Trail shoes", version: 5 }), 200, { etag: '"5"' }),
      },
    ]);

    const result = await updateProduct("RS-001", '"3"', VALUES);

    expect(result).toMatchObject({
      ok: false,
      status: 412,
      latest: { etag: '"5"', value: { name: "Trail shoes" } },
    });
  });

  it("on 412 still reports the conflict when the latest version cannot be loaded", async () => {
    mockFetch([
      { method: "PUT", path: "/api/v1/products/RS-001", respond: () => problem(412, "Precondition failed") },
      { method: "GET", path: "/api/v1/products/RS-001", respond: () => problem(404, "Not found") },
    ]);

    const result = await updateProduct("RS-001", '"3"', VALUES);

    expect(result).toMatchObject({ ok: false, status: 412 });
    expect(result).not.toHaveProperty("latest");
  });

  it("returns other failures as they are, and validates first", async () => {
    mockFetch([{ method: "PUT", path: "/api/v1/products/RS-001", respond: () => problem(404, "Product not found") }]);

    expect(await updateProduct("RS-001", '"3"', VALUES)).toMatchObject({ ok: false, status: 404 });
    expect(await updateProduct("RS-001", '"3"', { ...VALUES, name: "" })).toMatchObject({
      ok: false,
      status: 422,
      fieldErrors: { name: "Name is required" },
    });
  });
});

describe("deleteProduct", () => {
  it("deletes with If-Match", async () => {
    const api = mockFetch([{ method: "DELETE", path: "/api/v1/products/RS-001", respond: () => new Response(null, { status: 204 }) }]);

    expect(await deleteProduct("RS-001", '"3"')).toEqual({ ok: true });
    expect(headerOf(api.calls[0]?.init ?? {}, "if-match")).toBe('"3"');
  });

  it("reports a stale version", async () => {
    mockFetch([{ method: "DELETE", path: "/api/v1/products/RS-001", respond: () => problem(412, "Precondition failed") }]);

    expect(await deleteProduct("RS-001", '"1"')).toMatchObject({ ok: false, status: 412 });
  });
});

describe("removeProductImage", () => {
  it("returns the product with the etag the image endpoint answered", async () => {
    const api = mockFetch([
      { method: "DELETE", path: "/api/v1/products/RS-001/image", respond: () => json(product({ version: 5 }), 200, { etag: '"5"' }) },
    ]);

    expect(await removeProductImage("RS-001", '"4"')).toMatchObject({ ok: true, etag: '"5"' });
    expect(headerOf(api.calls[0]?.init ?? {}, "if-match")).toBe('"4"');
  });

  it("reports 404 when there is no image", async () => {
    mockFetch([{ method: "DELETE", path: "/api/v1/products/RS-001/image", respond: () => problem(404, "No image") }]);

    expect(await removeProductImage("RS-001", '"4"')).toMatchObject({ ok: false, status: 404 });
  });
});
