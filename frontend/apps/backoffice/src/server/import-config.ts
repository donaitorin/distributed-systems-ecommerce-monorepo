export const DEFAULT_IMPORT_MAX_BYTES = 52_428_800;

export function importMaxBytes(environment: Record<string, string | undefined> = process.env): number {
  const raw = environment.IMPORT_MAX_BYTES?.trim();
  if (!raw) {
    return DEFAULT_IMPORT_MAX_BYTES;
  }
  const value = Number(raw);
  if (!Number.isSafeInteger(value) || value <= 0) {
    throw new Error("IMPORT_MAX_BYTES must be a positive integer");
  }
  return value;
}
