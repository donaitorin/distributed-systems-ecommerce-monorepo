import { NextResponse, type NextRequest } from "next/server";
import { clientIpFrom } from "../client-ip";
import type { CookieSpec } from "../cookies";
import type { AuthRuntime } from "../runtime";
import { SessionUnavailableError } from "../verify";
import { withCookies } from "./cookie-header";
import {
  buildContentSecurityPolicy,
  CONTENT_SECURITY_POLICY_HEADER,
  createNonce,
  NONCE_HEADER,
} from "./security";

export type GuardOptions = {
  loginPath: string;
  requiredRole?: string;
  isProtected?: (pathname: string) => boolean;
};

export type ProxyOptions = {
  runtime: AuthRuntime;
  guard?: GuardOptions;
  development?: boolean;
};

const SERVICE_UNAVAILABLE = 503;
const RETRY_AFTER_SECONDS = "5";

function applyCookies(response: NextResponse, specs: readonly CookieSpec[]): void {
  for (const { name, value, options } of specs) {
    response.cookies.set(name, value, options);
  }
}

export function createProxy({ runtime, guard, development = false }: ProxyOptions) {
  const { config } = runtime;

  return async function proxy(request: NextRequest): Promise<NextResponse> {
    const nonce = createNonce();
    const policy = buildContentSecurityPolicy({ nonce, development });
    const { pathname, search } = request.nextUrl;

    const secured = (response: NextResponse, cookies: readonly CookieSpec[] = []): NextResponse => {
      response.headers.set(CONTENT_SECURITY_POLICY_HEADER, policy);
      applyCookies(response, cookies);
      return response;
    };

    const redirectToLogin = (cookies: readonly CookieSpec[], reason?: string): NextResponse => {
      const url = request.nextUrl.clone();
      url.pathname = guard?.loginPath ?? "/";
      url.search = "";
      url.searchParams.set("next", `${pathname}${search}`);
      if (reason) {
        url.searchParams.set("reason", reason);
      }
      return secured(NextResponse.redirect(url), cookies);
    };

    let cookies: readonly CookieSpec[] = [];
    const protectedPath =
      guard !== undefined &&
      pathname !== guard.loginPath &&
      (guard.isProtected?.(pathname) ?? true);

    if (guard && protectedPath) {
      let resolution;
      try {
        resolution = await runtime.resolve({
          accessToken: request.cookies.get(config.accessCookieName)?.value,
          refreshToken: request.cookies.get(config.refreshCookieName)?.value,
          clientIp: clientIpFrom(request.headers),
        });
      } catch (error) {
        if (error instanceof SessionUnavailableError) {
          return secured(
            new NextResponse("Service temporarily unavailable", {
              status: SERVICE_UNAVAILABLE,
              headers: { "Retry-After": RETRY_AFTER_SECONDS },
            }),
          );
        }
        throw error;
      }
      cookies = resolution.cookies;
      if (!resolution.session) {
        return redirectToLogin(cookies);
      }
      if (guard.requiredRole && resolution.session.role !== guard.requiredRole) {
        return redirectToLogin(cookies, "forbidden");
      }
    }

    const requestHeaders = new Headers(request.headers);
    requestHeaders.set(NONCE_HEADER, nonce);
    requestHeaders.set(CONTENT_SECURITY_POLICY_HEADER, policy);
    if (cookies.length > 0) {
      requestHeaders.set("cookie", withCookies(request.headers.get("cookie"), cookies));
    }
    return secured(NextResponse.next({ request: { headers: requestHeaders } }), cookies);
  };
}
