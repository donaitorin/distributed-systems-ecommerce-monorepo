import {
  createRemoteJWKSet,
  customFetch,
  errors,
  jwtVerify,
  type JWTPayload,
  type JWTVerifyGetKey,
} from "jose";
import type { AuthConfig } from "./config";

export type Session = {
  userId: string;
  role: string;
  email?: string;
  expiresAt: Date;
};

export type SessionVerifier = (token: string) => Promise<Session | null>;

export class SessionUnavailableError extends Error {
  constructor(cause?: unknown) {
    super("The session could not be verified right now", { cause });
    this.name = "SessionUnavailableError";
  }
}

const JWKS_CACHE_MAX_AGE_MS = 10 * 60 * 1000;
const JWKS_COOLDOWN_MS = 30 * 1000;

const INVALID_TOKEN_ERRORS = [
  errors.JWTExpired,
  errors.JWTClaimValidationFailed,
  errors.JWTInvalid,
  errors.JWSInvalid,
  errors.JWSSignatureVerificationFailed,
  errors.JWKSNoMatchingKey,
  errors.JOSEAlgNotAllowed,
] as const;

function isInvalidToken(error: unknown): boolean {
  return INVALID_TOKEN_ERRORS.some((type) => error instanceof type);
}

function toSession(payload: JWTPayload): Session | null {
  const { sub, role, email, exp } = payload;
  if (typeof sub !== "string" || typeof role !== "string" || typeof exp !== "number") {
    return null;
  }
  return {
    userId: sub,
    role,
    ...(typeof email === "string" ? { email } : {}),
    expiresAt: new Date(exp * 1000),
  };
}

export function createRemoteKeySet(config: AuthConfig, fetchImplementation?: typeof fetch): JWTVerifyGetKey {
  return createRemoteJWKSet(new URL(config.jwksUrl), {
    cacheMaxAge: JWKS_CACHE_MAX_AGE_MS,
    cooldownDuration: JWKS_COOLDOWN_MS,
    timeoutDuration: config.requestTimeoutMs,
    ...(fetchImplementation ? { [customFetch]: fetchImplementation } : {}),
  });
}

export function createSessionVerifier(
  config: AuthConfig,
  keySet: JWTVerifyGetKey = createRemoteKeySet(config),
): SessionVerifier {
  return async (token) => {
    try {
      const { payload } = await jwtVerify(token, keySet, {
        issuer: config.issuer,
        audience: config.audience,
        algorithms: ["RS256"],
      });
      return toSession(payload);
    } catch (error) {
      if (isInvalidToken(error)) {
        return null;
      }
      throw new SessionUnavailableError(error);
    }
  };
}
