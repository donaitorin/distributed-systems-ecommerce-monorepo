function svgDataUri(size: number, background: string, label: string): string {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}"><rect width="${size}" height="${size}" fill="${background}"/><text x="50%" y="50%" font-family="sans-serif" font-size="${size / 8}" fill="#111827" text-anchor="middle" dominant-baseline="middle">${label}</text></svg>`;
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

export const SAMPLE_THUMBNAIL = svgDataUri(400, "#bfdbfe", "400 px");
export const SAMPLE_IMAGE = svgDataUri(1200, "#bfdbfe", "1200 px");
export const BROKEN_IMAGE = "/media/does-not-exist.webp";
