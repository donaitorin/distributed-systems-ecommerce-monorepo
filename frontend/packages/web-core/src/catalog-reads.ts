import type { ApiClient, CatalogPaths } from "@ecommerce/api-client";
import type { Category, ProductPage } from "./catalog-types";
import { toCatalogQuery, type ProductSearchState } from "./product-search";

export type CatalogApi = ApiClient<CatalogPaths>;

export async function fetchProductPage(api: CatalogApi, state: ProductSearchState): Promise<ProductPage> {
  const { data } = await api.get("/api/v1/products", { query: toCatalogQuery(state) });
  return data;
}

export async function fetchCategories(api: CatalogApi): Promise<Category[]> {
  const { data } = await api.get("/api/v1/categories");
  return data;
}
