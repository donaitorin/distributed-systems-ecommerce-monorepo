import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { settled } from "@ecommerce/web-core/testing";
import { CheckoutView, type CheckoutActions } from "../src/components/checkout/checkout-view";
import { cartFingerprint, type PlaceOrderInput, type PlaceOrderResult } from "../src/lib/checkout";
import { cart, line } from "./support/cart";
import { address, ADDRESS_ID, OTHER_ADDRESS_ID } from "./support/addresses";
import { ORDER_ID } from "./support/orders";

const FIRST_KEY = "first-attempt-key-0001";
const FRESH_KEY = "fresh-attempt-key-0002";
const CARD = "4111 1111 1111 1111";
const OTHER_ADDRESS = address({ id: OTHER_ADDRESS_ID, recipient_name: "Grace Hopper", line1: "1 Compiler Way", city: "Arlington" });

function actions(overrides: Partial<CheckoutActions> = {}): jest.Mocked<CheckoutActions> {
  return {
    placeOrder: jest.fn().mockResolvedValue({ ok: true, orderId: ORDER_ID }),
    newAttemptKey: jest.fn().mockResolvedValue(FRESH_KEY),
    addAddress: jest.fn().mockResolvedValue({ ok: true, address: OTHER_ADDRESS }),
    ...overrides,
  } as jest.Mocked<CheckoutActions>;
}

const onPlaced = jest.fn();

function setup(options: { cart?: ReturnType<typeof cart>; addresses?: ReturnType<typeof address>[]; api?: jest.Mocked<CheckoutActions> } = {}) {
  const api = options.api ?? actions();
  const view = render(
    <CheckoutView
      cart={options.cart ?? cart()}
      addresses={options.addresses ?? [address()]}
      attemptKey={FIRST_KEY}
      actions={api}
      onPlaced={onPlaced}
    />,
  );
  return { api, user: userEvent.setup(), ...view };
}

const cardField = () => screen.getByLabelText("Card number");
const placeButton = () => screen.getByRole("button", { name: "Place order" });
const placeOrderMock = () => jest.fn<Promise<PlaceOrderResult>, [PlaceOrderInput]>();
const failed = (kind: Extract<PlaceOrderResult, { ok: false }>["kind"], extra = {}): PlaceOrderResult => ({ ok: false, kind, ...extra });

beforeEach(() => {
  jest.clearAllMocks();
});

