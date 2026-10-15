import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";
import { PriceTag, formatPrice } from "./price-tag";

describe("PriceTag", () => {
  it("has no accessibility violations", async () => {
    const { container } = render(
      <>
        <PriceTag amount="19.99" />
        <PriceTag amount="not-a-price" />
      </>,
    );

    expect(await axe(container)).toHaveNoViolations();
  });

  it("formats a decimal string as currency", () => {
    render(<PriceTag amount="1234.5" />);

    expect(screen.getByText("$1,234.50")).toBeInTheDocument();
  });

  it("formats whole numbers with two decimals", () => {
    render(<PriceTag amount="20" />);

    expect(screen.getByText("$20.00")).toBeInTheDocument();
  });

  it("supports another currency", () => {
    render(<PriceTag amount="10.00" currency="EUR" />);

    expect(screen.getByText("€10.00")).toBeInTheDocument();
  });

  it("keeps cents exact for large amounts", () => {
    expect(formatPrice("9007199254740993.01", "USD")).toBe("$9,007,199,254,740,993.01");
  });

  it.each(["", "abc", "-1", "1e3", "1.234", "1,000.00", "NaN"])(
    "rejects %p as unavailable",
    (amount) => {
      expect(formatPrice(amount, "USD")).toBeNull();
    },
  );

  it("announces unavailable prices", () => {
    render(<PriceTag amount="abc" />);

    expect(screen.getByText("Price unavailable")).toBeInTheDocument();
  });
});
