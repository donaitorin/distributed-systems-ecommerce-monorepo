import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";
import { ORDER_STATUSES, OrderStatusBadge, orderStatusLabel } from "./order-status-badge";

describe("OrderStatusBadge", () => {
  it("has no accessibility violations in any status", async () => {
    const { container } = render(
      <>
        {ORDER_STATUSES.map((status) => (
          <OrderStatusBadge key={status} status={status} />
        ))}
      </>,
    );

    expect(await axe(container)).toHaveNoViolations();
  });

  it.each([
    ["PENDING", "Pending"],
    ["STOCK_RESERVED", "Stock reserved"],
    ["PAID", "Paid"],
    ["CONFIRMED", "Confirmed"],
    ["CANCELLED", "Cancelled"],
  ] as const)("shows %s as the text %s, never by colour alone", (status, label) => {
    const { container } = render(<OrderStatusBadge status={status} />);

    expect(screen.getByText(label)).toBeInTheDocument();
    expect(orderStatusLabel(status)).toBe(label);
    expect(container.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
  });

  it("uses a different icon for finished and unfinished orders", () => {
    const confirmed = render(<OrderStatusBadge status="CONFIRMED" />).container.innerHTML;
    const cancelled = render(<OrderStatusBadge status="CANCELLED" />).container.innerHTML;
    const pending = render(<OrderStatusBadge status="PENDING" />).container.innerHTML;

    expect(new Set([confirmed, cancelled, pending].map((html) => /<svg.*<\/svg>/.exec(html)?.[0])).size).toBe(3);
  });

  it("accepts a class name", () => {
    const { container } = render(<OrderStatusBadge status="PAID" className="ml-2" />);

    expect(container.firstChild).toHaveClass("ml-2");
  });
});
