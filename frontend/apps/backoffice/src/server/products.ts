import { entityTag } from "../lib/entity-tag";
import { toCatalogQuery, type Failure, type ProductSearchState } from "@ecommerce/web-core";
import type { Category, Product, ProductPage, WithEtag } from "../lib/types";
import { catalogApi } from "./catalog";
import { guarded } from "./guarded";

export async function loadProductPage(state: ProductSearchState): Promise<ProductPage | Failure> {
  return guarded(async () => {
    const { data } = await catalogApi().get("/api/v1/products", { query: toCatalogQuery(state) });
    return data;
  });
}

export async function loadCategories(): Promise<Category[] | Failure> {
  return guarded(async () => {
    const { data } = await catalogApi().get("/api/v1/categories");
    return data;
  });
}

export async function loadProduct(sku: string): Promise<WithEtag<Product> | Failure> {
  return guarded(async () => {
    const { data, response } = await catalogApi().get("/api/v1/products/{sku}", { params: { sku } });
    return { value: data, etag: response.headers.get("etag") ?? entityTag(data.version) };
  });
}

export function isFailure(result: unknown): result is Failure {
  return typeof result === "object" && result !== null && (result as { ok?: unknown }).ok === false;
}
