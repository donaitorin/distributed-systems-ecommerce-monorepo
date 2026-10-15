import type { JWTVerifyGetKey } from "jose";
import { createAuthApi, type AuthApi } from "./auth-api";
import type { AuthConfig } from "./config";
import { createRefreshCoordinator, type RefreshCoordinator } from "./refresh";
import { createSessionResolver, type SessionResolver } from "./resolve-session";
import { createSessionVerifier, type SessionVerifier } from "./verify";

export type AuthRuntime = {
  config: AuthConfig;
  api: AuthApi;
  verify: SessionVerifier;
  refresh: RefreshCoordinator;
  resolve: SessionResolver;
};

export type RuntimeOverrides = {
  fetch?: typeof fetch;
  keySet?: JWTVerifyGetKey;
};

export function createAuthRuntime(config: AuthConfig, overrides: RuntimeOverrides = {}): AuthRuntime {
  const api = createAuthApi(config, overrides.fetch);
  const verify = createSessionVerifier(config, overrides.keySet);
  const refresh = createRefreshCoordinator(api.refresh);
  return { config, api, verify, refresh, resolve: createSessionResolver(config, verify, refresh) };
}
