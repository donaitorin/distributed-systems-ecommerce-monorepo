import { ApiError, type ProblemDetails } from "@ecommerce/api-client";
import { cookies, headers } from "next/headers";
import { redirect } from "next/navigation";
import { clientIpFrom, forwardingHeaders } from "../client-ip";
import { loadAuthConfig } from "../config";
import { clearedCookies, sessionCookies, type CookieSpec } from "../cookies";
import type { Credentials, RegisteredUser } from "../auth-api";
import { createAuthRuntime, type AuthRuntime } from "../runtime";
import { SessionUnavailableError, type Session } from "../verify";

export type SignInResult =
  | { ok: true; session: Session }
  | { ok: false; problem: ProblemDetails; retryAfterSeconds?: number };
export type RegisterResult =
  | { ok: true; user: RegisteredUser }
  | { ok: false; problem: ProblemDetails };

let runtime: AuthRuntime | undefined;

export function authRuntime(): AuthRuntime {
  runtime ??= createAuthRuntime(loadAuthConfig(process.env));
  return runtime;
}

export function resetAuthRuntime(replacement?: AuthRuntime): void {
  runtime = replacement;
}

async function writeCookies(specs: readonly CookieSpec[]): Promise<void> {
  const store = await cookies();
  for (const { name, value, options } of specs) {
    store.set(name, value, options);
  }
}

async function currentClientIp(): Promise<string | undefined> {
  return clientIpFrom(await headers());
}

export async function getSession(): Promise<Session | null> {
  const { config, verify } = authRuntime();
  const token = (await cookies()).get(config.accessCookieName)?.value;
  if (!token) {
    return null;
  }
  try {
    return await verify(token);
  } catch (error) {
    if (error instanceof SessionUnavailableError) {
      return null;
    }
    throw error;
  }
}

export async function authorizationHeaders(): Promise<Record<string, string>> {
  const token = (await cookies()).get(authRuntime().config.accessCookieName)?.value;
  return {
    ...(token ? { authorization: `Bearer ${token}` } : {}),
    ...forwardingHeaders(await currentClientIp()),
  };
}

export type RequireSessionOptions = {
  loginPath: string;
  role?: string;
};

export async function requireSession({ loginPath, role }: RequireSessionOptions): Promise<Session> {
  const session = await getSession();
  if (!session || (role !== undefined && session.role !== role)) {
    redirect(loginPath);
  }
  return session;
}

export async function signIn(credentials: Credentials): Promise<SignInResult> {
  const { api, verify } = authRuntime();
  try {
    const tokens = await api.login(credentials, await currentClientIp());
    const session = await verify(tokens.accessToken);
    if (!session) {
      throw new SessionUnavailableError();
    }
    await writeCookies(sessionCookies(authRuntime().config, tokens));
    return { ok: true, session };
  } catch (error) {
    if (error instanceof ApiError) {
      return {
        ok: false,
        problem: error.problem,
        ...(error.retryAfterSeconds !== undefined ? { retryAfterSeconds: error.retryAfterSeconds } : {}),
      };
    }
    throw error;
  }
}

export async function registerAccount(credentials: Credentials): Promise<RegisterResult> {
  try {
    const user = await authRuntime().api.register(credentials, await currentClientIp());
    return { ok: true, user };
  } catch (error) {
    if (error instanceof ApiError) {
      return { ok: false, problem: error.problem };
    }
    throw error;
  }
}

export async function signOut(): Promise<void> {
  const { api, config } = authRuntime();
  const refreshToken = (await cookies()).get(config.refreshCookieName)?.value;
  try {
    if (refreshToken) {
      await api.logout(refreshToken, await currentClientIp());
    }
  } finally {
    await writeCookies(clearedCookies(config));
  }
}
