import { ApiError, createApiClient, type ApiClient, type GatewayPaths } from "@ecommerce/api-client";
import type { AuthConfig } from "./config";
import type { TokenPair } from "./cookies";
import { forwardingHeaders } from "./client-ip";

export type Credentials = {
  email: string;
  password: string;
};

export type RegisteredUser = {
  id: string;
  email: string;
  role: string;
};

export type AuthApi = {
  register: (credentials: Credentials, clientIp?: string) => Promise<RegisteredUser>;
  login: (credentials: Credentials, clientIp?: string) => Promise<TokenPair>;
  refresh: (refreshToken: string, clientIp?: string) => Promise<TokenPair>;
  logout: (refreshToken: string, clientIp?: string) => Promise<void>;
};

type TokensResponse = {
  access_token: string;
  refresh_token: string;
  expires_in: number;
};

function toTokenPair(tokens: TokensResponse): TokenPair {
  return {
    accessToken: tokens.access_token,
    refreshToken: tokens.refresh_token,
    expiresInSeconds: tokens.expires_in,
  };
}

export function createAuthApi(
  config: AuthConfig,
  fetchImplementation?: typeof fetch,
  client: ApiClient<GatewayPaths> = createApiClient<GatewayPaths>({
    baseUrl: config.apiBaseUrl,
    timeoutMs: config.requestTimeoutMs,
    ...(fetchImplementation ? { fetch: fetchImplementation } : {}),
  }),
): AuthApi {
  return {
    async register(credentials, clientIp) {
      const { data } = await client.post("/api/v1/auth/register", {
        body: credentials,
        headers: forwardingHeaders(clientIp),
      });
      return data;
    },
    async login(credentials, clientIp) {
      const { data } = await client.post("/api/v1/auth/login", {
        body: credentials,
        headers: forwardingHeaders(clientIp),
      });
      return toTokenPair(data);
    },
    async refresh(refreshToken, clientIp) {
      const { data } = await client.post("/api/v1/auth/refresh", {
        body: { refresh_token: refreshToken },
        headers: forwardingHeaders(clientIp),
      });
      return toTokenPair(data);
    },
    async logout(refreshToken, clientIp) {
      try {
        await client.post("/api/v1/auth/logout", {
          body: { refresh_token: refreshToken },
          headers: forwardingHeaders(clientIp),
        });
      } catch (error) {
        if (!(error instanceof ApiError)) {
          throw error;
        }
      }
    },
  };
}
