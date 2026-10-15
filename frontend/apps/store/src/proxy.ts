import type { NextRequest, NextResponse } from "next/server";
import { authRuntime, createProxy } from "@ecommerce/auth/next";
import { isProtectedPath, LOGIN_PATH } from "./lib/paths";

type Handler = (request: NextRequest) => Promise<NextResponse>;

let handler: Handler | undefined;

export function proxy(request: NextRequest): Promise<NextResponse> {
  handler ??= createProxy({
    runtime: authRuntime(),
    guard: { loginPath: LOGIN_PATH, isProtected: isProtectedPath },
    development: process.env.NODE_ENV === "development",
  });
  return handler(request);
}

export const config = {
  matcher: ["/", "/((?!_next/static|_next/image|favicon.ico).*)"],
};