describe("CheckoutView", () => {
  it("shows the cart lines and subtotal as the cart service returned them, with one h1 and no accessibility violations", async () => {
    const { container } = setup();

    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 1, name: "Checkout" })).toBeInTheDocument();
    const items = within(screen.getByRole("list", { name: "Items in your order" })).getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(screen.getByRole("link", { name: "Running shoes" })).toHaveAttribute("href", "/products/RS-001");
    expect(screen.getByText("Subtotal (3 items)")).toBeInTheDocument();
    expect(screen.getByText("$137.50")).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("says that payments are simulated and lists the four test cards, visibly", () => {
    setup();

    expect(screen.getByText("Payments are simulated.")).toBeVisible();
    const notes = screen.getAllByRole("listitem").filter((item) => /ends|approves|declines|never answers/.test(item.textContent ?? ""));
    expect(notes.map((item) => item.textContent)).toEqual([
      expect.stringContaining("1111 approves"),
      expect.stringContaining("0000 declines"),
      expect.stringContaining("9999 never answers"),
      expect.stringContaining("2222 approves late"),
    ]);
  });

  it("gives the card field the attributes a browser and a phone need", () => {
    setup();

    expect(cardField()).toHaveAttribute("autocomplete", "cc-number");
    expect(cardField()).toHaveAttribute("inputmode", "numeric");
    expect(cardField()).toHaveAttribute("type", "text");
    expect(screen.getByRole("form", { name: "Payment" })).toHaveAttribute("method", "post");
  });

  it("groups the card digits by four while typing and ignores other characters", async () => {
    const { user } = setup();

    await user.type(cardField(), "41a11-11111111 1111");

    expect(cardField()).toHaveValue(CARD);
  });

  it("places the order with the key the server gave, the chosen address and the cart the customer saw, then opens the order page", async () => {
    const { api, user } = setup();

    await user.type(cardField(), "4111111111111111");
    await user.click(placeButton());

    await waitFor(() => {
      expect(onPlaced).toHaveBeenCalledWith(ORDER_ID);
    });
    expect(api.placeOrder).toHaveBeenCalledTimes(1);
    expect(api.placeOrder).toHaveBeenCalledWith({
      attemptKey: FIRST_KEY,
      addressId: ADDRESS_ID,
      cardNumber: CARD,
      cartFingerprint: cartFingerprint(cart()),
    });
    expect(api.newAttemptKey).not.toHaveBeenCalled();
  });

  it("clears the card number from the form after submitting, and keeps it out of the page", async () => {
    const { user, container } = setup();

    await user.type(cardField(), "4111111111111111");
    await user.click(placeButton());
    await waitFor(() => {
      expect(onPlaced).toHaveBeenCalled();
    });

    expect(cardField()).toHaveValue("");
    expect(container.textContent).not.toContain("4111");
    expect(window.location.href).not.toContain("4111");
    expect(JSON.stringify({ ...window.localStorage })).not.toContain("4111");
    expect(document.cookie).not.toContain("4111");
  });

  it("clears the card number after a failure too", async () => {
    const { user } = setup({ api: actions({ placeOrder: jest.fn().mockResolvedValue(failed("unavailable")) }) });

    await user.type(cardField(), "4111111111111111");
    await user.click(placeButton());

    expect(await screen.findByRole("alert")).toHaveTextContent("could not reach the order service");
    expect(cardField()).toHaveValue("");
  });

  it("creates one order for a double click", async () => {
    let finish: (result: PlaceOrderResult) => void = () => undefined;
    const placeOrder = jest.fn(() => new Promise<PlaceOrderResult>((resolve) => (finish = resolve)));
    const { user } = setup({ api: actions({ placeOrder }) });

    await user.type(cardField(), "4111111111111111");
    await user.dblClick(placeButton());

    expect(placeOrder).toHaveBeenCalledTimes(1);
    expect(placeButton()).toBeDisabled();
    finish({ ok: true, orderId: ORDER_ID });
    await waitFor(() => {
      expect(onPlaced).toHaveBeenCalledTimes(1);
    });
  });

  it("creates one order for two submits with the keyboard while the first is pending", async () => {
    const placeOrder = jest.fn(() => new Promise<PlaceOrderResult>(() => undefined));
    const { user } = setup({ api: actions({ placeOrder }) });

    await user.type(cardField(), "4111111111111111");
    await user.keyboard("{Enter}{Enter}");

    expect(placeOrder).toHaveBeenCalledTimes(1);
  });

  it("does not let a second order start after the first was accepted, while the page is opening", async () => {
    const { api, user } = setup();

    await user.type(cardField(), "4111111111111111");
    await user.click(placeButton());
    await waitFor(() => {
      expect(onPlaced).toHaveBeenCalled();
    });

    expect(placeButton()).toBeDisabled();
    await user.type(cardField(), "4111111111111111{Enter}");
    expect(api.placeOrder).toHaveBeenCalledTimes(1);
  });

  it("reuses the same key when the same attempt is sent again after a network failure", async () => {
    const placeOrder = placeOrderMock().mockResolvedValueOnce(failed("unavailable")).mockResolvedValueOnce({ ok: true, orderId: ORDER_ID });
    const { api, user } = setup({ api: actions({ placeOrder }) });

    await user.type(cardField(), "4111111111111111");
    await user.click(placeButton());
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    await settled();

    await user.type(cardField(), "4111111111111111");
    await user.click(placeButton());
    await waitFor(() => {
      expect(onPlaced).toHaveBeenCalledWith(ORDER_ID);
    });

    expect(placeOrder).toHaveBeenCalledTimes(2);
    expect(placeOrder.mock.calls[0]?.[0]).toMatchObject({ attemptKey: FIRST_KEY });
    expect(placeOrder.mock.calls[1]?.[0]).toMatchObject({ attemptKey: FIRST_KEY });
    expect(api.newAttemptKey).not.toHaveBeenCalled();
  });

  it("starts a new attempt with a new key when the address is edited after a failure", async () => {
    const placeOrder = placeOrderMock().mockResolvedValueOnce(failed("unavailable")).mockResolvedValueOnce({ ok: true, orderId: ORDER_ID });
    const { api, user } = setup({ addresses: [address(), OTHER_ADDRESS], api: actions({ placeOrder }) });

    await user.click(screen.getByRole("radio", { name: /Ada Lovelace/ }));
    await user.type(cardField(), "4111111111111111");
    await user.click(placeButton());
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    await settled();

    await user.click(screen.getByRole("radio", { name: /Grace Hopper/ }));
    await user.type(cardField(), "4111111111111111");
    await user.click(placeButton());
    await waitFor(() => {
      expect(onPlaced).toHaveBeenCalled();
    });

    expect(api.newAttemptKey).toHaveBeenCalledTimes(1);
    expect(placeOrder.mock.calls[0]?.[0]).toMatchObject({ attemptKey: FIRST_KEY, addressId: ADDRESS_ID });
    expect(placeOrder.mock.calls[1]?.[0]).toMatchObject({ attemptKey: FRESH_KEY, addressId: OTHER_ADDRESS_ID });
  });

  it("starts a new attempt when the card changes after a failure", async () => {
    const placeOrder = placeOrderMock().mockResolvedValueOnce(failed("unavailable")).mockResolvedValueOnce({ ok: true, orderId: ORDER_ID });
    const { api, user } = setup({ api: actions({ placeOrder }) });

    await user.type(cardField(), "4111111111111111");
    await user.click(placeButton());
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    await settled();

    await user.type(cardField(), "4111111111110000");
    await user.click(placeButton());
    await waitFor(() => {
      expect(onPlaced).toHaveBeenCalled();
    });

    expect(api.newAttemptKey).toHaveBeenCalledTimes(1);
    expect(placeOrder.mock.calls[1]?.[0]).toMatchObject({ attemptKey: FRESH_KEY, cardNumber: "4111 1111 1111 0000" });
  });

  it("asks for a fresh key when the server says the key was used for another order", async () => {
    const placeOrder = placeOrderMock().mockResolvedValueOnce(failed("attempt_changed")).mockResolvedValueOnce({ ok: true, orderId: ORDER_ID });
    const { api, user } = setup({ api: actions({ placeOrder }) });

    await user.type(cardField(), "4111111111111111");
    await user.click(placeButton());
    expect(await screen.findByRole("alert")).toHaveTextContent("Something changed");
    await settled();
    expect(api.newAttemptKey).toHaveBeenCalledTimes(1);

    await user.type(cardField(), "4111111111111111");
    await user.click(placeButton());
    await waitFor(() => {
      expect(onPlaced).toHaveBeenCalled();
    });

    expect(placeOrder.mock.calls[1]?.[0]).toMatchObject({ attemptKey: FRESH_KEY });
  });

  it("does not call the server for a card number that is too short, and moves focus to the field", async () => {
    const { api, user } = setup();

    await user.type(cardField(), "4111");
    await user.click(placeButton());

    await waitFor(() => {
      expect(cardField()).toHaveFocus();
    });
    expect(cardField()).toBeInvalid();
    expect(cardField()).toHaveAccessibleDescription(/12 to 19 digits/);
    expect(api.placeOrder).not.toHaveBeenCalled();
  });

  it("shows a card rejected by the server on the field and focuses it", async () => {
    const { user } = setup({ api: actions({ placeOrder: jest.fn().mockResolvedValue(failed("invalid_card")) }) });

    await user.type(cardField(), "4111111111111111");
    await user.click(placeButton());

    await waitFor(() => {
      expect(cardField()).toHaveFocus();
    });
    expect(cardField()).toBeInvalid();
    expect(cardField()).toHaveAccessibleDescription(/card number is not valid/);
  });

  it("asks for an address when none is chosen, focuses the first one and sends nothing", async () => {
    const { api, user } = setup({ addresses: [address(), OTHER_ADDRESS] });

    await user.type(cardField(), "4111111111111111");
    await user.click(placeButton());

    expect(screen.getByText("Choose a shipping address, or add a new one, to continue.")).toBeVisible();
    expect(screen.getByRole("radio", { name: /Ada Lovelace/ })).toHaveFocus();
    expect(api.placeOrder).not.toHaveBeenCalled();

    await user.click(screen.getByRole("radio", { name: /Grace Hopper/ }));
    expect(screen.queryByText(/Choose a shipping address, or add/)).not.toBeInTheDocument();
  });

  it("starts with no address chosen when there are several, and the arrow keys change the choice", async () => {
    const { user } = setup({ addresses: [address(), OTHER_ADDRESS] });

    expect(screen.getAllByRole("radio")).toHaveLength(2);
    expect(screen.getAllByRole("radio").every((radio) => !(radio as HTMLInputElement).checked)).toBe(true);
    screen.getAllByRole("radio")[0]?.focus();
    await user.keyboard("{ArrowDown}");
    expect(screen.getByRole("radio", { name: /Grace Hopper/ })).toBeChecked();
    await user.keyboard("{ArrowUp}");
    expect(screen.getByRole("radio", { name: /Ada Lovelace/ })).toBeChecked();
  });

  it("adds an address inline, selects it and orders to it", async () => {
    const { api, user } = setup();

    await user.click(screen.getByRole("button", { name: "Add a new address" }));
    await user.type(screen.getByLabelText("Full name"), "Grace Hopper");
    await user.type(screen.getByLabelText("Address line 1"), "1 Compiler Way");
    await user.type(screen.getByLabelText("City"), "Arlington");
    await user.type(screen.getByLabelText("Postal code"), "22201");
    await user.type(screen.getByLabelText("Country"), "us");
    await user.click(screen.getByRole("button", { name: "Save address" }));

    const added = await screen.findByRole("radio", { name: /Grace Hopper/ });
    expect(added).toBeChecked();
    await waitFor(() => {
      expect(added).toHaveFocus();
    });
    expect(api.addAddress).toHaveBeenCalledWith(expect.objectContaining({ recipient_name: "Grace Hopper", country: "us" }));
    await settled();

    await user.type(cardField(), "4111111111111111");
    await user.click(placeButton());
    await waitFor(() => {
      expect(api.placeOrder).toHaveBeenCalledWith(expect.objectContaining({ addressId: OTHER_ADDRESS_ID }));
    });
  });

  it("goes back to the Add button when the inline form is cancelled", async () => {
    const { user } = setup();

    await user.click(screen.getByRole("button", { name: "Add a new address" }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.queryByLabelText("Full name")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add a new address" })).toHaveFocus();
  });

  it("opens the address form at once when there are no saved addresses", async () => {
    const { user } = setup({ addresses: [] });

    expect(screen.queryByRole("radio")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Full name")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Cancel" })).not.toBeInTheDocument();

    await user.type(cardField(), "4111111111111111");
    await user.click(placeButton());
    expect(screen.getByText("Choose a shipping address, or add a new one, to continue.")).toBeVisible();
  });

  it("blocks checkout when a line has a flag and links back to the cart", () => {
    const flagged = cart([
      line({ flags: [{ type: "price_changed", old_price: "59.00", new_price: "64.50" }] }),
      line({ sku: "TY-002", name: "Toy robot", flags: [{ type: "insufficient_stock", available: 0 }] }),
    ]);
    setup({ cart: flagged });

    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("You cannot place this order yet");
    expect(alert).toHaveTextContent("Running shoes: Price changed");
    expect(alert).toHaveTextContent("Toy robot: Out of stock");
    expect(within(alert).getByRole("link", { name: "Back to your cart to resolve them" })).toHaveAttribute("href", "/cart");
    expect(placeButton()).toBeDisabled();
  });

  it.each([
    ["cart_flagged", "Back to your cart", "/cart"],
    ["empty_cart", "Back to your cart", "/cart"],
    ["cart_changed", "Reload checkout", "/checkout"],
  ] as const)("offers a way out when the server answers %s", async (kind, label, href) => {
    const { user } = setup({ api: actions({ placeOrder: jest.fn().mockResolvedValue(failed(kind)) }) });

    await user.type(cardField(), "4111111111111111");
    await user.click(placeButton());

    const alert = await screen.findByRole("alert");
    expect(within(alert).getByRole("link", { name: label })).toHaveAttribute("href", href);
    await waitFor(() => {
      expect(within(alert).getByText(/./, { selector: "p" })).toHaveFocus();
    });
  });

  it("tells how long to wait after a rate limit", async () => {
    const { user } = setup({ api: actions({ placeOrder: jest.fn().mockResolvedValue(failed("rate_limited", { retryAfterSeconds: 30 })) }) });

    await user.type(cardField(), "4111111111111111");
    await user.click(placeButton());

    expect(await screen.findByRole("alert")).toHaveTextContent("Wait 30 seconds");
  });

  it("can be completed with the keyboard alone", async () => {
    const { api, user } = setup();

    await user.keyboard("{Tab}");
    while (document.activeElement !== cardField()) {
      await user.keyboard("{Tab}");
    }
    await user.keyboard("4111111111111111{Enter}");

    await waitFor(() => {
      expect(api.placeOrder).toHaveBeenCalledTimes(1);
    });
    expect(placeButton()).toBeInTheDocument();
  });
});
