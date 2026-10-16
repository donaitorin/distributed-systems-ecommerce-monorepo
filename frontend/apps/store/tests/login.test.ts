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

const CUSTOMER = { ok: true, session: { userId: "u1", role: "customer" } };
const CREDENTIALS = { email: "ada@example.com", password: "a-long-password" };

beforeEach(() => {
  signIn.mockReset();
  signOut.mockReset();
});

describe("performSignIn", () => {
  it("signs in and goes to the requested internal page", async () => {
    signIn.mockResolvedValue(CUSTOMER);

    await expect(performSignIn({}, form({ ...CREDENTIALS, email: "  ada@example.com ", next: "/account" }))).rejects.toThrow(
      "NEXT_REDIRECT /account",
    );

    expect(signIn).toHaveBeenCalledWith(CREDENTIALS);
  });

  it("goes to the products page when there is no next page", async () => {
    signIn.mockResolvedValue(CUSTOMER);

    await expect(performSignIn({}, form(CREDENTIALS))).rejects.toThrow("NEXT_REDIRECT /products");
  });

  it("lets an administrator browse the store too", async () => {
    signIn.mockResolvedValue({ ok: true, session: { userId: "u2", role: "admin" } });

    await expect(performSignIn({}, form(CREDENTIALS))).rejects.toThrow("NEXT_REDIRECT /products");
  });

  it.each([
    ["an absolute URL", "https://evil.example"],
    ["a protocol relative URL", "//evil.example"],
    ["a backslash", "/\\evil.example"],
    ["the login page itself", "/login"],
    ["nothing", ""],
  ])("never redirects to %s after signing in", async (_label, next) => {
    signIn.mockResolvedValue(CUSTOMER);

    await expect(performSignIn({}, form({ ...CREDENTIALS, next }))).rejects.toThrow("NEXT_REDIRECT /products");
  });

  it("asks for missing fields without calling the API", async () => {
    expect(await performSignIn({}, form({ email: "", password: "" }))).toEqual({
      email: "",
      fieldErrors: { email: "Enter your email address", password: "Enter your password" },
    });
    expect(signIn).not.toHaveBeenCalled();
  });

  it("treats a missing form value as empty", async () => {
    expect((await performSignIn({}, new FormData())).fieldErrors).toBeDefined();
  });

  it("answers the same generic message for a wrong password and an unknown email", async () => {
    signIn.mockResolvedValue({ ok: false, problem: { status: 401, title: "Invalid credentials" } });

    const state = await performSignIn({}, form(CREDENTIALS));

    expect(state).toEqual({ email: "ada@example.com", error: "The email or password is incorrect." });
    expect(JSON.stringify(state)).not.toContain("a-long-password");
  });

  it("tells the customer when to retry after a rate limit, with or without a retry time", async () => {
    signIn.mockResolvedValueOnce({ ok: false, problem: { status: 429, title: "Too Many Requests" }, retryAfterSeconds: 42 });
    expect(await performSignIn({}, form(CREDENTIALS))).toMatchObject({
      error: "Too many sign in attempts. Try again in 42 seconds.",
    });

    signIn.mockResolvedValueOnce({ ok: false, problem: { status: 429, title: "Too Many Requests" } });
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
});

describe("server actions", () => {
  it("signInAction delegates to the sign in logic", async () => {
    signIn.mockResolvedValue(CUSTOMER);

    await expect(signInAction({}, form(CREDENTIALS))).rejects.toThrow("NEXT_REDIRECT /products");
  });

  it("signOutAction clears the session and goes to the products page, even if the API call fails", async () => {
    signOut.mockResolvedValue(undefined);
    await expect(signOutAction()).rejects.toThrow("NEXT_REDIRECT /products");

    signOut.mockRejectedValue(new Error("offline"));
    await expect(signOutAction()).rejects.toThrow("NEXT_REDIRECT /products");
    expect(signOut).toHaveBeenCalledTimes(2);
  });
});
