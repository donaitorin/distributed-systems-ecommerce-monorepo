import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";
import { NuqsTestingAdapter } from "nuqs/adapters/testing";
import OrderPage, { generateMetadata } from "../src/app/orders/[id]/page";
import OrdersPage from "../src/app/orders/page";
import { NotificationsProvider } from "../src/components/notifications";
import { ORDER_ID, orderDetail, orderRow, payment } from "./support/api";

const loadOrderPage = jest.fn();
const loadOrder = jest.fn();

jest.mock("../src/server/orders", () => ({
  loadOrderPage: (...args: unknown[]) => loadOrderPage(...args) as unknown,
  loadOrder: (...args: unknown[]) => loadOrder(...args) as unknown,
}));
jest.mock("../src/server/products", () => ({ isFailure: (value: { ok?: boolean }) => value.ok === false }));
jest.mock("next/navigation", () => jest.requireActual("./support/navigation-mock") as unknown);

globalThis.Request ??= class Request {} as unknown as typeof Request;

function inProviders(element: React.ReactElement, searchParams = "") {
  return render(
    <NuqsTestingAdapter searchParams={searchParams}>
      <NotificationsProvider>{element}</NotificationsProvider>
    </NuqsTestingAdapter>,
  );
}

beforeEach(() => {
  loadOrderPage.mockReset();
  loadOrder.mockReset();
});

describe("orders list page", () => {
  it("loads the page for the filters in the URL and ignores invalid ones", async () => {
    loadOrderPage.mockResolvedValue({ items: [orderRow()], next_cursor: null });

    const { container } = inProviders(
      await OrdersPage({ searchParams: Promise.resolve({ status: "PAID", from: "2026-10-01", to: "nope", limit: ["50", "100"], cursor: "c" }) }),
    );

    expect(loadOrderPage).toHaveBeenCalledWith({ status: "PAID", from: "2026-10-01", to: null, limit: 50, cursor: "c" });
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 1, name: "Orders" })).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("does not ask the API for an end date before the start date and says so", async () => {
    inProviders(await OrdersPage({ searchParams: Promise.resolve({ from: "2026-10-17", to: "2026-10-01" }) }), "?from=2026-10-17&to=2026-10-01");

    expect(loadOrderPage).not.toHaveBeenCalled();
    expect(screen.getAllByRole("alert")[0]).toHaveTextContent("on or after the start date");
  });

  it("shows a failed load", async () => {
    loadOrderPage.mockResolvedValue({ ok: false, status: 503, title: "Down", fieldErrors: {} });

    inProviders(await OrdersPage({ searchParams: Promise.resolve({}) }));

    expect(screen.getAllByRole("alert")[0]).toHaveTextContent("not available right now");
  });
});

describe("order detail page", () => {
  const params = (id: string = ORDER_ID) => ({ params: Promise.resolve({ id }) });

  it("shows the order and its payment under one h1", async () => {
    loadOrder.mockResolvedValue({ order: orderDetail(), payment: { payment: payment() } });

    const { container } = render(await OrderPage(params()));

    expect(loadOrder).toHaveBeenCalledWith(ORDER_ID);
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 1, name: "Order 6F1C2F64" })).toBeInTheDocument();
    expect(screen.getByText("ada@example.com")).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("names the page after the order", async () => {
    expect(await generateMetadata(params())).toEqual({ title: "Order 6F1C2F64" });
  });

  it("answers a real 404 for an order that does not exist", async () => {
    loadOrder.mockResolvedValue({ ok: false, status: 404, title: "Not found", fieldErrors: {} });

    await expect(OrderPage(params())).rejects.toThrow("NEXT_NOT_FOUND");
  });

  it("explains a failed load without a partial page", async () => {
    loadOrder.mockResolvedValue({ ok: false, status: 503, title: "Down", fieldErrors: {} });

    const { container } = render(await OrderPage(params()));

    expect(screen.getByRole("alert")).toHaveTextContent("could not be loaded");
    expect(screen.queryByRole("region", { name: "Customer" })).not.toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });
});
