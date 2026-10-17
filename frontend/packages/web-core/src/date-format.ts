const DATE_TIME = new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeStyle: "medium", timeZone: "UTC" });
const DATE = new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeZone: "UTC" });

export function formatDateTime(iso: string): string {
  return `${DATE_TIME.format(new Date(iso))} UTC`;
}

export function formatDate(iso: string): string {
  return DATE.format(new Date(iso));
}
