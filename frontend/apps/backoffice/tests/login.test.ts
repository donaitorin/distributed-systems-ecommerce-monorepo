/**
 * @jest-environment node
 */
import { signInAction } from "../src/app/login/actions";
import { signOutAction } from "../src/app/session-actions";
import { performSignIn } from "../src/server/login";

const signIn = jest.fn();
const signOut = jest.fn();

jest.mock("@ecommerce/auth/next", () => ({
  signIn: (...args: unknown[]) => signIn(...args) as unknown,
  signOut: () => signOut() as unknown,
}));

jest.mock("next/navigation", () => ({
  redirect: (path: string) => {
    throw new Error(`NEXT_REDIRECT ${path}`);
  },
}));

function form(values: Record<string, string>): FormData {
  const data = new FormData();
  for (const [name, value] of Object.entries(values)) {
    data.set(name, value);
  }
  return data;
}

const ADMIN = { ok: true, session: { userId: "u1", role: "admin" } };
const CREDENTIALS = { email: "admin@example.com", password: "secret-password" };

beforeEach(() => {
  signIn.mockReset();
  signOut.mockReset();
});

describe("performSignIn", () => {
  it("signs in the administrator and redirects to the requested internal page", async () => {
    signIn.mockResolvedValue(ADMIN);

    await expect(performSignIn({}, form({ ...CREDENTIALS, email: "  admin@example.com ", next: "/products?q=a" }))).rejects.toThrow(
      "NEXT_REDIRECT /products?q=a",
    );

    expect(signIn).toHaveBeenCalledWith(CREDENTIALS);
  });

  it.each([
    ["an absolute URL", "https://evil.example"],
    ["a protocol relative URL", "//evil.example"],
    ["a protocol relative URL behind the zone", "/admin//evil.example"],
    ["a backslash", "/\\evil.example"],
    ["nothing", ""],
  ])("never redirects to %s after signing in", async (_label, next) => {
    signIn.mockResolvedValue(ADMIN);

    await expect(performSignIn({}, form({ ...CREDENTIALS, next }))).rejects.toThrow("NEXT_REDIRECT /");
    await expect(performSignIn({}, form({ ...CREDENTIALS, next }))).rejects.not.toThrow(/evil/);
  });

  it("strips the zone prefix because the router adds it back", async () => {
    signIn.mockResolvedValue(ADMIN);

    await expect(performSignIn({}, form({ ...CREDENTIALS, next: "/admin/products" }))).rejects.toThrow(
      "NEXT_REDIRECT /products",
    );
  });

  it("asks for missing fields without calling the API", async () => {
    const state = await performSignIn({}, form({ email: "", password: "" }));

    expect(state).toEqual({
      email: "",
      fieldErrors: { email: "Enter your email address", password: "Enter your password" },
    });
    expect(signIn).not.toHaveBeenCalled();
  });

  it("treats a missing form value as empty", async () => {
    const state = await performSignIn({}, new FormData());

    expect(state.fieldErrors).toBeDefined();
  });

  it("answers the same generic message for a wrong password and an unknown email", async () => {
    signIn.mockResolvedValue({ ok: false, problem: { status: 401, title: "Invalid credentials" } });

    const state = await performSignIn({}, form(CREDENTIALS));

    expect(state).toEqual({ email: "admin@example.com", error: "The email or password is incorrect." });
    expect(JSON.stringify(state)).not.toContain("secret-password");
  });

  it("tells the administrator when to retry after a rate limit", async () => {
    signIn.mockResolvedValue({ ok: false, problem: { status: 429, title: "Too Many Requests" }, retryAfterSeconds: 42 });

    expect(await performSignIn({}, form(CREDENTIALS))).toMatchObject({
      error: "Too many sign in attempts. Try again in 42 seconds.",
    });
  });

  it("still explains a rate limit without a retry time", async () => {
    signIn.mockResolvedValue({ ok: false, problem: { status: 429, title: "Too Many Requests" } });

    expect(await performSignIn({}, form(CREDENTIALS))).toMatchObject({
      error: "Too many sign in attempts. Wait a minute and try again.",
    });
  });

  it("reports an unavailable service for other API errors and for thrown errors", async () => {
    signIn.mockResolvedValueOnce({ ok: false, problem: { status: 503, title: "Down" } });
    expect(await performSignIn({}, form(CREDENTIALS))).toMatchObject({ error: expect.stringContaining("not available") as string });

    signIn.mockRejectedValueOnce(new Error("network"));
    expect(await performSignIn({}, form(CREDENTIALS))).toMatchObject({ error: expect.stringContaining("not available") as string });
  });

  it("does not let a customer into the backoffice", async () => {
    signIn.mockResolvedValue({ ok: true, session: { userId: "u2", role: "customer" } });

    expect(await performSignIn({}, form(CREDENTIALS))).toMatchObject({
      error: "This account does not have access to the backoffice.",
    });
  });
});

describe("server actions", () => {
  it("signInAction delegates to the sign in logic", async () => {
    signIn.mockResolvedValue(ADMIN);

    await expect(signInAction({}, form(CREDENTIALS))).rejects.toThrow("NEXT_REDIRECT /");
  });

  it("signOutAction clears the session and goes to the login page, even if the API call fails", async () => {
    signOut.mockResolvedValue(undefined);
    await expect(signOutAction()).rejects.toThrow("NEXT_REDIRECT /login");

    signOut.mockRejectedValue(new Error("offline"));
    await expect(signOutAction()).rejects.toThrow("NEXT_REDIRECT /login");
    expect(signOut).toHaveBeenCalledTimes(2);
  });
});
