import type { Cart, CartLine } from "../../src/lib/cart";

export function line(overrides: Partial<CartLine> = {}): CartLine {
  return {
    sku: "RS-001",
    name: "Running shoes",
    quantity: 2,
    price: "59.00",
    line_total: "118.00",
    thumbnail_url: "/media/products/RS-001/a-400.webp",
    flags: [],
    ...overrides,
  };
}

export function cart(items: CartLine[] = [line(), line({ sku: "TY-002", name: "Toy robot", quantity: 1, price: "19.50", line_total: "19.50", thumbnail_url: null })]): Cart {
  const units = items.reduce((total, item) => total + item.quantity, 0);
  const subtotal = items.reduce((total, item) => total + Number(item.line_total), 0);
  return { items, item_count: units, subtotal: subtotal.toFixed(2) };
}
