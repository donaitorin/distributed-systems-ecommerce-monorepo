import { render, screen, within } from "@testing-library/react";
import { axe } from "jest-axe";
import { OrderDetailView } from "../src/components/orders/order-detail-view";
import type { PaymentLookup } from "../src/server/orders";
import { orderDetail, payment } from "./support/api";

const withPayment = (value = payment()): PaymentLookup => ({ payment: value });

describe("OrderDetailView", () => {
  it("shows the customer email, address, lines, totals, payment, last 4 digits and the full history", async () => {
    const { container } = render(<OrderDetailView order={orderDetail()} payment={withPayment()} />);

    expect(screen.getByRole("link", { name: "Back to orders" })).toHaveAttribute("href", "/admin/orders");
    const customer = screen.getByRole("region", { name: "Customer" });
    expect(within(customer).getByText("ada@example.com")).toBeInTheDocument();
    expect(within(customer).getByText("0f6c1f0e-7a52-4f33-9c2a-5d9c3b1e7a10")).toBeInTheDocument();
    const summary = screen.getByRole("region", { name: "Summary" });
    expect(within(summary).getByText("Confirmed")).toBeInTheDocument();
    expect(within(summary).getByText("$137.50")).toBeInTheDocument();
    expect(within(summary).getByText("17 Oct 2026, 10:00:00 UTC")).toBeInTheDocument();
    const lines = within(screen.getByRole("list", { name: "Items in this order" })).getAllByRole("listitem");
    expect(lines[0]).toHaveTextContent("Running shoes");
    expect(lines[0]).toHaveTextContent("2 × $59.00");
    expect(lines[1]).toHaveTextContent("TY-002");
    const address = screen.getByRole("region", { name: "Shipping address" });
    expect(address).toHaveTextContent("Ada Lovelace");
    expect(address).toHaveTextContent("London, Greater London, N1 9GU");
    expect(address).toHaveTextContent("+442071234567");
    const paymentSection = screen.getByRole("region", { name: "Payment" });
    expect(paymentSection).toHaveTextContent("Card ending in 1111");
    expect(within(paymentSection).getByText("Succeeded")).toBeInTheDocument();
    const history = within(screen.getByRole("list", { name: "Status history" })).getAllByRole("listitem");
    expect(history.map((item) => item.textContent)).toEqual([
      "Created as PENDING: order created17 Oct 2026, 10:00:00 UTC",
      "PENDING to STOCK_RESERVED: stock reserved17 Oct 2026, 10:00:02 UTC",
      "STOCK_RESERVED to CONFIRMED: order confirmed17 Oct 2026, 10:00:09 UTC",
    ]);
    expect(await axe(container)).toHaveNoViolations();
  });

  it("falls back to the customer id for an old order without an email", () => {
    render(<OrderDetailView order={orderDetail({ customer_email: null })} payment={withPayment()} />);

    expect(within(screen.getByRole("region", { name: "Customer" })).getByText("Not recorded for this order")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Customer" })).getByText("0f6c1f0e-7a52-4f33-9c2a-5d9c3b1e7a10")).toBeInTheDocument();
  });

  it("omits the optional address lines", () => {
    const base = orderDetail();
    render(
      <OrderDetailView
        order={{ ...base, shipping_address: { ...base.shipping_address, line2: null, region: null, phone: null } }}
        payment={withPayment()}
      />,
    );

    const address = screen.getByRole("region", { name: "Shipping address" });
    expect(address).toHaveTextContent("London, N1 9GU");
    expect(address).not.toHaveTextContent("Floor 2");
    expect(address).not.toHaveTextContent("+44");
  });

  it("shows the cancel reason and the refund of a late payment", async () => {
    const refunded = "2026-10-17T10:02:00Z";
    const { container } = render(
      <OrderDetailView
        order={orderDetail({ status: "CANCELLED", cancel_reason: "saga_timeout", refunded_at: refunded })}
        payment={withPayment(payment({ status: "REFUNDED", refunded_at: refunded }))}
      />,
    );

    expect(screen.getByText("Payment timed out")).toBeInTheDocument();
    expect(screen.getAllByText("17 Oct 2026, 10:02:00 UTC").length).toBe(2);
    expect(within(screen.getByRole("region", { name: "Payment" })).getByText("Refunded", { selector: "dd" })).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("shows the refund of the order when the payment has no refund time", () => {
    render(
      <OrderDetailView
        order={orderDetail({ status: "CANCELLED", cancel_reason: "saga_timeout", refunded_at: "2026-10-17T10:02:00Z" })}
        payment={withPayment(payment({ status: "SUCCEEDED" }))}
      />,
    );

    expect(within(screen.getByRole("region", { name: "Payment" })).getByText("17 Oct 2026, 10:02:00 UTC")).toBeInTheDocument();
  });

  it("shows the failure reason of a declined payment", () => {
    render(
      <OrderDetailView
        order={orderDetail({ status: "CANCELLED", cancel_reason: "payment_failed", card_last4: "0000" })}
        payment={withPayment(payment({ status: "FAILED", failure_reason: "card_declined", card_last4: "0000" }))}
      />,
    );

    expect(screen.getByText("Payment declined")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Payment" })).getByText("card_declined")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Payment" })).getByText("Failed")).toBeInTheDocument();
  });

  it("says when no payment was recorded, or could not be loaded", () => {
    const { unmount } = render(<OrderDetailView order={orderDetail({ status: "CANCELLED" })} payment={{ payment: null, unavailable: false }} />);
    expect(screen.getByText("No payment was recorded for this order.")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Payment" })).toHaveTextContent("Card ending in 1111");
    unmount();

    render(<OrderDetailView order={orderDetail()} payment={{ payment: null, unavailable: true }} />);
    expect(screen.getByText(/payment could not be loaded right now/)).toBeInTheDocument();
  });
});
