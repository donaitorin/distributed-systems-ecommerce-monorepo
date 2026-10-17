/**
 * @jest-environment node
 */
import { addCheckoutAddressAction, newAttemptKeyAction, placeOrderAction } from "../src/app/checkout/actions";
import { refreshCartCountAction } from "../src/app/orders/actions";

const requireSession = jest.fn();
const getSession = jest.fn();
const revalidatePath = jest.fn();
const server = {
  placeOrder: jest.fn(),
  addAddress: jest.fn(),
};

jest.mock("@ecommerce/auth/next", () => ({
  requireSession: (options: unknown) => requireSession(options) as unknown,
  getSession: () => getSession() as unknown,
}));
jest.mock("next/cache", () => ({ revalidatePath: (...args: unknown[]) => revalidatePath(...args) as unknown }));
jest.mock("../src/server/orders", () => ({ placeOrder: (...args: unknown[]) => server.placeOrder(...args) as unknown }));
jest.mock("../src/server/addresses", () => ({
  addAddress: (...args: unknown[]) => server.addAddress(...args) as unknown,
}));

beforeEach(() => {
  jest.clearAllMocks();
  requireSession.mockResolvedValue({ userId: "u1", role: "customer" });
  getSession.mockResolvedValue({ userId: "u1", role: "customer" });
});

describe("checkout actions", () => {
  it("places the order through the server module", async () => {
    server.placeOrder.mockResolvedValue({ ok: true, orderId: "o1" });
    const input = { attemptKey: "k".repeat(10), addressId: "a", cardNumber: "4111111111111111", cartFingerprint: "" };

    expect(await placeOrderAction(input)).toEqual({ ok: true, orderId: "o1" });
    expect(server.placeOrder).toHaveBeenCalledWith(input);
  });

  it("creates a new attempt key on the server, for a signed in customer only", async () => {
    const first = await newAttemptKeyAction();
    const second = await newAttemptKeyAction();

    expect(requireSession).toHaveBeenCalledWith({ loginPath: "/login" });
    expect(first).toMatch(/^[0-9a-f-]{36}$/);
    expect(second).not.toBe(first);
  });

  it("saves an address added during checkout, returning to checkout if the session expired", async () => {
    server.addAddress.mockResolvedValue({ ok: true });

    await addCheckoutAddressAction({ recipient_name: "Ada" } as never);

    expect(server.addAddress).toHaveBeenCalledWith({ recipient_name: "Ada" }, "/checkout");
  });
});

describe("refreshCartCountAction", () => {
  it("renders the header again for a signed in customer", async () => {
    await refreshCartCountAction();

    expect(revalidatePath).toHaveBeenCalledWith("/", "layout");
  });

  it("does nothing without a session", async () => {
    getSession.mockResolvedValue(null);

    await refreshCartCountAction();

    expect(revalidatePath).not.toHaveBeenCalled();
  });
});
