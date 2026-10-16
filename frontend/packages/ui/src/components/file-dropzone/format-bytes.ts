const UNITS = ["B", "KB", "MB", "GB"] as const;
const STEP = 1024;

export function formatBytes(bytes: number): string {
  let value = bytes;
  let unit = 0;
  while (value >= STEP && unit < UNITS.length - 1) {
    value /= STEP;
    unit += 1;
  }
  const rounded = unit === 0 || Number.isInteger(value) ? String(Math.round(value)) : value.toFixed(1);
  return `${rounded} ${UNITS[unit]}`;
}
