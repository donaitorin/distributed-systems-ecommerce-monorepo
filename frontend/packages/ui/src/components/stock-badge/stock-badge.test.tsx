import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";
import { StockBadge } from "./stock-badge";

describe("StockBadge", () => {
  it("has no accessibility violations in any state", async () => {
    const { container } = render(
      <>
        <StockBadge stock={50} />
        <StockBadge stock={3} />
        <StockBadge stock={0} />
      </>,
    );

    expect(await axe(container)).toHaveNoViolations();
  });

  it.each([
    [50, "In stock"],
    [6, "In stock"],
    [5, "Only 5 left"],
    [1, "Only 1 left"],
    [0, "Out of stock"],
    [-2, "Out of stock"],
  ])("labels stock %i as %s", (stock, label) => {
    render(<StockBadge stock={stock} />);

    expect(screen.getByText(label)).toBeInTheDocument();
  });

  it("respects a custom low stock threshold", () => {
    render(<StockBadge stock={8} lowStockThreshold={10} />);

    expect(screen.getByText("Only 8 left")).toBeInTheDocument();
  });

  it("hides the decorative icon from assistive technology", () => {
    const { container } = render(<StockBadge stock={0} />);

    expect(container.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
  });
});
