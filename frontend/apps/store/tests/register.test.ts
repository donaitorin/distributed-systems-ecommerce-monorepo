/**
 * @jest-environment node
 */
import { registerAction } from "../src/app/register/actions";
import { performRegister } from "../src/server/register";

const registerAccount = jest.fn();
const signIn = jest.fn();

jest.mock("@ecommerce/auth/next", () => ({
  registerAccount: (...args: unknown[]) => registerAccount(...args) as unknown,
  signIn: (...args: unknown[]) => signIn(...args) as unknown,
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

const CREDENTIALS = { email: "ada@example.com", password: "a-long-password" };
const REGISTERED = { ok: true, user: { id: "1", email: "ada@example.com", role: "customer" } };
const problem = (status: number, errors: object[] = [], extra: object = {}) => ({
  ok: false,
  problem: { type: "about:blank", title: "Problem", status, errors },
  ...extra,
});

beforeEach(() => {
  registerAccount.mockReset();
  signIn.mockReset();
});

describe("performRegister", () => {
  it("registers, signs in with the same credentials and goes to the requested page", async () => {
    registerAccount.mockResolvedValue(REGISTERED);
    signIn.mockResolvedValue({ ok: true, session: { userId: "1", role: "customer" } });

    await expect(performRegister({}, form({ ...CREDENTIALS, email: " ada@example.com ", next: "/account" }))).rejects.toThrow(
      "NEXT_REDIRECT /account",
    );

    expect(registerAccount).toHaveBeenCalledWith(CREDENTIALS);
    expect(signIn).toHaveBeenCalledWith(CREDENTIALS);
    expect(registerAccount.mock.invocationCallOrder[0]).toBeLessThan(signIn.mock.invocationCallOrder[0] as number);
  });

  it("goes to the products page without a next page and refuses hostile ones", async () => {
    registerAccount.mockResolvedValue(REGISTERED);
    signIn.mockResolvedValue({ ok: true, session: { userId: "1", role: "customer" } });

    await expect(performRegister({}, form(CREDENTIALS))).rejects.toThrow("NEXT_REDIRECT /products");
    await expect(performRegister({}, form({ ...CREDENTIALS, next: "//evil.example" }))).rejects.toThrow(
      "NEXT_REDIRECT /products",
    );
    await expect(performRegister({}, form({ ...CREDENTIALS, next: "/register" }))).rejects.toThrow(
      "NEXT_REDIRECT /products",
    );
  });

  it("asks for missing fields without calling the API", async () => {
    expect(await performRegister({}, form({ email: "", password: "" }))).toMatchObject({
      fieldErrors: { email: "Enter your email address", password: "Enter your password" },
    });
    expect(await performRegister({}, new FormData())).toMatchObject({ fieldErrors: expect.any(Object) as object });
    expect(registerAccount).not.toHaveBeenCalled();
  });

  it("puts a taken email on the email field and offers to sign in", async () => {
    registerAccount.mockResolvedValue(problem(409));

    expect(await performRegister({}, form(CREDENTIALS))).toEqual({
      email: "ada@example.com",
      fieldErrors: { email: expect.stringContaining("already exists") as string },
      emailTaken: true,
    });
    expect(signIn).not.toHaveBeenCalled();
  });

  it.each([
    ["too_short", "at least 10 characters"],
    ["too_common", "too easy to guess"],
    ["same_as_email", "cannot be the same as your email"],
  ])("explains the password rule %s in plain language", async (type, text) => {
    registerAccount.mockResolvedValue(problem(422, [{ location: "body.password", message: "technical", type }]));

    const state = await performRegister({}, form(CREDENTIALS));

    expect(state.fieldErrors?.password).toContain(text);
    expect(state.fieldErrors?.password).not.toContain("technical");
    expect(JSON.stringify(state)).not.toContain("a-long-password");
  });

  it("puts an invalid email on the email field", async () => {
    registerAccount.mockResolvedValue(problem(422, [{ location: "body.email", message: "must contain exactly one @", type: "invalid_email" }]));

    expect((await performRegister({}, form(CREDENTIALS))).fieldErrors?.email).toContain("valid email");
  });

  it("falls back to a general message for a 422 without field details", async () => {
    registerAccount.mockResolvedValue(problem(422));

    expect(await performRegister({}, form(CREDENTIALS))).toMatchObject({ error: expect.stringContaining("could not be created") as string });
  });

  it("tells the customer when to retry after a rate limit", async () => {
    registerAccount.mockResolvedValueOnce(problem(429, [], { retryAfterSeconds: 30 }));
    expect(await performRegister({}, form(CREDENTIALS))).toMatchObject({
      error: "Too many sign up attempts. Try again in 30 seconds.",
    });

    registerAccount.mockResolvedValueOnce(problem(429));
    expect(await performRegister({}, form(CREDENTIALS))).toMatchObject({
      error: "Too many sign up attempts. Wait a minute and try again.",
    });
  });

  it("reports an unavailable service for other errors and thrown errors", async () => {
    registerAccount.mockResolvedValueOnce(problem(503));
    expect(await performRegister({}, form(CREDENTIALS))).toMatchObject({ error: expect.stringContaining("not available") as string });

    registerAccount.mockRejectedValueOnce(new Error("network"));
    expect(await performRegister({}, form(CREDENTIALS))).toMatchObject({ error: expect.stringContaining("not available") as string });
  });

  it("says the account exists when signing in afterwards fails, instead of reporting a failed sign up", async () => {
    registerAccount.mockResolvedValue(REGISTERED);
    signIn.mockResolvedValueOnce({ ok: false, problem: { status: 503, title: "Down" } });
    expect(await performRegister({}, form(CREDENTIALS))).toMatchObject({ error: expect.stringContaining("account was created") as string });

    signIn.mockRejectedValueOnce(new Error("network"));
    expect(await performRegister({}, form(CREDENTIALS))).toMatchObject({ error: expect.stringContaining("account was created") as string });
  });

  it("registerAction delegates to the sign up logic", async () => {
    registerAccount.mockResolvedValue(problem(409));

    expect(await registerAction({}, form(CREDENTIALS))).toMatchObject({ emailTaken: true });
  });
});
