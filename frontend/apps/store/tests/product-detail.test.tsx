import { render, screen, within } from "@testing-library/react";
import { axe } from "jest-axe";
import { AddToCartSlot } from "../src/components/catalog/add-to-cart-slot";
import { formatWeight, ProductDetail } from "../src/components/catalog/product-detail";
import { product } from "./support/api";

const add = jest.fn();

describe("ProductDetail", () => {
  it("has no accessibility violations for a product with and without image and stock", async () => {
    const { container } = render(
      <main>
        <ProductDetail product={product()} addToCart={add} />
      </main>,
    );
    expect(await axe(container)).toHaveNoViolations();
  });

  it("has no accessibility violations without image, stock, category, description or weight", async () => {
    const bare = render(
      <main>
        <ProductDetail product={product({ image_url: null, thumbnail_url: null, stock: 0, category: null, description: null, weight_kg: null })} addToCart={add} />
      </main>,
    );
    expect(await axe(bare.container)).toHaveNoViolations();
  });

  it("shows name, price, stock, description, category and weight, with the full-size image", () => {
    render(<ProductDetail product={product({ stock: 3 })} addToCart={add} />);

    expect(screen.getByRole("heading", { level: 1, name: "Running shoes" })).toBeInTheDocument();
    expect(screen.getByText("$59.00")).toBeInTheDocument();
    expect(screen.getByText("Only 3 left")).toBeInTheDocument();
    expect(screen.getByText("Light and fast")).toBeInTheDocument();
    expect(screen.getByText("0.8 kg")).toBeInTheDocument();
    const image = screen.getByRole("img", { name: "Running shoes" });
    expect(image).toHaveAttribute("src", "/media/products/RS-001/a-1200.webp");
    expect(image).toHaveAttribute("srcset", "/media/products/RS-001/a-1200.webp 1200w");
  });

  it("links the breadcrumb to the catalog and the category and marks the current page", () => {
    render(<ProductDetail product={product()} addToCart={add} />);
    const breadcrumb = screen.getByRole("navigation", { name: "Breadcrumb" });

    expect(within(breadcrumb).getByRole("link", { name: "Products" })).toHaveAttribute("href", "/products");
    expect(within(breadcrumb).getByRole("link", { name: "Footwear" })).toHaveAttribute("href", "/products?category=footwear");
    expect(within(breadcrumb).getByText("Running shoes")).toHaveAttribute("aria-current", "page");
  });

  it("shows the placeholder, no category link and no weight when the data is missing", () => {
    render(<ProductDetail product={product({ image_url: null, category: null, weight_kg: null, description: null })} addToCart={add} />);

    expect(screen.getByRole("img", { name: "Running shoes" }).tagName.toLowerCase()).toBe("svg");
    expect(screen.getByText("Uncategorised")).toBeInTheDocument();
    expect(screen.queryByText("Weight")).not.toBeInTheDocument();
  });

  it("keeps an out of stock product visible but not purchasable", () => {
    render(<ProductDetail product={product({ stock: 0 })} addToCart={add} />);

    expect(screen.getByText("Out of stock")).toBeInTheDocument();
    expect(screen.getByText(/cannot be added to a cart/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add to cart" })).toBeDisabled();
    expect(screen.queryByRole("group", { name: /Quantity of/ })).not.toBeInTheDocument();
  });

  it("leaves the marked slot for the add to cart action when the product is in stock", () => {
    const { container } = render(<ProductDetail product={product()} addToCart={add} />);

    expect(container.querySelector("#add-to-cart-slot")).toHaveAttribute("data-sku", "RS-001");
  });
});

describe("AddToCartSlot", () => {
  it("keeps the marked slot and enables the button only for products that can be bought", () => {
    const { container, rerender } = render(<AddToCartSlot product={{ sku: "A", name: "A", stock: 1 }} add={add} />);
    expect(container.querySelector("#add-to-cart-slot")).toHaveAttribute("data-sku", "A");
    expect(screen.getByRole("button", { name: "Add to cart" })).toBeEnabled();

    rerender(<AddToCartSlot product={{ sku: "A", name: "A", stock: 0 }} add={add} />);
    expect(container.querySelector("#add-to-cart-slot")).toHaveAttribute("data-sku", "A");
    expect(screen.getByRole("button", { name: "Add to cart" })).toBeDisabled();
  });
});

describe("formatWeight", () => {
  it("drops trailing zeros and keeps unreadable values as they are", () => {
    expect(formatWeight("0.800")).toBe("0.8 kg");
    expect(formatWeight("12.000")).toBe("12 kg");
    expect(formatWeight("heavy")).toBe("heavy");
    expect(formatWeight(null)).toBeNull();
  });
});
