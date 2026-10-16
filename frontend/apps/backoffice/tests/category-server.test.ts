/**
 * @jest-environment node
 */
import { createCategoryAction } from "../src/app/categories/actions";
import { createCategory } from "../src/server/category-actions";
import { CATEGORY, headerOf, json, mockFetch, problem } from "./support/api";

jest.mock("@ecommerce/auth/next", () => ({
  authRuntime: () => ({ config: { apiBaseUrl: "http://gateway.test" } }),
  authorizationHeaders: () => Promise.resolve({ authorization: "Bearer t" }),
}));

jest.mock("next/navigation", () => ({
  redirect: (path: string) => {
    throw new Error(`NEXT_REDIRECT ${path}`);
  },
}));

describe("createCategory", () => {
  it("posts the normalized name and returns the category", async () => {
    const api = mockFetch([{ method: "POST", path: "/api/v1/categories", respond: () => json(CATEGORY, 201) }]);

    expect(await createCategory({ name: "  Home   goods " })).toEqual({ ok: true, category: CATEGORY });
    expect(JSON.parse(api.calls[0]?.init.body as string)).toEqual({ name: "Home goods" });
    expect(headerOf(api.calls[0]?.init ?? {}, "authorization")).toBe("Bearer t");
  });

  it("validates before calling the API", async () => {
    const api = mockFetch([]);

    expect(await createCategory({ name: "   " })).toMatchObject({
      ok: false,
      status: 422,
      fieldErrors: { name: "Name is required" },
    });
    expect(api.calls).toHaveLength(0);
  });

  it("returns a duplicate as a 409 failure", async () => {
    mockFetch([{ method: "POST", path: "/api/v1/categories", respond: () => problem(409, "Category already exists") }]);

    expect(await createCategory({ name: "Sports" })).toMatchObject({ ok: false, status: 409 });
  });

  it("sends an expired session to the login page", async () => {
    mockFetch([{ method: "POST", path: "/api/v1/categories", respond: () => problem(401, "Unauthorized") }]);

    await expect(createCategory({ name: "Sports" })).rejects.toThrow("NEXT_REDIRECT /login?reason=expired");
  });

  it("is what the server action runs", async () => {
    mockFetch([{ method: "POST", path: "/api/v1/categories", respond: () => json(CATEGORY, 201) }]);

    expect(await createCategoryAction({ name: "Sports" })).toMatchObject({ ok: true });
  });
});
