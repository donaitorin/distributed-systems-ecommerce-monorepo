import type { CatalogComponents } from "@ecommerce/api-client";

export type Product = CatalogComponents["schemas"]["ProductOut"];
export type Category = CatalogComponents["schemas"]["CategoryOut"];
export type ProductPage = CatalogComponents["schemas"]["ProductPage"];

export type WithEtag<Value> = { value: Value; etag: string };
