import type { paths as AccountsPaths } from "./generated/accounts";
import type { paths as AuthPaths } from "./generated/auth";
import type { paths as CatalogPaths } from "./generated/catalog";

export type { components as AccountsComponents } from "./generated/accounts";
export type { components as AuthComponents } from "./generated/auth";
export type { components as CatalogComponents } from "./generated/catalog";
export type { AccountsPaths, AuthPaths, CatalogPaths };

export type GatewayPaths = Omit<AuthPaths, "/health" | "/ready"> &
  Omit<CatalogPaths, "/health" | "/ready"> &
  Omit<AccountsPaths, "/health" | "/ready">;

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
