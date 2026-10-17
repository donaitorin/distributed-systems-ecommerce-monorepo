import { isFailure, type Failure } from "@ecommerce/web-core";
import { toOrdersQuery, type OrderSearchState } from "../lib/order-search";
import type { OrderDetail, OrderListPage, Payment } from "../lib/types";
import { gatewayApi } from "./gateway";
import { guarded } from "./guarded";

export type PaymentLookup = { payment: Payment } | { payment: null; unavailable: boolean };
export type OrderWithPayment = { order: OrderDetail; payment: PaymentLookup };

const NOT_FOUND = 404;
const ORDER_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export async function loadOrderPage(state: OrderSearchState): Promise<OrderListPage | Failure> {
  return guarded(async () => {
    const { data } = await gatewayApi().get("/api/v1/admin/orders", { query: toOrdersQuery(state) });
    return data;
  });
}

async function loadPayment(orderId: string): Promise<PaymentLookup> {
  const result = await guarded(async () => {
    const { data } = await gatewayApi().get("/api/v1/payments/{order_id}", { params: { order_id: orderId } });
    return data;
  });
  if (isFailure(result)) {
    return { payment: null, unavailable: result.status !== NOT_FOUND };
  }
  return { payment: result };
}

export async function loadOrder(orderId: string): Promise<OrderWithPayment | Failure> {
  if (!ORDER_ID.test(orderId)) {
    return { ok: false, status: NOT_FOUND, title: "Order not found", fieldErrors: {} };
  }
  const order = await guarded(async () => {
    const { data } = await gatewayApi().get("/api/v1/admin/orders/{order_id}", { params: { order_id: orderId } });
    return data;
  });
  if (isFailure(order)) {
    return order;
  }
  return { order, payment: await loadPayment(orderId) };
}
