/**
 * @jest-environment node
 */
import { updateProfileAction } from "../src/app/account/actions";
import { loadProfile, updateProfile } from "../src/server/profile";
import { json, mockFetch, problem, PROFILE } from "./support/api";

jest.mock("@ecommerce/auth/next", () => ({
  authRuntime: () => ({ config: { apiBaseUrl: "http://gateway.test" } }),
  authorizationHeaders: () => Promise.resolve({ authorization: "Bearer t", "x-forwarded-for": "203.0.113.7" }),
}));

jest.mock("next/navigation", () => ({
  redirect: (path: string) => {
    throw new Error(`NEXT_REDIRECT ${path}`);
  },
}));

const ME = { method: "GET", path: "/api/v1/accounts/me" };

describe("loadProfile", () => {
  it("reads the profile of the signed in customer with the bearer token", async () => {
    const api = mockFetch([{ ...ME, respond: () => json(PROFILE) }]);

    expect(await loadProfile()).toEqual(PROFILE);
    expect(new Headers(api.calls[0]?.init.headers).get("authorization")).toBe("Bearer t");
  });

  it("sends an expired session to the login page and back to the account afterwards", async () => {
    mockFetch([{ ...ME, respond: () => problem(401, "Unauthorized") }]);

    await expect(loadProfile()).rejects.toThrow("NEXT_REDIRECT /login?next=%2Faccount&reason=expired");
  });

  it("returns a failure for other errors and for an unreachable gateway", async () => {
    mockFetch([{ ...ME, respond: () => problem(503, "Down") }]);
    expect(await loadProfile()).toMatchObject({ ok: false, status: 503 });

    global.fetch = jest.fn(() => Promise.reject(new TypeError("fetch failed")));
    expect(await loadProfile()).toMatchObject({ ok: false, status: null });
  });
});

describe("updateProfile", () => {
  const PATCH = { method: "PATCH", path: "/api/v1/accounts/me" };

  it("sends the name and the phone, clearing a blank phone", async () => {
    const api = mockFetch([{ ...PATCH, respond: () => json({ ...PROFILE, phone: null }) }]);

    const result = await updateProfile({ name: " Ada ", phone: "" });

    expect(result).toEqual({ ok: true, profile: { ...PROFILE, phone: null } });
    expect(JSON.parse(api.calls[0]?.init.body as string)).toEqual({ name: "Ada", phone: null });
  });

  it("does not call the API for values the form rules refuse", async () => {
    const api = mockFetch([]);

    expect(await updateProfile({ name: " ", phone: "123" })).toMatchObject({
      ok: false,
      status: 422,
      fieldErrors: { name: "Enter your name", phone: expect.stringContaining("country code") as string },
    });
    expect(api.calls).toHaveLength(0);
  });

  it("maps the API's field errors, wording the phone one in plain language", async () => {
    mockFetch([
      {
        ...PATCH,
        respond: () =>
          problem(422, "Validation failed", {
            errors: [{ location: "body.phone", message: "phone must start with + and have 8 to 15 digits", type: "value_error" }],
          }),
      },
    ]);

    const result = await updateProfile({ name: "Ada", phone: "+34600123456" });

    expect(result).toMatchObject({ ok: false, status: 422, fieldErrors: { phone: expect.stringContaining("country code") as string } });
  });

  it("sends an expired session to the login page", async () => {
    mockFetch([{ ...PATCH, respond: () => problem(401, "Unauthorized") }]);

    await expect(updateProfile({ name: "Ada", phone: "" })).rejects.toThrow("NEXT_REDIRECT /login");
  });

  it("is available as a server action", async () => {
    mockFetch([{ ...PATCH, respond: () => json(PROFILE) }]);

    expect(await updateProfileAction({ name: "Ada Lovelace", phone: "+34600123456" })).toMatchObject({ ok: true });
  });
});
