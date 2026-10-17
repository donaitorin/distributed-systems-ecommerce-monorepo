import type { Metadata } from "next";
import { requireSession } from "@ecommerce/auth/next";
import { ButtonLink, EmptyState } from "@ecommerce/ui";
import { isFailure } from "@ecommerce/web-core";
import { CheckoutScreen } from "../../components/checkout/checkout-screen";
import { isCartFailure } from "../../lib/cart";
import { CHECKOUT_PATH, LOGIN_PATH, PRODUCTS_PATH } from "../../lib/paths";
import { loadAddresses } from "../../server/addresses";
import { loadCart } from "../../server/cart";
import { addCheckoutAddressAction, newAttemptKeyAction, placeOrderAction } from "./actions";

export const metadata: Metadata = { title: "Checkout", robots: { index: false } };

const ACTIONS = { placeOrder: placeOrderAction, newAttemptKey: newAttemptKeyAction, addAddress: addCheckoutAddressAction };

export default async function CheckoutPage() {
  await requireSession({ loginPath: LOGIN_PATH });
  const [cart, addresses] = await Promise.all([loadCart(CHECKOUT_PATH), loadAddresses(CHECKOUT_PATH)]);
  if (isCartFailure(cart) || isFailure(addresses)) {
    return (
      <section aria-labelledby="checkout-error-heading" className="flex flex-col gap-4">
        <h1 id="checkout-error-heading" className="text-3xl font-semibold">
          Checkout
        </h1>
        <div role="alert" className="flex flex-col items-start gap-3 text-base text-danger-strong">
          <p>Checkout could not be loaded right now. Nothing was ordered. Try again in a moment.</p>
          <a href={CHECKOUT_PATH} className="text-accent-strong underline">
            Try again
          </a>
        </div>
      </section>
    );
  }
  if (cart.items.length === 0) {
    return (
      <section aria-labelledby="checkout-empty-heading" className="flex flex-col gap-4">
        <h1 id="checkout-empty-heading" className="text-3xl font-semibold">
          Checkout
        </h1>
        <EmptyState
          title="Your cart is empty"
          description="Add a product from the catalog before you check out."
          action={<ButtonLink href={PRODUCTS_PATH}>Browse products</ButtonLink>}
        />
      </section>
    );
  }
  return <CheckoutScreen cart={cart} addresses={addresses} attemptKey={crypto.randomUUID()} actions={ACTIONS} />;
}
