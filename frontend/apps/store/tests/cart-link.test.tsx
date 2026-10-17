import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";
import { CartLink } from "../src/components/cart/cart-link";

describe("CartLink", () => {
  it("links to the cart and includes the count in its name, with no accessibility violations", async () => {
    const { container } = render(<CartLink count={3} />);

    const link = screen.getByRole("link", { name: "Cart 3 items in your cart" });
    expect(link).toHaveAttribute("href", "/cart");
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("uses the singular for one item", () => {
    render(<CartLink count={1} />);

    expect(screen.getByRole("link", { name: "Cart 1 item in your cart" })).toBeInTheDocument();
  });

  it.each([0, null])("shows no badge when the count is %s", (count) => {
    render(<CartLink count={count} />);

    expect(screen.getByRole("link", { name: "Cart" })).toBeInTheDocument();
  });

  it("announces nothing on first render", () => {
    render(<CartLink count={4} />);

    expect(screen.getByRole("status")).toHaveTextContent("");
  });

  it("announces politely when the count changes", () => {
    const { rerender } = render(<CartLink count={1} />);

    rerender(<CartLink count={3} />);
    expect(screen.getByRole("status")).toHaveAttribute("aria-live", "polite");
    expect(screen.getByRole("status")).toHaveTextContent("Cart updated: 3 items in your cart.");

    rerender(<CartLink count={1} />);
    expect(screen.getByRole("status")).toHaveTextContent("Cart updated: 1 item in your cart.");

    rerender(<CartLink count={0} />);
    expect(screen.getByRole("status")).toHaveTextContent("Your cart is empty.");

    rerender(<CartLink count={null} />);
    expect(screen.getByRole("status")).toHaveTextContent("");
  });
});
