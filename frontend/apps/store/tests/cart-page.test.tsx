import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";
import CartPage from "../src/app/cart/page";
import { cart } from "./support/cart";

const requireSession = jest.fn();
const loadCart = jest.fn();

jest.mock("@ecommerce/auth/next", () => ({
  requireSession: (options: unknown) => requireSession(options) as unknown,
}));
jest.mock("../src/server/cart", () => ({ loadCart: (returnTo: string) => loadCart(returnTo) as unknown }));
jest.mock("../src/app/cart/actions", () => ({
  setQuantityAction: jest.fn(),
  removeItemAction: jest.fn(),
  clearCartAction: jest.fn(),
}));

beforeEach(() => {
  requireSession.mockReset();
  loadCart.mockReset();
  requireSession.mockResolvedValue({ userId: "u1", role: "customer" });
  loadCart.mockResolvedValue(cart());
});

describe("cart page", () => {
  it("requires a session and shows the cart", async () => {
    const { container } = render(await CartPage());

    expect(requireSession).toHaveBeenCalledWith({ loginPath: "/login" });
    expect(loadCart).toHaveBeenCalledWith("/cart");
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByText("Subtotal (3 items)")).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("explains a cart that could not be loaded, with a way to retry and no lines", async () => {
    loadCart.mockResolvedValue({ ok: false, kind: "unavailable" });

    const { container } = render(await CartPage());

    expect(screen.getByRole("alert")).toHaveTextContent("could not be loaded");
    expect(screen.getByRole("link", { name: "Try again" })).toHaveAttribute("href", "/cart");
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });
});
