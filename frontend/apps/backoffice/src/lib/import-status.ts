import type { ImportView } from "./types";

export type PolledImport = ImportView & { polls: number };

const SETTLED = new Set(["validated", "rejected", "completed", "failed"]);
const BASE_DELAY_MS = 1000;
const GROWTH = 1.5;
const MAX_DELAY_MS = 8000;

export function isSettled(status: string): boolean {
  return SETTLED.has(status);
}

export function nextPollDelay(data: Pick<PolledImport, "status" | "polls"> | undefined): number | false {
  if (!data || isSettled(data.status)) {
    return false;
  }
  return Math.min(Math.round(BASE_DELAY_MS * GROWTH ** data.polls), MAX_DELAY_MS);
}

export function withPollCount(next: ImportView, previous: PolledImport | undefined): PolledImport {
  return { ...next, polls: previous && previous.status === next.status ? previous.polls + 1 : 0 };
}

export function reportable(status: string): boolean {
  return status !== "uploaded" && status !== "validating";
}

function plural(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

export function announcementFor(data: ImportView): string {
  const summary = data.summary;
  switch (data.status) {
    case "uploaded":
      return "File uploaded. Waiting for validation.";
    case "validating":
      return "Validating the file.";
    case "validated":
      return summary && summary.importable_rows > 0
        ? `Validation finished. ${plural(summary.importable_rows, "row")} can be imported, ${plural(summary.error_rows, "row")} with errors.`
        : "Validation finished. No rows can be imported.";
    case "rejected":
      return "The file was rejected. The problems are listed below.";
    case "queued":
      return "Import confirmed and waiting to start.";
    case "processing":
      return "Importing products.";
    case "completed":
      return `Import completed. ${data.progress.created_rows} created, ${data.progress.updated_rows} updated, ${data.progress.restored_rows} restored, ${data.progress.unchanged_rows} unchanged.`;
    case "failed":
      return `The import failed.${data.failure_reason ? ` ${data.failure_reason}` : ""}`;
    default:
      return "";
  }
}

export function progressFraction(data: ImportView): number | null {
  const total = data.summary?.importable_rows ?? 0;
  if (total <= 0) {
    return null;
  }
  return Math.min(1, data.progress.processed_rows / total);
}
