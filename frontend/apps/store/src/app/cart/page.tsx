import type { Metadata } from "next";
import { requireSession } from "@ecommerce/auth/next";
import { CartView } from "../../components/cart/cart-view";
import { isCartFailure } from "../../lib/cart";
import { CART_PATH, LOGIN_PATH } from "../../lib/paths";
import { loadCart } from "../../server/cart";
import { clearCartAction, removeItemAction, setQuantityAction } from "./actions";

export const metadata: Metadata = { title: "Your cart", robots: { index: false } };

const ACTIONS = { setQuantity: setQuantityAction, removeItem: removeItemAction, clearCart: clearCartAction };

export default async function CartPage() {
  await requireSession({ loginPath: LOGIN_PATH });
  const cart = await loadCart(CART_PATH);
  if (isCartFailure(cart)) {
    return (
      <section aria-labelledby="cart-error-heading" className="flex flex-col gap-4">
        <h1 id="cart-error-heading" className="text-3xl font-semibold">
          Your cart
        </h1>
        <div role="alert" className="flex flex-col items-start gap-3 text-base text-danger-strong">
          <p>Your cart could not be loaded right now. Nothing was lost. Try again in a moment.</p>
          <a href={CART_PATH} className="text-accent-strong underline">
            Try again
          </a>
        </div>
      </section>
    );
  }
  return <CartView cart={cart} actions={ACTIONS} />;
}
