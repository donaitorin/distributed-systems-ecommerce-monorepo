import { createApiClient, type CatalogPaths } from "@ecommerce/api-client";
import { authorizationHeaders, authRuntime } from "@ecommerce/auth/next";

export function catalogApi() {
  return createApiClient<CatalogPaths>({
    baseUrl: authRuntime().config.apiBaseUrl,
    headers: authorizationHeaders,
  });
}
