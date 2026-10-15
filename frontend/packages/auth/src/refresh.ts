import { createHash } from "node:crypto";
import { ApiError } from "@ecommerce/api-client";
import type { TokenPair } from "./cookies";

export type RefreshFunction = (refreshToken: string, clientIp?: string) => Promise<TokenPair>;

export type RefreshOptions = {
  clientIp?: string;
  readLatestRefreshToken?: () => Promise<string | undefined> | string | undefined;
};

export type RefreshCoordinator = (
  refreshToken: string,
  options?: RefreshOptions,
) => Promise<TokenPair>;

export class RefreshRejectedError extends Error {
  constructor(cause?: unknown) {
    super("The refresh token was rejected", { cause });
    this.name = "RefreshRejectedError";
  }
}

const REUSE_WINDOW_MS = 10_000;
const REJECTED_STATUSES = new Set([400, 401, 403, 422]);

function fingerprint(token: string): string {
  return createHash("sha256").update(token).digest("hex");
}

function isRejection(error: unknown): boolean {
  return error instanceof ApiError && REJECTED_STATUSES.has(error.status);
}

export function createRefreshCoordinator(
  refresh: RefreshFunction,
  now: () => number = Date.now,
): RefreshCoordinator {
  const inFlight = new Map<string, { result: Promise<TokenPair>; expiresAt: number }>();

  function prune(): void {
    const current = now();
    for (const [key, entry] of inFlight) {
      if (entry.expiresAt <= current) {
        inFlight.delete(key);
      }
    }
  }

  function shared(token: string, clientIp: string | undefined): Promise<TokenPair> {
    prune();
    const key = fingerprint(token);
    const existing = inFlight.get(key);
    if (existing) {
      return existing.result;
    }
    const result = refresh(token, clientIp);
    inFlight.set(key, { result, expiresAt: now() + REUSE_WINDOW_MS });
    result.catch(() => {
      inFlight.delete(key);
    });
    return result;
  }

  return async (refreshToken, options = {}) => {
    try {
      return await shared(refreshToken, options.clientIp);
    } catch (error) {
      if (!isRejection(error)) {
        throw error;
      }
      const latest = await options.readLatestRefreshToken?.();
      if (latest && latest !== refreshToken) {
        try {
          return await shared(latest, options.clientIp);
        } catch (retryError) {
          throw isRejection(retryError) ? new RefreshRejectedError(retryError) : retryError;
        }
      }
      throw new RefreshRejectedError(error);
    }
  };
}
