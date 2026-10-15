import { createLocalJWKSet, exportJWK, generateKeyPair, SignJWT, type JWK, type JWTVerifyGetKey } from "jose";
import { loadAuthConfig, type AuthConfig } from "../../src";

export const CONFIG: AuthConfig = loadAuthConfig({
  API_BASE_URL: "http://gateway.test",
  AUTH_COOKIE_SECURE: "false",
});

export type TestKeys = {
  keySet: JWTVerifyGetKey;
  sign: (claims?: Record<string, unknown>, options?: { expiresIn?: string; issuer?: string; audience?: string }) => Promise<string>;
  jwks: { keys: JWK[] };
};

export async function createTestKeys(kid = "test-key"): Promise<TestKeys> {
  const { publicKey, privateKey } = await generateKeyPair("RS256");
  const jwk = { ...(await exportJWK(publicKey)), kid, alg: "RS256", use: "sig" };
  return {
    keySet: createLocalJWKSet({ keys: [jwk] }),
    jwks: { keys: [jwk] },
    sign: (claims = {}, options = {}) =>
      new SignJWT({ role: "customer", email: "ada@example.com", ...claims })
        .setProtectedHeader({ alg: "RS256", kid })
        .setSubject("user-1")
        .setIssuer(options.issuer ?? CONFIG.issuer)
        .setAudience(options.audience ?? CONFIG.audience)
        .setIssuedAt()
        .setExpirationTime(options.expiresIn ?? "15m")
        .sign(privateKey),
  };
}

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

export function problemResponse(status: number, title = "Unauthorized"): Response {
  return new Response(JSON.stringify({ type: "about:blank", title, status }), {
    status,
    headers: { "content-type": "application/problem+json" },
  });
}

export function tokensBody(access: string, refresh: string, expiresIn = 900) {
  return { access_token: access, refresh_token: refresh, token_type: "Bearer", expires_in: expiresIn };
}
