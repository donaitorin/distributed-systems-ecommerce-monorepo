export type ContentSecurityPolicyOptions = {
  nonce: string;
  development?: boolean;
};

export const NONCE_HEADER = "x-nonce";
export const CONTENT_SECURITY_POLICY_HEADER = "Content-Security-Policy";

export function createNonce(): string {
  return btoa(crypto.randomUUID());
}

export function buildContentSecurityPolicy({
  nonce,
  development = false,
}: ContentSecurityPolicyOptions): string {
  const scriptExtras = development ? " 'unsafe-eval'" : "";
  const connectExtras = development ? " ws: wss:" : "";
  return [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${scriptExtras}`,
    `style-src 'self' 'nonce-${nonce}'`,
    "style-src-attr 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self'",
    `connect-src 'self'${connectExtras}`,
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ].join("; ");
}
