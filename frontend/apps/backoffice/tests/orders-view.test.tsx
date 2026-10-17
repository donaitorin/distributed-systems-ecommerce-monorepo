import { screen, waitFor, within } from "@testing-library/react";
import { axe } from "jest-axe";
import type { UrlUpdateEvent } from "nuqs/adapters/testing";
import type { Failure } from "@ecommerce/web-core";
import { settled } from "@ecommerce/web-core/testing";
import { OrdersView, orderHref, type OrdersViewProps } from "../src/components/orders/orders-view";
import { orderRow } from "./support/api";
import { resetRouter } from "./support/navigation-mock";
import { renderApp } from "./support/render";

jest.mock("next/navigation", () => jest.requireActual("./support/navigation-mock") as unknown);

const FIRST = orderRow();
const SECOND = orderRow({ id: "7a2d3e75-4f1f-4d2b-8e63-8b2c9d0e1f32", status: "CANCELLED", item_count: 1, total: "19.50", customer_email: null });
const THIRD = orderRow({ id: "8b3e4f86-5a20-4e3c-9f74-9c3d0e1f2a43", status: "STOCK_RESERVED", item_count: 12, total: "1204.50" });

function props(overrides: Partial<OrdersViewProps> = {}): OrdersViewProps {
  return { page: { items: [FIRST, SECOND, THIRD], next_cursor: "NEXT" }, failure: null, ...overrides };
}

function lastUrl(onUrlUpdate: jest.Mock<void, [UrlUpdateEvent]>): URLSearchParams {
  return onUrlUpdate.mock.lastCall?.[0].searchParams ?? new URLSearchParams();
}

function failure(status: number | null, extra: object = {}): Failure {
  return { ok: false, status, title: "Problem", fieldErrors: {}, ...extra };
}

beforeEach(() => {
  resetRouter();
});

