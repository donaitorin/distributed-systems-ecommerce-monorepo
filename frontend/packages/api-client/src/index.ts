import type { paths as AccountsPaths } from "./generated/accounts";
import type { paths as AuthPaths } from "./generated/auth";
import type { paths as CartPaths } from "./generated/cart";
import type { paths as CatalogPaths } from "./generated/catalog";
import type { paths as OrdersPaths } from "./generated/orders";
import type { paths as PaymentsPaths } from "./generated/payments";

export type { components as AccountsComponents } from "./generated/accounts";
export type { components as AuthComponents } from "./generated/auth";
export type { components as CartComponents } from "./generated/cart";
export type { components as CatalogComponents } from "./generated/catalog";
export type { components as OrdersComponents } from "./generated/orders";
export type { components as PaymentsComponents } from "./generated/payments";
export type { AccountsPaths, AuthPaths, CartPaths, CatalogPaths, OrdersPaths, PaymentsPaths };

export type GatewayPaths = Omit<AuthPaths, "/health" | "/ready"> &
  Omit<CatalogPaths, "/health" | "/ready"> &
  Omit<AccountsPaths, "/health" | "/ready"> &
  Omit<CartPaths, "/health" | "/ready"> &
  Omit<OrdersPaths, "/health" | "/ready"> &
  Omit<PaymentsPaths, "/health" | "/ready">;

export { createApiClient, buildPath, buildQuery } from "./client";
export type { ApiClient, ApiClientOptions } from "./client";
export {
  ApiError,
  ApiNetworkError,
  PROBLEM_MEDIA_TYPE,
  readProblem,
  type FieldError,
  type ProblemDetails,
} from "./problem";
export type {
  ApiResult,
  HttpMethod,
  OperationOf,
  OptionsArguments,
  PathsWith,
  RequestOptions,
  ResponseBody,
} from "./types";
