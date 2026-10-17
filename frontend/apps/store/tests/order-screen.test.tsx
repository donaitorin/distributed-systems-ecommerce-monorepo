import { render, screen, waitFor } from "@testing-library/react";
import { OrderScreen } from "../src/components/orders/order-screen";
import { OrderRequestError } from "../src/lib/order-client";
import { router } from "./support/navigation-mock";
import { ORDER_ID, order } from "./support/orders";

jest.mock("next/navigation", () => jest.requireActual("./support/navigation-mock") as unknown);

describe("OrderScreen", () => {
  it("shows the order", () => {
    render(<OrderScreen initial={order({ status: "CONFIRMED" })} fetchOrder={() => Promise.resolve(order({ status: "CONFIRMED" }))} />);

    expect(screen.getByRole("status")).toHaveTextContent("Order confirmed");
  });

  it("sends an expired session to the login page and back to the order", async () => {
    render(<OrderScreen initial={order()} fetchOrder={() => Promise.reject(new OrderRequestError(401))} />);

    await waitFor(() => {
      expect(router.replace).toHaveBeenCalledWith(`/login?next=%2Forders%2F${ORDER_ID}&reason=expired`);
    });
  });
});
