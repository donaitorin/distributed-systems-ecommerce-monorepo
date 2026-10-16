import type { AccountsComponents, CatalogComponents } from "@ecommerce/api-client";

export type Product = CatalogComponents["schemas"]["ProductOut"];
export type Category = CatalogComponents["schemas"]["CategoryOut"];
export type ProductPage = CatalogComponents["schemas"]["ProductPage"];

export type ImportView = CatalogComponents["schemas"]["ImportOut"];
export type ImportSummary = CatalogComponents["schemas"]["ImportSummaryOut"];
export type ImportProblem = CatalogComponents["schemas"]["catalog__api__import_schemas__ProblemOut"];
export type ImportProblemsPage = CatalogComponents["schemas"]["ProblemsPageOut"];

export type UserProfile = AccountsComponents["schemas"]["ProfileOut"];
export type UserPage = AccountsComponents["schemas"]["ProfilePageOut"];
export type Role = AccountsComponents["schemas"]["Role"];

export type WithEtag<Value> = { value: Value; etag: string };