describe("OrdersView list", () => {
  it("shows orders with a link, customer, status as text and icon, and has no accessibility violations", async () => {
    const { container } = renderApp(<OrdersView {...props()} />);
    const table = screen.getByRole("table", { name: "Order list" });

    expect(within(table).getByRole("link", { name: "Order 6F1C2F64" })).toHaveAttribute("href", `/admin/orders/${FIRST.id}`);
    expect(within(table).getAllByText("ada@example.com")).toHaveLength(2);
    expect(within(table).getByText("Customer 0f6c1f0e")).toBeInTheDocument();
    expect(within(table).getByText("Confirmed")).toBeInTheDocument();
    expect(within(table).getByText("Cancelled")).toBeInTheDocument();
    expect(within(table).getByText("Stock reserved")).toBeInTheDocument();
    expect(within(table).getAllByText("17 Oct 2026, 10:00:00 UTC").length).toBe(3);
    expect(within(table).getByText("$1,204.50")).toBeInTheDocument();
    expect(table.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("shows each order as a card on small screens, with the same facts", () => {
    renderApp(<OrdersView {...props()} />);
    const cards = within(screen.getByRole("list", { name: "Order list" })).getAllByRole("listitem");

    expect(cards).toHaveLength(3);
    expect(within(cards[1] as HTMLElement).getByText("Cancelled")).toBeInTheDocument();
    expect(cards[1]).toHaveTextContent("1 item, $19.50");
    expect(cards[2]).toHaveTextContent("12 items, $1,204.50");
    expect(within(cards[0] as HTMLElement).getByRole("link", { name: "Order 6F1C2F64" })).toBeInTheDocument();
  });

  it("builds the address of an order inside the zone", () => {
    expect(orderHref({ id: "abc" })).toBe("/admin/orders/abc");
  });

  it("announces how many orders are on the page", () => {
    const { unmount } = renderApp(<OrdersView {...props()} />);
    expect(screen.getByRole("status")).toHaveTextContent("3 orders on this page, more available");
    unmount();

    renderApp(<OrdersView {...props({ page: { items: [FIRST], next_cursor: null } })} />);
    expect(screen.getByRole("status")).toHaveTextContent("1 order on this page");
    expect(screen.getByRole("status")).not.toHaveTextContent("more available");
  });

  it("shows the empty message", () => {
    renderApp(<OrdersView {...props({ page: { items: [], next_cursor: null } })} />);

    expect(within(screen.getByRole("table")).getByText("No orders match these filters.")).toBeInTheDocument();
  });

  it.each([
    [failure(503), "not available right now"],
    [failure(null), "not available right now"],
    [failure(422, { fieldErrors: { status: "bad" } }), "filters are not valid"],
    [failure(422, { fieldErrors: { cursor: "bad" } }), "no longer matches the current filters"],
    [failure(500, { detail: "Broke" }), "Broke"],
    [failure(500), "Problem"],
  ])("shows a failed load as an alert: %j", (error, text) => {
    renderApp(<OrdersView {...props({ page: null, failure: error })} />);

    expect(within(screen.getByRole("table")).getByRole("alert")).toHaveTextContent(text);
    expect(screen.queryByRole("navigation", { name: "Order pages" })).not.toBeInTheDocument();
  });
});

describe("OrdersView URL state", () => {
  it("reads the filters from the URL and ignores invalid values", () => {
    renderApp(<OrdersView {...props()} />, { searchParams: "?status=SHIPPED&from=2026-10-01&to=nope&limit=100" });

    expect(screen.getByRole("combobox", { name: "Status" })).toHaveTextContent("Any status");
    expect(screen.getByLabelText("Placed from")).toHaveValue("2026-10-01");
    expect(screen.getByLabelText("Placed until")).toHaveValue("");
    expect(screen.getByRole("combobox", { name: "Orders per page" })).toHaveTextContent("100 per page");
  });

  it("writes the status to the URL, keeps the other filters and clears the cursor", async () => {
    const onUrlUpdate = jest.fn<void, [UrlUpdateEvent]>();
    const { user } = renderApp(<OrdersView {...props()} />, { searchParams: "?cursor=OLD&from=2026-10-01", onUrlUpdate });

    await user.click(screen.getByRole("combobox", { name: "Status" }));
    await user.click(await screen.findByRole("option", { name: "Cancelled" }));

    await waitFor(() => {
      expect(lastUrl(onUrlUpdate).get("status")).toBe("CANCELLED");
    });
    expect(lastUrl(onUrlUpdate).has("cursor")).toBe(false);
    expect(lastUrl(onUrlUpdate).get("from")).toBe("2026-10-01");
    expect(onUrlUpdate.mock.lastCall?.[0].options.history).toBe("push");
    await settled();

    await user.click(screen.getByRole("combobox", { name: "Status" }));
    await user.click(await screen.findByRole("option", { name: "Any status" }));
    await waitFor(() => {
      expect(lastUrl(onUrlUpdate).has("status")).toBe(false);
    });
  });

  it("writes the dates to the URL and clears the cursor", async () => {
    const onUrlUpdate = jest.fn<void, [UrlUpdateEvent]>();
    const { user } = renderApp(<OrdersView {...props()} />, { searchParams: "?cursor=OLD", onUrlUpdate });

    await user.type(screen.getByLabelText("Placed from"), "2026-10-01");
    await waitFor(() => {
      expect(lastUrl(onUrlUpdate).get("from")).toBe("2026-10-01");
    });
    await settled();
    await user.type(screen.getByLabelText("Placed until"), "2026-10-17");

    await waitFor(() => {
      expect(lastUrl(onUrlUpdate).get("to")).toBe("2026-10-17");
    });
    expect(lastUrl(onUrlUpdate).has("cursor")).toBe(false);
  });

  it("removes a date from the URL when the field is emptied", async () => {
    const onUrlUpdate = jest.fn<void, [UrlUpdateEvent]>();
    const { user } = renderApp(<OrdersView {...props()} />, { searchParams: "?from=2026-10-01&to=2026-10-17", onUrlUpdate });

    await user.clear(screen.getByLabelText("Placed from"));

    await waitFor(() => {
      expect(lastUrl(onUrlUpdate).has("from")).toBe(false);
    });
    expect(lastUrl(onUrlUpdate).get("to")).toBe("2026-10-17");
  });

  it("marks an end date before the start date as invalid and explains it", async () => {
    const { container } = renderApp(<OrdersView {...props({ page: null })} />, { searchParams: "?from=2026-10-17&to=2026-10-01" });

    expect(screen.getByLabelText("Placed until")).toBeInvalid();
    expect(screen.getByLabelText("Placed until")).toHaveAccessibleDescription("The end date must be on or after the start date.");
    expect(within(screen.getByRole("table")).getByRole("alert")).toHaveTextContent("on or after the start date");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("does not write the default page size, and writes another one", async () => {
    const onUrlUpdate = jest.fn<void, [UrlUpdateEvent]>();
    const { user } = renderApp(<OrdersView {...props()} />, { searchParams: "?limit=50", onUrlUpdate });

    await user.click(screen.getByRole("combobox", { name: "Orders per page" }));
    await user.click(await screen.findByRole("option", { name: "25 per page" }));
    await waitFor(() => {
      expect(onUrlUpdate).toHaveBeenCalled();
    });
    expect(lastUrl(onUrlUpdate).has("limit")).toBe(false);
    await settled();

    await user.click(screen.getByRole("combobox", { name: "Orders per page" }));
    await user.click(await screen.findByRole("option", { name: "100 per page" }));
    await waitFor(() => {
      expect(lastUrl(onUrlUpdate).get("limit")).toBe("100");
    });
  });

  it("clears the filters", async () => {
    const onUrlUpdate = jest.fn<void, [UrlUpdateEvent]>();
    const { user } = renderApp(<OrdersView {...props()} />, { searchParams: "?status=PAID&from=2026-10-01&to=2026-10-17&cursor=C", onUrlUpdate });

    await user.click(screen.getByRole("button", { name: "Clear filters" }));

    await waitFor(() => {
      expect(onUrlUpdate).toHaveBeenCalled();
    });
    expect([...lastUrl(onUrlUpdate).keys()]).toEqual([]);
  });

  it("offers no clear button without filters", () => {
    renderApp(<OrdersView {...props()} />, { searchParams: "?limit=50" });

    expect(screen.queryByRole("button", { name: "Clear filters" })).not.toBeInTheDocument();
  });
});

describe("OrdersView pagination", () => {
  it("moves forward with the cursor, keeping the filters, and back to the first page", async () => {
    const onUrlUpdate = jest.fn<void, [UrlUpdateEvent]>();
    const { user } = renderApp(<OrdersView {...props()} />, { searchParams: "?status=PAID", onUrlUpdate });
    expect(screen.getByRole("button", { name: "First page" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => {
      expect(lastUrl(onUrlUpdate).get("cursor")).toBe("NEXT");
    });
    expect(lastUrl(onUrlUpdate).get("status")).toBe("PAID");
    await settled();

    await user.click(screen.getByRole("button", { name: "First page" }));
    await waitFor(() => {
      expect(lastUrl(onUrlUpdate).has("cursor")).toBe(false);
    });
  });

  it("disables Next on the last page", () => {
    renderApp(<OrdersView {...props({ page: { items: [FIRST], next_cursor: null } })} />, { searchParams: "?cursor=C" });

    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "First page" })).toBeEnabled();
  });

  it("offers to go back when a pasted cursor does not match the filters", async () => {
    const onUrlUpdate = jest.fn<void, [UrlUpdateEvent]>();
    const { user } = renderApp(<OrdersView {...props({ page: null, failure: failure(422, { fieldErrors: { cursor: "bad" } }) })} />, {
      searchParams: "?cursor=BAD",
      onUrlUpdate,
    });

    await user.click(screen.getByRole("button", { name: "Back to the first page" }));

    await waitFor(() => {
      expect(lastUrl(onUrlUpdate).has("cursor")).toBe(false);
    });
  });
});
