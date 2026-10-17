/**
 * @jest-environment node
 */
import { addToCartAction, clearCartAction, removeItemAction, setQuantityAction } from "../src/app/cart/actions";

const getSession = jest.fn();
const revalidatePath = jest.fn();
const server = {
  addToCart: jest.fn(),
  clearCart: jest.fn(),
  removeItem: jest.fn(),
  setQuantity: jest.fn(),
};

jest.mock("@ecommerce/auth/next", () => ({ getSession: () => getSession() as unknown }));
jest.mock("next/cache", () => ({ revalidatePath: (...args: unknown[]) => revalidatePath(...args) as unknown }));
jest.mock("next/navigation", () => ({
  redirect: (path: string) => {
    throw new Error(`NEXT_REDIRECT ${path}`);
  },
}));
jest.mock("../src/server/cart", () => ({
  addToCart: (...args: unknown[]) => server.addToCart(...args) as unknown,
  clearCart: () => server.clearCart() as unknown,
  removeItem: (...args: unknown[]) => server.removeItem(...args) as unknown,
  setQuantity: (...args: unknown[]) => server.setQuantity(...args) as unknown,
}));

beforeEach(() => {
  jest.clearAllMocks();
  getSession.mockResolvedValue({ userId: "u1", role: "customer" });
});

describe("cart actions", () => {
  it("refresh the header count after changing the cart", async () => {
    server.setQuantity.mockResolvedValue({ ok: true });
    server.removeItem.mockResolvedValue({ ok: true });
    server.clearCart.mockResolvedValue({ ok: true });

    await setQuantityAction("RS-001", 2, "64.50");
    await removeItemAction("RS-001");
    await clearCartAction();

    expect(server.setQuantity).toHaveBeenCalledWith("RS-001", 2, "64.50");
    expect(server.removeItem).toHaveBeenCalledWith("RS-001");
    expect(revalidatePath).toHaveBeenCalledTimes(3);
    expect(revalidatePath).toHaveBeenCalledWith("/", "layout");
  });

  it("adds for a signed in customer and returns to the product if the session expires", async () => {
    server.addToCart.mockResolvedValue({ ok: true, quantity: 1, capped: false });

    expect(await addToCartAction("RS-001", 1)).toEqual({ ok: true, quantity: 1, capped: false });
    expect(server.addToCart).toHaveBeenCalledWith("RS-001", 1, "/products/RS-001");
    expect(revalidatePath).toHaveBeenCalledWith("/", "layout");
  });

  it("sends a visitor to the login page and back to the product, touching nothing", async () => {
    getSession.mockResolvedValue(null);

    await expect(addToCartAction("RS 001", 1)).rejects.toThrow("NEXT_REDIRECT /login?next=%2Fproducts%2FRS%2520001");
    expect(server.addToCart).not.toHaveBeenCalled();
    expect(revalidatePath).not.toHaveBeenCalled();
  });
});
