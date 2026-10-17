import type { Product } from "@ecommerce/web-core";
import type { AddToCart } from "../../lib/cart";
import { AddToCartForm } from "../cart/add-to-cart-form";

export const ADD_TO_CART_SLOT_ID = "add-to-cart-slot";

export function AddToCartSlot({
  product,
  add,
}: {
  product: Pick<Product, "sku" | "name" | "stock">;
  add: AddToCart;
}) {
  return (
    <div id={ADD_TO_CART_SLOT_ID} data-sku={product.sku}>
      <AddToCartForm sku={product.sku} name={product.name} stock={product.stock} add={add} />
    </div>
  );
}
