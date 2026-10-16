import { NextResponse } from "next/server";
import { clientIpFrom } from "../client-ip";
import type { CookieSpec } from "../cookies";
import type { AuthRuntime } from "../runtime";
import { SessionUnavailableError, type Session } from "../verify";

export type RouteGuardOptions = {
  runtime: AuthRuntime;
  requiredRole?: string;
};

export type RouteAccess = {
  session: Session;
  accessToken: string;
  clientIp: string | undefined;
  cookies: CookieSpec[];
};

export type RouteGuardResult = { ok: true; access: RouteAccess } | { ok: false; response: NextResponse };

const PROBLEM_MEDIA_TYPE = "application/problem+json";
const RETRY_AFTER_SECONDS = "5";

function problem(status: number, title: string, headers: Record<string, string> = {}): NextResponse {
  return NextResponse.json(
    { type: "about:blank", title, status },
    { status, headers: { "content-type": PROBLEM_MEDIA_TYPE, "cache-control": "no-store", ...headers } },
  );
}

export function applyCookies(response: NextResponse, specs: readonly CookieSpec[]): NextResponse {
  for (const { name, value, options } of specs) {
    response.cookies.set(name, value, options);
  }
  return response;
}

export async function guardRoute(
  request: Request,
  { runtime, requiredRole }: RouteGuardOptions,
): Promise<RouteGuardResult> {
  if (request.headers.get("sec-fetch-site") === "cross-site") {
    return { ok: false, response: problem(403, "Cross-site requests are not allowed") };
  }
  const { config } = runtime;
  const cookieHeader = request.headers.get("cookie") ?? "";
  const read = (name: string) =>
    cookieHeader
      .split(";")
      .map((part) => part.trim())
      .find((part) => part.startsWith(`${name}=`))
      ?.slice(name.length + 1);
  const clientIp = clientIpFrom(request.headers);

  let resolution;
  try {
    resolution = await runtime.resolve({
      accessToken: read(config.accessCookieName),
      refreshToken: read(config.refreshCookieName),
      clientIp,
    });
  } catch (error) {
    if (error instanceof SessionUnavailableError) {
      return {
        ok: false,
        response: problem(503, "Service temporarily unavailable", { "retry-after": RETRY_AFTER_SECONDS }),
      };
    }
    throw error;
  }

  const refreshed = resolution.cookies.find((cookie) => cookie.name === config.accessCookieName);
  const accessToken = refreshed?.value || read(config.accessCookieName);
  if (!resolution.session || !accessToken) {
    return { ok: false, response: applyCookies(problem(401, "Authentication required"), resolution.cookies) };
  }
  if (requiredRole !== undefined && resolution.session.role !== requiredRole) {
    return { ok: false, response: applyCookies(problem(403, "Forbidden"), resolution.cookies) };
  }
  return {
    ok: true,
    access: { session: resolution.session, accessToken, clientIp, cookies: resolution.cookies },
  };
}
