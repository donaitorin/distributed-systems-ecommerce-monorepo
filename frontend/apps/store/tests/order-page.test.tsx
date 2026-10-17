import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";
import OrderPage from "../src/app/orders/[id]/page";
import OrderNotFound from "../src/app/orders/[id]/not-found";
import { ORDER_ID, order } from "./support/orders";

const requireSession = jest.fn();
const loadOrder = jest.fn();

jest.mock("@ecommerce/auth/next", () => ({ requireSession: (options: unknown) => requireSession(options) as unknown }));
jest.mock("next/navigation", () => jest.requireActual("./support/navigation-mock") as unknown);
jest.mock("../src/server/orders", () => ({ loadOrder: (id: string) => loadOrder(id) as unknown }));
jest.mock("../src/app/orders/actions", () => ({ refreshCartCountAction: jest.fn() }));

beforeEach(() => {
  requireSession.mockReset();
  loadOrder.mockReset();
  requireSession.mockResolvedValue({ userId: "u1", role: "customer" });
  loadOrder.mockResolvedValue(order({ status: "CONFIRMED" }));
});

const params = (id = ORDER_ID) => ({ params: Promise.resolve({ id }) });

describe("order page", () => {
  it("requires a session and shows the order", async () => {
    const { container } = render(await OrderPage(params()));

    expect(requireSession).toHaveBeenCalledWith({ loginPath: "/login" });
    expect(loadOrder).toHaveBeenCalledWith(ORDER_ID);
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("status")).toHaveTextContent("Order confirmed");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("answers a real 404 for an order that is not the customer's", async () => {
    loadOrder.mockResolvedValue({ ok: false, kind: "not_found" });

    await expect(OrderPage(params())).rejects.toThrow("NEXT_NOT_FOUND");
  });

  it("explains a temporary failure with a way to retry, and no order", async () => {
    loadOrder.mockResolvedValue({ ok: false, kind: "unavailable" });

    const { container } = render(await OrderPage(params()));

    expect(screen.getByRole("alert")).toHaveTextContent("could not be loaded");
    expect(screen.getByRole("link", { name: "Try again" })).toHaveAttribute("href", `/orders/${ORDER_ID}`);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("has a not found page with a way back to the catalog", async () => {
    const { container } = render(<OrderNotFound />);

    expect(screen.getByRole("heading", { level: 1, name: "Order not found" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Browse products" })).toHaveAttribute("href", "/products");
    expect(await axe(container)).toHaveNoViolations();
  });
});
