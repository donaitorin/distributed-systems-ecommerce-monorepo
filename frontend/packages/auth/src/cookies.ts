import type { AuthConfig } from "./config";

export type TokenPair = {
  accessToken: string;
  refreshToken: string;
  expiresInSeconds: number;
};

export type CookieOptions = {
  httpOnly: true;
  secure: boolean;
  sameSite: "lax";
  path: "/";
  maxAge: number;
};

export type CookieSpec = {
  name: string;
  value: string;
  options: CookieOptions;
};

function options(config: AuthConfig, maxAge: number): CookieOptions {
  return { httpOnly: true, secure: config.secureCookies, sameSite: "lax", path: "/", maxAge };
}

export function sessionCookies(config: AuthConfig, tokens: TokenPair): CookieSpec[] {
  return [
    {
      name: config.accessCookieName,
      value: tokens.accessToken,
      options: options(config, Math.max(1, Math.floor(tokens.expiresInSeconds))),
    },
    {
      name: config.refreshCookieName,
      value: tokens.refreshToken,
      options: options(config, config.refreshCookieMaxAgeSeconds),
    },
  ];
}

export function clearedCookies(config: AuthConfig): CookieSpec[] {
  return [config.accessCookieName, config.refreshCookieName].map((name) => ({
    name,
    value: "",
    options: options(config, 0),
  }));
}
