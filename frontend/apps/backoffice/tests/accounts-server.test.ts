/**
 * @jest-environment node
 */
import { changeUserRoleAction } from "../src/app/users/actions";
import { changeUserRole, loadUserPage } from "../src/server/accounts";
import { json, mockFetch, problem, profile } from "./support/api";

jest.mock("@ecommerce/auth/next", () => ({
  authRuntime: () => ({ config: { apiBaseUrl: "http://gateway.test" } }),
  authorizationHeaders: () => Promise.resolve({ authorization: "Bearer t" }),
}));

jest.mock("next/navigation", () => ({
  redirect: (path: string) => {
    throw new Error(`NEXT_REDIRECT ${path}`);
  },
}));

describe("loadUserPage", () => {
  it("sends the filters as query parameters", async () => {
    const api = mockFetch([
      { method: "GET", path: "/api/v1/accounts", respond: () => json({ items: [profile()], next_cursor: "n" }) },
    ]);

    const result = await loadUserPage({ email: "ada", role: "admin", limit: 50, cursor: "c" });

    expect(result).toMatchObject({ items: [{ email: "ada@example.com" }], next_cursor: "n" });
    expect(Object.fromEntries(api.calls[0]?.url.searchParams ?? [])).toEqual({
      email: "ada",
      role: "admin",
      limit: "50",
      cursor: "c",
    });
  });

  it("returns a rejected cursor as a failure and redirects when the session is gone", async () => {
    mockFetch([
      {
        method: "GET",
        path: "/api/v1/accounts",
        respond: () =>
          problem(422, "Invalid", { errors: [{ location: "query.cursor", message: "no match", type: "cursor_mismatch" }] }),
      },
    ]);
    expect(await loadUserPage({ email: null, role: null, limit: 25, cursor: "x" })).toMatchObject({
      ok: false,
      fieldErrors: { cursor: "no match" },
    });

    mockFetch([{ method: "GET", path: "/api/v1/accounts", respond: () => problem(403, "Forbidden") }]);
    await expect(loadUserPage({ email: null, role: null, limit: 25, cursor: null })).rejects.toThrow(
      "NEXT_REDIRECT /login?reason=forbidden",
    );
  });
});


describe("changeUserRole", () => {
  const ID = "11111111-1111-4111-8111-111111111111";

  it("patches the role through the auth service", async () => {
    const api = mockFetch([
      {
        method: "PATCH",
        path: `/api/v1/auth/users/${ID}/role`,
        respond: () => json({ id: ID, email: "ada@example.com", role: "admin" }),
      },
    ]);

    expect(await changeUserRole(ID, "admin")).toEqual({ ok: true, userId: ID, role: "admin" });
    expect(JSON.parse(api.calls[0]?.init.body as string)).toEqual({ role: "admin" });
    expect(await changeUserRoleAction(ID, "admin")).toMatchObject({ ok: true });
  });

  it.each([404, 409, 422])("returns %s as a failure", async (status) => {
    mockFetch([{ method: "PATCH", path: `/api/v1/auth/users/${ID}/role`, respond: () => problem(status, "Problem") }]);

    expect(await changeUserRole(ID, "customer")).toMatchObject({ ok: false, status });
  });
});
