import type { Product } from "@ecommerce/web-core";

export const ADD_TO_CART_SLOT_ID = "add-to-cart-slot";

export function AddToCartSlot({ product }: { product: Pick<Product, "sku" | "stock"> }) {
  if (product.stock <= 0) {
    return (
      <p id="add-to-cart-unavailable" className="max-w-prose text-base font-medium text-danger-strong">
        This product is out of stock and cannot be added to a cart.
      </p>
    );
  }
  return <div id={ADD_TO_CART_SLOT_ID} data-sku={product.sku} />;
}
