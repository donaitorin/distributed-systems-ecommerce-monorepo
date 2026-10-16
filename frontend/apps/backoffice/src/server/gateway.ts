import { createApiClient, type GatewayPaths } from "@ecommerce/api-client";
import { authorizationHeaders, authRuntime } from "@ecommerce/auth/next";

export function gatewayApi() {
  return createApiClient<GatewayPaths>({
    baseUrl: authRuntime().config.apiBaseUrl,
    headers: authorizationHeaders,
  });
}
