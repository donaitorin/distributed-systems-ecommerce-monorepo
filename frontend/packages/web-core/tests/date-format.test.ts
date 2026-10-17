import { formatDate, formatDateTime } from "../src/date-format";

describe("date formats", () => {
  it("prints the time zone, so the server and the browser agree", () => {
    expect(formatDateTime("2026-10-17T10:05:09Z")).toBe("17 Oct 2026, 10:05:09 UTC");
    expect(formatDateTime("2026-10-17T23:59:59-05:00")).toBe("18 Oct 2026, 04:59:59 UTC");
  });

  it("prints a date in UTC", () => {
    expect(formatDate("2026-10-17T23:30:00Z")).toBe("17 Oct 2026");
  });
});
