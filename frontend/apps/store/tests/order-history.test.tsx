import { render, screen, within } from "@testing-library/react";
import { axe } from "jest-axe";
import { nextPageHref, OrderHistory } from "../src/components/orders/order-history";
import { ORDER_ID, summary } from "./support/orders";

const OTHER_ID = "9a8b7c6d-1234-4abc-8def-0123456789ab";

describe("OrderHistory", () => {
  it("lists the orders with date, items, total and a status that is text and an icon", async () => {
    const page = {
      items: [summary(), summary({ id: OTHER_ID, status: "CANCELLED", item_count: 1, total: "19.50", created_at: "2026-10-16T09:30:00Z" })],
      next_cursor: null,
    };
    const { container } = render(<OrderHistory page={page} cursor={null} />);

    const rows = within(screen.getByRole("list", { name: "Your orders" })).getAllByRole("listitem");
    expect(rows).toHaveLength(2);
    expect(within(rows[0] as HTMLElement).getByRole("link", { name: "Order 6F1C2F64" })).toHaveAttribute("href", `/orders/${ORDER_ID}`);
    expect(rows[0]).toHaveTextContent("17 Oct 2026, 10:00:00 UTC");
    expect(rows[0]).toHaveTextContent("3 items");
    expect(rows[0]).toHaveTextContent("Total: $137.50");
    expect(within(rows[0] as HTMLElement).getByText("Confirmed")).toBeInTheDocument();
    expect(rows[1]).toHaveTextContent("1 item");
    expect(within(rows[1] as HTMLElement).getByText("Cancelled")).toBeInTheDocument();
    expect(rows[1]?.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
    expect(screen.queryByRole("navigation", { name: "Order pages" })).not.toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("offers only Next on the first page when more orders follow", () => {
    render(<OrderHistory page={{ items: [summary()], next_cursor: "abc/def==" }} cursor={null} />);

    const nav = screen.getByRole("navigation", { name: "Order pages" });
    expect(within(nav).getByRole("link", { name: "Next page" })).toHaveAttribute("href", "/orders?cursor=abc%2Fdef%3D%3D");
    expect(within(nav).queryByRole("link", { name: "First page" })).not.toBeInTheDocument();
  });

  it("offers First page on a later page and no Next on the last one", async () => {
    const { container } = render(<OrderHistory page={{ items: [summary()], next_cursor: null }} cursor="abc" />);

    const nav = screen.getByRole("navigation", { name: "Order pages" });
    expect(within(nav).getByRole("link", { name: "First page" })).toHaveAttribute("href", "/orders");
    expect(within(nav).queryByRole("link", { name: "Next page" })).not.toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("explains that there are no orders yet, with a way to the catalog", async () => {
    const { container } = render(<OrderHistory page={{ items: [], next_cursor: null }} cursor={null} />);

    expect(screen.getByRole("heading", { level: 2, name: "You have no orders yet" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Browse products" })).toHaveAttribute("href", "/products");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("still offers the way back when a later page is empty", () => {
    render(<OrderHistory page={{ items: [], next_cursor: null }} cursor="abc" />);

    expect(screen.getByRole("link", { name: "First page" })).toBeInTheDocument();
  });

  it("builds the link of the next page", () => {
    expect(nextPageHref("a b")).toBe("/orders?cursor=a%20b");
  });
});
