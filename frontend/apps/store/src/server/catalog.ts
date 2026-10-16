import { cache } from "react";
import { createApiClient, type CatalogPaths } from "@ecommerce/api-client";
import { authorizationHeaders, authRuntime } from "@ecommerce/auth/next";
import {
  fetchCategories,
  fetchProductPage,
  settle,
  type Category,
  type Failure,
  type Product,
  type ProductPage,
  type ProductSearchState,
} from "@ecommerce/web-core";

function catalogApi() {
  return createApiClient<CatalogPaths>({
    baseUrl: authRuntime().config.apiBaseUrl,
    headers: authorizationHeaders,
  });
}

export function loadProductPage(state: ProductSearchState): Promise<ProductPage | Failure> {
  return settle(() => fetchProductPage(catalogApi(), state));
}

export function loadCategories(): Promise<Category[] | Failure> {
  return settle(() => fetchCategories(catalogApi()));
}

export const loadProduct = cache(function loadProduct(sku: string): Promise<Product | Failure> {
  return settle(async () => {
    const { data } = await catalogApi().get("/api/v1/products/{sku}", { params: { sku } });
    return data;
  });
});
