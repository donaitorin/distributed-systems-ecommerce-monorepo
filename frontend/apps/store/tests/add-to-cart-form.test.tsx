import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { AddToCartForm } from "../src/components/cart/add-to-cart-form";
import type { AddResult, AddToCart } from "../src/lib/cart";

type Add = jest.Mock<ReturnType<AddToCart>, Parameters<AddToCart>>;

const resolving = (result: AddResult): Add => jest.fn<ReturnType<AddToCart>, Parameters<AddToCart>>().mockResolvedValue(result);

function setup(add: Add, stock = 10) {
  return render(<AddToCartForm sku="RS-001" name="Running shoes" stock={stock} add={add} />);
}

const button = () => screen.getByRole("button", { name: "Add to cart" });

describe("AddToCartForm", () => {
  it("adds the chosen quantity and confirms politely with a link to the cart", async () => {
    const add = resolving({ ok: true, quantity: 3, capped: false });
    const { container } = setup(add);

    await userEvent.click(screen.getByRole("button", { name: "Increase quantity of Running shoes" }));
    await userEvent.click(screen.getByRole("button", { name: "Increase quantity of Running shoes" }));
    await userEvent.click(button());

    expect(add).toHaveBeenCalledWith("RS-001", 3);
    expect(await screen.findByRole("status")).toHaveTextContent("Added to your cart. You now have 3 in your cart.");
    expect(screen.getByRole("link", { name: "View cart" })).toHaveAttribute("href", "/cart");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("says when the cart already holds the most it can", async () => {
    setup(resolving({ ok: true, quantity: 99, capped: true }));

    await userEvent.click(button());

    expect(await screen.findByRole("status")).toHaveTextContent("Your cart now holds 99, the most you can have of one product.");
  });

  it("can be submitted with the keyboard from the quantity field", async () => {
    const add = resolving({ ok: true, quantity: 1, capped: false });
    setup(add);

    await userEvent.click(screen.getByRole("textbox", { name: "Quantity of Running shoes" }));
    await userEvent.tab();
    await userEvent.tab();
    expect(button()).toHaveFocus();
    await userEvent.keyboard("{Enter}");

    await waitFor(() => {
      expect(add).toHaveBeenCalledTimes(1);
    });
  });

  it("limits the quantity to the stock", async () => {
    setup(resolving({ ok: true, quantity: 1, capped: false }), 2);

    expect(screen.getByRole("button", { name: "Increase quantity of Running shoes" })).toBeEnabled();
    await userEvent.click(screen.getByRole("button", { name: "Increase quantity of Running shoes" }));
    expect(screen.getByRole("button", { name: "Increase quantity of Running shoes" })).toBeDisabled();
  });

  it("disables the button while adding", async () => {
    let finish: (result: AddResult) => void = () => undefined;
    const add: Add = jest.fn<ReturnType<AddToCart>, Parameters<AddToCart>>(
      () => new Promise((resolve) => { finish = resolve; }),
    );
    setup(add);

    await userEvent.click(button());

    expect(button()).toBeDisabled();
    finish({ ok: true, quantity: 1, capped: false });
    await waitFor(() => {
      expect(button()).toBeEnabled();
    });
  });

  it.each([
    ["cart_full", "100 different products"],
    ["not_found", "no longer available"],
    ["unavailable", "Try again in a moment"],
    ["invalid", "from 1 to 99"],
  ] as const)("explains %s", async (kind, text) => {
    setup(resolving({ ok: false, kind }));

    await userEvent.click(button());

    expect(await screen.findByRole("alert")).toHaveTextContent(text);
    expect(screen.queryByRole("link", { name: "View cart" })).not.toBeInTheDocument();
  });

  it("is disabled for a product that is out of stock, and says why", async () => {
    const add = resolving({ ok: true, quantity: 1, capped: false });
    const { container } = setup(add, 0);

    expect(button()).toBeDisabled();
    expect(screen.getByText(/out of stock and cannot be added/)).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: /Quantity of/ })).not.toBeInTheDocument();
    await userEvent.click(button());
    expect(add).not.toHaveBeenCalled();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("never submits while sold out even with the keyboard", () => {
    const add = resolving({ ok: true, quantity: 1, capped: false });
    setup(add, 0);

    const form = screen.getByRole("form", { name: "Add Running shoes to your cart" });
    form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));

    expect(add).not.toHaveBeenCalled();
  });
});
