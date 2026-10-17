import type { AccountsComponents, CatalogComponents, OrdersComponents, PaymentsComponents } from "@ecommerce/api-client";

export type { Category, Product, ProductPage } from "@ecommerce/web-core";

export type ImportView = CatalogComponents["schemas"]["ImportOut"];
export type ImportSummary = CatalogComponents["schemas"]["ImportSummaryOut"];
export type ImportProblem = CatalogComponents["schemas"]["catalog__api__import_schemas__ProblemOut"];
export type ImportProblemsPage = CatalogComponents["schemas"]["ProblemsPageOut"];

export type UserProfile = AccountsComponents["schemas"]["ProfileOut"];
export type UserPage = AccountsComponents["schemas"]["ProfilePageOut"];
export type Role = AccountsComponents["schemas"]["Role"];

export type OrderRow = OrdersComponents["schemas"]["AdminOrderSummaryOut"];
export type OrderListPage = OrdersComponents["schemas"]["AdminOrderPageOut"];
export type OrderDetail = OrdersComponents["schemas"]["AdminOrderDetailOut"];
export type OrderLineRow = OrdersComponents["schemas"]["OrderLineOut"];
export type OrderHistoryRow = OrdersComponents["schemas"]["HistoryEntryOut"];
export type Payment = PaymentsComponents["schemas"]["PaymentOut"];

export type WithEtag<Value> = { value: Value; etag: string };
