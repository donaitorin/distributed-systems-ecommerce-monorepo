const FORWARDED_FOR = "x-forwarded-for";
const REAL_IP = "x-real-ip";
const IP_CHARACTERS = /^[0-9a-fA-F:.]+$/;

function isIpLike(value: string): boolean {
  return value.length >= 2 && value.length <= 45 && IP_CHARACTERS.test(value);
}

export function clientIpFrom(headers: Headers): string | undefined {
  const forwarded = headers
    .get(FORWARDED_FOR)
    ?.split(",")
    .map((entry) => entry.trim())
    .filter(Boolean);
  const candidate = forwarded?.at(-1) ?? headers.get(REAL_IP)?.trim();
  return candidate && isIpLike(candidate) ? candidate : undefined;
}

export function forwardingHeaders(clientIp: string | undefined): Record<string, string> {
  return clientIp ? { [FORWARDED_FOR]: clientIp } : {};
}
