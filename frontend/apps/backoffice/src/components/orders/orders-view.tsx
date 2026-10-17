"use client";

import { useTransition } from "react";
import { useQueryStates } from "nuqs";
import { Button, Input, OrderStatusBadge, ORDER_STATUSES, orderStatusLabel, Select, Table, type SelectOption, type TableColumn } from "@ecommerce/ui";
import { formatDateTime, type Failure } from "@ecommerce/web-core";
import { customerLabel, shortOrderId } from "../../lib/order-format";
import { dateRangeError, hasOrderFilters, ORDER_PAGE_SIZES, orderSearchParsers } from "../../lib/order-search";
import { ORDERS_PATH, ZONE_PATH } from "../../lib/paths";
import type { OrderListPage, OrderRow } from "../../lib/types";

export type OrdersViewProps = {
  page: OrderListPage | null;
  failure: Failure | null;
};

const ANY = "any";
const STATUS_OPTIONS: readonly SelectOption[] = [
  { value: ANY, label: "Any status" },
  ...ORDER_STATUSES.map((status) => ({ value: status, label: orderStatusLabel(status) })),
];
const MONEY = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });

export function orderHref(order: Pick<OrderRow, "id">): string {
  return `${ZONE_PATH}${ORDERS_PATH}/${order.id}`;
}

function money(value: string): string {
  return MONEY.format(Number(value));
}

function failureText(failure: Failure): string {
  if (failure.status === 422) {
    return failure.fieldErrors.cursor !== undefined
      ? "This page link no longer matches the current filters."
      : "Some filters are not valid. Adjust them and try again.";
  }
  if (failure.status === 503 || failure.status === null) {
    return "The order list is not available right now. Try again in a moment.";
  }
  return failure.detail ?? failure.title;
}

export function OrdersView({ page, failure }: OrdersViewProps) {
  const [pending, startTransition] = useTransition();
  const [state, setState] = useQueryStates(orderSearchParsers, { history: "push", shallow: false, startTransition });
  const rangeError = dateRangeError(state);

  const orderLink = (order: OrderRow) => (
    <a href={orderHref(order)} className="font-medium text-accent-strong underline">
      Order {shortOrderId(order.id)}
    </a>
  );
  const when = (order: OrderRow) => formatDateTime(order.created_at);
  const customer = (order: OrderRow) => <span className="break-all">{customerLabel(order)}</span>;

  const columns: readonly TableColumn<OrderRow>[] = [
    { key: "order", header: "Order", cell: orderLink },
    { key: "date", header: "Placed", cell: when },
    { key: "customer", header: "Customer", cell: customer },
    { key: "status", header: "Status", cell: (order) => <OrderStatusBadge status={order.status} /> },
    { key: "items", header: "Items", cell: (order) => order.item_count, align: "right" },
    { key: "total", header: "Total", cell: (order) => money(order.total), align: "right" },
  ];

  const items = page?.items ?? [];
  const hasMore = Boolean(page?.next_cursor);

  return (
    <div className="flex flex-col gap-6">
      <form
        role="search"
        aria-label="Filter orders"
        className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5"
        onSubmit={(event) => {
          event.preventDefault();
        }}
      >
        <Select
          label="Status"
          options={STATUS_OPTIONS}
          value={state.status ?? ANY}
          onValueChange={(value) => {
            void setState({ status: value === ANY ? null : (value as OrderRow["status"]), cursor: null });
          }}
        />
        <Input
          label="Placed from"
          type="date"
          name="from"
          value={state.from ?? ""}
          onChange={(event) => {
            void setState({ from: event.target.value || null, cursor: null });
          }}
        />
        <Input
          label="Placed until"
          type="date"
          name="to"
          value={state.to ?? ""}
          {...(rangeError ? { error: rangeError } : {})}
          onChange={(event) => {
            void setState({ to: event.target.value || null, cursor: null });
          }}
        />
        <Select
          label="Orders per page"
          options={ORDER_PAGE_SIZES.map((size) => ({ value: String(size), label: `${size} per page` }))}
          value={String(state.limit)}
          onValueChange={(value) => {
            void setState({ limit: Number(value), cursor: null });
          }}
        />
        {hasOrderFilters(state) ? (
          <div className="flex items-end">
            <Button
              variant="secondary"
              onClick={() => {
                void setState({ status: null, from: null, to: null, cursor: null });
              }}
            >
              Clear filters
            </Button>
          </div>
        ) : null}
      </form>
      <div aria-busy={pending} className={pending ? "flex flex-col gap-4 opacity-60" : "flex flex-col gap-4"}>
        <Table
          caption="Order list"
          columns={columns}
          rows={items}
          getRowKey={(order) => order.id}
          error={rangeError ?? (failure ? failureText(failure) : undefined)}
          emptyMessage="No orders match these filters."
          renderCard={(order) => (
            <div className="flex flex-col gap-2">
              <p>{orderLink(order)}</p>
              <p className="text-sm text-secondary">{when(order)}</p>
              <p className="text-sm">{customer(order)}</p>
              <div className="flex items-center justify-between gap-3">
                <OrderStatusBadge status={order.status} />
                <p className="text-sm font-medium">
                  {order.item_count === 1 ? "1 item" : `${order.item_count} items`}, {money(order.total)}
                </p>
              </div>
            </div>
          )}
        />
        {failure?.fieldErrors.cursor !== undefined ? (
          <div>
            <Button
              variant="secondary"
              onClick={() => {
                void setState({ cursor: null });
              }}
            >
              Back to the first page
            </Button>
          </div>
        ) : null}
        {page ? (
          <nav aria-label="Order pages" className="flex flex-wrap items-center justify-between gap-4">
            <p role="status" className="text-sm text-secondary">
              {items.length === 1 ? "1 order on this page" : `${items.length} orders on this page`}
              {hasMore ? ", more available" : ""}
            </p>
            <div className="flex gap-2">
              <Button
                variant="secondary"
                disabled={state.cursor === null || pending}
                onClick={() => {
                  void setState({ cursor: null });
                }}
              >
                First page
              </Button>
              <Button
                variant="secondary"
                disabled={!hasMore || pending}
                onClick={() => {
                  void setState({ cursor: page.next_cursor ?? null });
                }}
              >
                Next
              </Button>
            </div>
          </nav>
        ) : null}
      </div>
    </div>
  );
}
