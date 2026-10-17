import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { CartView } from "../src/components/cart/cart-view";
import type { CartActions, CartFlag, CartResult } from "../src/lib/cart";
import { cart, line } from "./support/cart";
import { settled } from "@ecommerce/web-core/testing";

function actions(overrides: Partial<CartActions> = {}): jest.Mocked<CartActions> {
  return {
    setQuantity: jest.fn().mockResolvedValue({ ok: true, cart: cart() }),
    removeItem: jest.fn().mockResolvedValue({ ok: true, cart: cart() }),
    clearCart: jest.fn().mockResolvedValue({ ok: true }),
    ...overrides,
  } as jest.Mocked<CartActions>;
}

const flagged = (flags: CartFlag[]) => cart([line({ flags }), line({ sku: "TY-002", name: "Toy robot" })]);

describe("CartView", () => {
  it("lists every line with image, name, price, quantity, total, and the subtotal", async () => {
    const { container } = render(<CartView cart={cart()} actions={actions()} />);

    expect(screen.getByRole("heading", { level: 1, name: "Your cart" })).toBeInTheDocument();
    const items = within(screen.getByRole("list", { name: "Items in your cart" })).getAllByRole("listitem", {});
    expect(items.length).toBeGreaterThanOrEqual(2);
    expect(screen.getByRole("link", { name: "Running shoes" })).toHaveAttribute("href", "/products/RS-001");
    expect(screen.getByRole("img", { name: "Running shoes" })).toHaveAttribute("src", "/media/products/RS-001/a-400.webp");
    expect(screen.getByText("$118.00")).toBeInTheDocument();
    expect(screen.getByText("Subtotal (3 items)")).toBeInTheDocument();
    expect(screen.getByText("$137.50")).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("offers a Checkout action that opens the checkout page, and none for an empty cart", () => {
    const first = render(<CartView cart={cart()} actions={actions()} />);
    expect(screen.getByRole("link", { name: "Checkout" })).toHaveAttribute("href", "/checkout");
    first.unmount();

    render(<CartView cart={cart([])} actions={actions()} />);
    expect(screen.queryByRole("link", { name: "Checkout" })).not.toBeInTheDocument();
  });

  it("shows an empty state with a way back to the catalog", async () => {
    const { container } = render(<CartView cart={cart([])} actions={actions()} />);

    expect(screen.getByRole("heading", { level: 2, name: "Your cart is empty" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Browse products" })).toHaveAttribute("href", "/products");
    expect(screen.queryByRole("button", { name: "Clear cart" })).not.toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("changes a quantity and announces it", async () => {
    const api = actions();
    render(<CartView cart={cart()} actions={api} />);

    await userEvent.click(screen.getByRole("button", { name: "Increase quantity of Running shoes" }));

    expect(api.setQuantity).toHaveBeenCalledWith("RS-001", 3);
    expect(await screen.findByText("Quantity of Running shoes set to 3.")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Quantity of Running shoes set to 3.");
  });

  it("removes a line, announces it and keeps the keyboard on the page heading when the cart empties", async () => {
    const api = actions({ removeItem: jest.fn().mockResolvedValue({ ok: true, cart: cart([]) }) });
    render(<CartView cart={cart([line()])} actions={api} />);

    await userEvent.click(screen.getByRole("button", { name: "Remove Running shoes from your cart" }));

    expect(api.removeItem).toHaveBeenCalledWith("RS-001");
    expect(await screen.findByText("Running shoes removed from your cart.")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole("heading", { level: 1, name: "Your cart" })).toHaveFocus();
    });
  });

  it("asks before clearing the cart and clears it only after confirmation", async () => {
    const api = actions();
    render(<CartView cart={cart()} actions={api} />);

    await userEvent.click(screen.getByRole("button", { name: "Clear cart" }));
    const dialog = await screen.findByRole("dialog", { name: "Clear your cart?" });
    expect(within(dialog).getByText("This removes all 3 items from your cart.")).toBeInTheDocument();
    expect(api.clearCart).not.toHaveBeenCalled();

    await userEvent.click(within(dialog).getByRole("button", { name: "Clear cart" }));

    expect(api.clearCart).toHaveBeenCalledTimes(1);
    expect(await screen.findByText("Your cart is empty.")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    expect(screen.getByRole("heading", { level: 1, name: "Your cart" })).toHaveFocus();
  });

  it("can cancel clearing the cart", async () => {
    const api = actions();
    render(<CartView cart={cart()} actions={api} />);

    await userEvent.click(screen.getByRole("button", { name: "Clear cart" }));
    await userEvent.click(await screen.findByRole("button", { name: "Cancel" }));

    expect(api.clearCart).not.toHaveBeenCalled();
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });

  it("keeps the dialog open with the reason when clearing fails", async () => {
    const api = actions({ clearCart: jest.fn().mockResolvedValue({ ok: false, kind: "unavailable" }) });
    render(<CartView cart={cart()} actions={api} />);

    await userEvent.click(screen.getByRole("button", { name: "Clear cart" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Clear cart" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Nothing was changed");
  });

  describe("notices", () => {
    it("explains a price change in plain words and accepts the new price", async () => {
      const api = actions();
      const { container } = render(
        <CartView cart={flagged([{ type: "price_changed", old_price: "59.00", new_price: "64.50" }])} actions={api} />,
      );

      expect(screen.getByText(/The price changed from \$59.00 to \$64.50\./)).toBeInTheDocument();
      expect(await axe(container)).toHaveNoViolations();

      await userEvent.click(screen.getByRole("button", { name: "Accept new price of $64.50 for Running shoes" }));

      expect(api.setQuantity).toHaveBeenCalledWith("RS-001", 2, "64.50");
      expect(await screen.findByText("The price of Running shoes is now $64.50.")).toBeInTheDocument();
    });

    it("refreshes the price shown after a conflict and accepts that one next", async () => {
      const setQuantity = jest
        .fn()
        .mockResolvedValueOnce({ ok: false, kind: "price_changed", currentPrice: "66.00" })
        .mockResolvedValueOnce({ ok: true, cart: cart() });
      render(
        <CartView
          cart={flagged([{ type: "price_changed", old_price: "59.00", new_price: "64.50" }])}
          actions={actions({ setQuantity })}
        />,
      );

      await userEvent.click(screen.getByRole("button", { name: /Accept new price of \$64.50/ }));

      expect(await screen.findByRole("alert")).toHaveTextContent("The price is now $66.00");
      expect(screen.getByText(/The price changed from \$59.00 to \$66\.00\./)).toBeInTheDocument();
      await settled();

      await userEvent.click(screen.getByRole("button", { name: /Accept new price of \$66.00/ }));

      expect(setQuantity).toHaveBeenLastCalledWith("RS-001", 2, "66.00");
      await waitFor(() => {
        expect(screen.queryByRole("alert")).not.toBeInTheDocument();
      });
    });

    it("says a product is no longer available and offers only to remove it", async () => {
      const { container } = render(<CartView cart={flagged([{ type: "unavailable" }])} actions={actions()} />);

      expect(screen.getByText(/This product is no longer available\./)).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /Accept new price/ })).not.toBeInTheDocument();
      expect(screen.queryByRole("link", { name: "Running shoes" })).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Remove Running shoes from your cart" })).toBeEnabled();
      expect(await axe(container)).toHaveNoViolations();
    });

    it("says how many are left, or that the product is out of stock", () => {
      const first = render(<CartView cart={flagged([{ type: "insufficient_stock", available: 1 }])} actions={actions()} />);
      expect(screen.getByText(/Only 1 left\./)).toBeInTheDocument();
      first.unmount();

      render(<CartView cart={flagged([{ type: "insufficient_stock", available: 0 }])} actions={actions()} />);
      expect(screen.getByText(/This product is out of stock\./)).toBeInTheDocument();
    });

    it("shows several notices for one line", () => {
      render(
        <CartView
          cart={flagged([
            { type: "price_changed", old_price: "59.00", new_price: "64.50" },
            { type: "insufficient_stock", available: 1 },
          ])}
          actions={actions()}
        />,
      );

      const notices = screen.getByRole("list", { name: "Notices for Running shoes" });
      expect(within(notices).getAllByRole("listitem")).toHaveLength(2);
    });
  });

  describe("errors", () => {
    it("shows the cart limit when a line cannot be added", async () => {
      const api = actions({ setQuantity: jest.fn().mockResolvedValue({ ok: false, kind: "cart_full" }) });
      render(<CartView cart={cart()} actions={api} />);

      await userEvent.click(screen.getByRole("button", { name: "Increase quantity of Running shoes" }));

      expect(await screen.findByRole("alert")).toHaveTextContent("100 different products");
    });

    it("explains a refused quantity", async () => {
      const api = actions({ setQuantity: jest.fn().mockResolvedValue({ ok: false, kind: "invalid" }) });
      render(<CartView cart={cart()} actions={api} />);

      await userEvent.click(screen.getByRole("button", { name: "Increase quantity of Running shoes" }));

      expect(await screen.findByRole("alert")).toHaveTextContent("from 1 to 99");
    });

    it("offers to try again when the cart cannot be reached, and repeats the same change", async () => {
      const setQuantity = jest
        .fn()
        .mockResolvedValueOnce({ ok: false, kind: "unavailable" })
        .mockResolvedValueOnce({ ok: true, cart: cart() });
      render(<CartView cart={cart()} actions={actions({ setQuantity })} />);

      await userEvent.click(screen.getByRole("button", { name: "Increase quantity of Running shoes" }));
      expect(await screen.findByRole("alert")).toHaveTextContent("Nothing was changed");
      await userEvent.click(screen.getByRole("button", { name: "Try again" }));

      expect(setQuantity).toHaveBeenCalledTimes(2);
      expect(setQuantity).toHaveBeenLastCalledWith("RS-001", 3);
      expect(await screen.findByText("Quantity of Running shoes set to 3.")).toBeInTheDocument();
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });

    it("retries a removal and an accepted price the same way", async () => {
      const removeItem = jest
        .fn()
        .mockResolvedValueOnce({ ok: false, kind: "unavailable" })
        .mockResolvedValueOnce({ ok: true, cart: cart() });
      const setQuantity = jest
        .fn()
        .mockResolvedValueOnce({ ok: false, kind: "unavailable" })
        .mockResolvedValueOnce({ ok: true, cart: cart() });
      render(
        <CartView
          cart={flagged([{ type: "price_changed", old_price: "59.00", new_price: "64.50" }])}
          actions={actions({ removeItem, setQuantity })}
        />,
      );

      await userEvent.click(screen.getByRole("button", { name: "Remove Running shoes from your cart" }));
      await userEvent.click(await screen.findByRole("button", { name: "Try again" }));
      expect(removeItem).toHaveBeenCalledTimes(2);
      await settled();

      await userEvent.click(screen.getByRole("button", { name: /Accept new price/ }));
      await userEvent.click(await screen.findByRole("button", { name: "Try again" }));
      expect(setQuantity).toHaveBeenCalledTimes(2);
    });

    it("ignores a second change while one is still in flight, then accepts the next one", async () => {
      let finishRemoval: () => void = () => undefined;
      const removeItem = jest
        .fn()
        .mockResolvedValueOnce({ ok: false, kind: "unavailable" })
        .mockImplementationOnce(
          () =>
            new Promise<CartResult>((resolve) => {
              finishRemoval = () => {
                resolve({ ok: true, cart: cart() });
              };
            }),
        );
      const setQuantity = jest.fn().mockResolvedValue({ ok: true, cart: cart() });
      render(
        <CartView
          cart={flagged([{ type: "price_changed", old_price: "59.00", new_price: "64.50" }])}
          actions={actions({ removeItem, setQuantity })}
        />,
      );

      await userEvent.click(screen.getByRole("button", { name: "Remove Running shoes from your cart" }));
      await userEvent.click(await screen.findByRole("button", { name: "Try again" }));
      const accept = screen.getByRole("button", { name: /Accept new price/ });

      expect(accept).toBeDisabled();
      await userEvent.click(accept);
      expect(setQuantity).not.toHaveBeenCalled();

      finishRemoval();
      await settled();
      await userEvent.click(screen.getByRole("button", { name: /Accept new price/ }));

      expect(setQuantity).toHaveBeenCalledWith("RS-001", 2, "64.50");
    });

    it("disables every control while a change is in flight", async () => {
      let finish: () => void = () => undefined;
      const setQuantity = jest.fn(
        () =>
          new Promise<CartResult>((resolve) => {
            finish = () => {
              resolve({ ok: true, cart: cart() });
            };
          }),
      );
      render(<CartView cart={cart()} actions={actions({ setQuantity })} />);

      await userEvent.click(screen.getByRole("button", { name: "Increase quantity of Running shoes" }));

      expect(screen.getByRole("button", { name: "Remove Running shoes from your cart" })).toBeDisabled();
      expect(screen.getByRole("button", { name: "Clear cart" })).toBeDisabled();
      finish();
      await waitFor(() => {
        expect(screen.getByRole("button", { name: "Clear cart" })).toBeEnabled();
      });
    });
  });

  it("can be used with the keyboard alone", async () => {
    const api = actions();
    render(<CartView cart={cart([line()])} actions={api} />);

    await userEvent.tab();
    expect(screen.getByRole("button", { name: "Clear cart" })).toHaveFocus();
    await userEvent.tab();
    expect(screen.getByRole("link", { name: "Running shoes" })).toHaveFocus();
    await userEvent.tab();
    expect(screen.getByRole("button", { name: "Decrease quantity of Running shoes" })).toHaveFocus();
    await userEvent.tab();
    await userEvent.tab();
    await userEvent.keyboard("{Enter}");

    expect(api.setQuantity).toHaveBeenCalledWith("RS-001", 3);
  });
});
