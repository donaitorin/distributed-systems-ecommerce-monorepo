import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";
import CheckoutPage from "../src/app/checkout/page";
import { cart } from "./support/cart";
import { address } from "./support/addresses";

const requireSession = jest.fn();
const loadCart = jest.fn();
const loadAddresses = jest.fn();

jest.mock("@ecommerce/auth/next", () => ({ requireSession: (options: unknown) => requireSession(options) as unknown }));
jest.mock("next/navigation", () => jest.requireActual("./support/navigation-mock") as unknown);
jest.mock("../src/server/cart", () => ({ loadCart: (returnTo: string) => loadCart(returnTo) as unknown }));
jest.mock("../src/server/addresses", () => ({ loadAddresses: (returnTo: string) => loadAddresses(returnTo) as unknown }));
jest.mock("../src/app/checkout/actions", () => ({
  placeOrderAction: jest.fn(),
  newAttemptKeyAction: jest.fn(),
  addCheckoutAddressAction: jest.fn(),
}));

beforeEach(() => {
  requireSession.mockReset();
  loadCart.mockReset();
  loadAddresses.mockReset();
  requireSession.mockResolvedValue({ userId: "u1", role: "customer" });
  loadCart.mockResolvedValue(cart());
  loadAddresses.mockResolvedValue([address()]);
});

describe("checkout page", () => {
  it("requires a session and shows the cart, the addresses and the payment form", async () => {
    const { container } = render(await CheckoutPage());

    expect(requireSession).toHaveBeenCalledWith({ loginPath: "/login" });
    expect(loadCart).toHaveBeenCalledWith("/checkout");
    expect(loadAddresses).toHaveBeenCalledWith("/checkout");
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("radio", { name: /Ada Lovelace/ })).toBeChecked();
    expect(screen.getByLabelText("Card number")).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("gives every render its own attempt key", async () => {
    const randomUUID = jest.spyOn(crypto, "randomUUID");

    await CheckoutPage();
    await CheckoutPage();

    expect(randomUUID).toHaveBeenCalledTimes(2);
    expect(randomUUID.mock.results[0]?.value).not.toBe(randomUUID.mock.results[1]?.value);
    randomUUID.mockRestore();
  });

  it("explains an empty cart with a way back to the catalog and no form", async () => {
    loadCart.mockResolvedValue(cart([]));

    const { container } = render(await CheckoutPage());

    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 2, name: "Your cart is empty" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Browse products" })).toHaveAttribute("href", "/products");
    expect(screen.queryByLabelText("Card number")).not.toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it.each([
    ["the cart", () => loadCart.mockResolvedValue({ ok: false, kind: "unavailable" })],
    ["the addresses", () => loadAddresses.mockResolvedValue({ ok: false, status: 503, title: "Down", fieldErrors: {} })],
  ])("explains that checkout could not load when %s cannot be read", async (_label, arrange) => {
    arrange();

    const { container } = render(await CheckoutPage());

    expect(screen.getByRole("alert")).toHaveTextContent("Nothing was ordered");
    expect(screen.getByRole("link", { name: "Try again" })).toHaveAttribute("href", "/checkout");
    expect(screen.queryByLabelText("Card number")).not.toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });
});
