import {
  announcementFor,
  isSettled,
  nextPollDelay,
  progressFraction,
  reportable,
  withPollCount,
} from "../src/lib/import-status";
import { importView } from "./support/api";

describe("polling", () => {
  it.each(["validated", "rejected", "completed", "failed"])("stops on %s", (status) => {
    expect(isSettled(status)).toBe(true);
    expect(nextPollDelay({ status, polls: 0 })).toBe(false);
  });

  it.each(["uploaded", "validating", "queued", "processing"])("keeps polling on %s", (status) => {
    expect(isSettled(status)).toBe(false);
    expect(nextPollDelay({ status, polls: 0 })).toBe(1000);
  });

  it("backs off by half again each time and caps at eight seconds", () => {
    const delays = [0, 1, 2, 3, 4, 5, 6, 20].map((polls) => nextPollDelay({ status: "validating", polls }));

    expect(delays).toEqual([1000, 1500, 2250, 3375, 5063, 7594, 8000, 8000]);
  });

  it("does not poll without data", () => {
    expect(nextPollDelay(undefined)).toBe(false);
  });

  it("counts consecutive polls of the same status and starts over when it changes", () => {
    const first = withPollCount(importView({ status: "validating" }), undefined);
    const second = withPollCount(importView({ status: "validating" }), first);
    const third = withPollCount(importView({ status: "validated" }), second);

    expect([first.polls, second.polls, third.polls]).toEqual([0, 1, 0]);
  });
});

describe("reportable", () => {
  it("has a report once validation has finished", () => {
    expect(reportable("uploaded")).toBe(false);
    expect(reportable("validating")).toBe(false);
    expect(reportable("validated")).toBe(true);
    expect(reportable("completed")).toBe(true);
  });
});

describe("announcementFor", () => {
  it.each([
    ["uploaded", {}, "Waiting for validation"],
    ["validating", {}, "Validating the file."],
    ["rejected", {}, "The file was rejected"],
    ["queued", {}, "waiting to start"],
    ["processing", {}, "Importing products."],
    ["failed", { failure_reason: "worker error" }, "The import failed. worker error"],
    ["failed", { failure_reason: null }, "The import failed."],
    ["mystery", {}, ""],
  ])("announces %s", (status, extra, text) => {
    expect(announcementFor(importView({ status, ...extra }))).toContain(text);
  });

  it("announces how many rows can be imported, with singular and plural", () => {
    expect(announcementFor(importView({ status: "validated" }))).toBe(
      "Validation finished. 88 rows can be imported, 4 rows with errors.",
    );
    expect(announcementFor(importView({ status: "validated" }, { importable_rows: 1, error_rows: 1 }))).toBe(
      "Validation finished. 1 row can be imported, 1 row with errors.",
    );
    expect(announcementFor(importView({ status: "validated" }, { importable_rows: 0 }))).toBe(
      "Validation finished. No rows can be imported.",
    );
    expect(announcementFor(importView({ status: "validated" }, null))).toBe("Validation finished. No rows can be imported.");
  });

  it("announces the result of a finished import", () => {
    const done = importView({
      status: "completed",
      progress: { processed_rows: 88, created_rows: 80, updated_rows: 5, restored_rows: 2, unchanged_rows: 1 },
    });

    expect(announcementFor(done)).toBe("Import completed. 80 created, 5 updated, 2 restored, 1 unchanged.");
  });
});

describe("progressFraction", () => {
  it("is processed rows over importable rows, capped at one", () => {
    const progress = (processed_rows: number) => ({
      processed_rows,
      created_rows: 0,
      updated_rows: 0,
      restored_rows: 0,
      unchanged_rows: 0,
    });

    expect(progressFraction(importView({ progress: progress(44) }))).toBe(0.5);
    expect(progressFraction(importView({ progress: progress(500) }))).toBe(1);
  });

  it("is unknown without importable rows", () => {
    expect(progressFraction(importView({}, { importable_rows: 0 }))).toBeNull();
    expect(progressFraction(importView({}, null))).toBeNull();
  });
});
