const MEDIA_PREFIX = "/media/";

export function sameOriginMedia(url: string | null | undefined): string | null {
  if (!url) {
    return null;
  }
  try {
    const { pathname, search } = new URL(url, "http://media.invalid");
    return pathname.startsWith(MEDIA_PREFIX) ? `${pathname}${search}` : url;
  } catch {
    return url;
  }
}
