import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CheckoutScreen } from "../src/components/checkout/checkout-screen";
import { cart } from "./support/cart";
import { address } from "./support/addresses";
import { router } from "./support/navigation-mock";
import { ORDER_ID } from "./support/orders";

jest.mock("next/navigation", () => jest.requireActual("./support/navigation-mock") as unknown);

describe("CheckoutScreen", () => {
  it("opens the order page when the order is accepted", async () => {
    const actions = {
      placeOrder: jest.fn().mockResolvedValue({ ok: true, orderId: ORDER_ID }),
      newAttemptKey: jest.fn(),
      addAddress: jest.fn(),
    };
    render(<CheckoutScreen cart={cart()} addresses={[address()]} attemptKey="first-attempt-key-0001" actions={actions} />);

    await userEvent.type(screen.getByLabelText("Card number"), "4111111111111111");
    await userEvent.click(screen.getByRole("button", { name: "Place order" }));

    await waitFor(() => {
      expect(router.push).toHaveBeenCalledWith(`/orders/${ORDER_ID}`);
    });
  });
});
