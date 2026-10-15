import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";
import { ProductCard, ProductCardSkeleton, type ProductCardProps } from "./product-card";

const PRODUCT: ProductCardProps = {
  name: "Running shoes",
  href: "/products/RS-001",
  price: "59.00",
  stock: 12,
  thumbnailUrl: "/media/rs-400.webp",
  imageUrl: "/media/rs-1200.webp",
};

describe("ProductCard", () => {
  it("has no accessibility violations in any state", async () => {
    const { container } = render(
      <>
        <ProductCard {...PRODUCT} />
        <ProductCard {...PRODUCT} stock={0} />
        <ProductCard {...PRODUCT} thumbnailUrl={null} imageUrl={null} />
        <ProductCardSkeleton />
      </>,
    );

    expect(await axe(container)).toHaveNoViolations();
  });

  it("links the product name to its page", () => {
    render(<ProductCard {...PRODUCT} />);

    expect(screen.getByRole("link", { name: "Running shoes" })).toHaveAttribute(
      "href",
      "/products/RS-001",
    );
  });

  it("shows the price and the stock status", () => {
    render(<ProductCard {...PRODUCT} stock={0} />);

    expect(screen.getByText("$59.00")).toBeInTheDocument();
    expect(screen.getByText("Out of stock")).toBeInTheDocument();
  });

  it("uses the product name as the image alt text", () => {
    render(<ProductCard {...PRODUCT} />);

    expect(screen.getByRole("img", { name: "Running shoes" })).toBeInTheDocument();
  });

  it("shows the placeholder without images", () => {
    const { container } = render(<ProductCard {...PRODUCT} thumbnailUrl={null} imageUrl={null} />);

    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByRole("img", { name: "Running shoes" })).toBeInTheDocument();
  });

  it("uses the requested heading level", () => {
    render(<ProductCard {...PRODUCT} headingLevel={3} />);

    expect(screen.getByRole("heading", { level: 3, name: "Running shoes" })).toBeInTheDocument();
  });

  it("defaults to a level 2 heading", () => {
    render(<ProductCard {...PRODUCT} />);

    expect(screen.getByRole("heading", { level: 2 })).toBeInTheDocument();
  });

  it("formats the price in the given currency", () => {
    render(<ProductCard {...PRODUCT} currency="EUR" />);

    expect(screen.getByText("€59.00")).toBeInTheDocument();
  });
});

describe("ProductCardSkeleton", () => {
  it("announces loading", () => {
    render(<ProductCardSkeleton />);

    expect(screen.getByRole("status")).toHaveTextContent("Loading product");
  });
});
