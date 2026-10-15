import { clearedCookies, sessionCookies, type CookieSpec } from "./cookies";
import type { AuthConfig } from "./config";
import { RefreshRejectedError, type RefreshCoordinator } from "./refresh";
import { SessionUnavailableError, type Session, type SessionVerifier } from "./verify";

export type SessionInput = {
  accessToken?: string;
  refreshToken?: string;
  clientIp?: string;
  readLatestRefreshToken?: () => Promise<string | undefined> | string | undefined;
};

export type SessionResolution = {
  session: Session | null;
  cookies: CookieSpec[];
};

export type SessionResolver = (input: SessionInput) => Promise<SessionResolution>;

export function createSessionResolver(
  config: AuthConfig,
  verify: SessionVerifier,
  refresh: RefreshCoordinator,
): SessionResolver {
  return async ({ accessToken, refreshToken, clientIp, readLatestRefreshToken }) => {
    if (accessToken) {
      const session = await verify(accessToken);
      if (session) {
        return { session, cookies: [] };
      }
    }
    if (!refreshToken) {
      return { session: null, cookies: accessToken ? clearedCookies(config) : [] };
    }
    try {
      const tokens = await refresh(refreshToken, { clientIp, readLatestRefreshToken });
      const session = await verify(tokens.accessToken);
      if (!session) {
        return { session: null, cookies: clearedCookies(config) };
      }
      return { session, cookies: sessionCookies(config, tokens) };
    } catch (error) {
      if (error instanceof RefreshRejectedError) {
        return { session: null, cookies: clearedCookies(config) };
      }
      if (error instanceof SessionUnavailableError) {
        throw error;
      }
      throw new SessionUnavailableError(error);
    }
  };
}
