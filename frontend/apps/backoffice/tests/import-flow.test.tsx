import { screen, waitFor, within } from "@testing-library/react";
import { axe } from "jest-axe";
import type { UrlUpdateEvent } from "nuqs/adapters/testing";
import { ImportFlow } from "../src/components/imports/import-flow";
import { CATEGORY, importView } from "./support/api";
import { advance, deferred, failure, IMPORT_ID, loaded, mocks, problemsPage, renderWithQueries, settled } from "./support/import-harness";
import { resetRouter, router } from "./support/navigation-mock";

jest.mock("next/navigation", () => jest.requireActual("./support/navigation-mock") as unknown);

const MAX_BYTES = 50 * 1024 * 1024;

function setup(search = `?import=${IMPORT_ID}`, onUrlUpdate?: jest.Mock<void, [UrlUpdateEvent]>, fakeTimers = false) {
  const harness = mocks();
  const view = renderWithQueries(<ImportFlow maxBytes={MAX_BYTES} api={deferred(harness.api)} actions={harness.actions} />, {
    searchParams: search,
    onUrlUpdate,
    fakeTimers,
  });
  return { ...view, ...harness };
}

function csv(name = "products.csv", size = 100): File {
  const file = new File(["x"], name, { type: "text/csv" });
  Object.defineProperty(file, "size", { value: size });
  return file;
}

const UNKNOWN = [{ value: "Gardening", rows: 2, suggestion: null }];
const PROBLEM = { severity: "error", row: 7, column: "category", value: "Gardening", code: "unknown_category", reason: "unknown category Gardening" };

beforeEach(() => {
  resetRouter();
});

afterEach(() => {
  jest.useRealTimers();
});

describe("upload", () => {
  it("offers the dropzone with the size limit and the file format", () => {
    setup("");

    expect(screen.getByRole("group", { name: "Products CSV file" })).toBeInTheDocument();
    expect(screen.getByText(/Up to 50 MB/)).toBeInTheDocument();
    expect(screen.getByLabelText("Choose a file")).toHaveAttribute("accept", ".csv,text/csv");
  });

  it("uploads the chosen file, puts the import in the URL and starts watching it", async () => {
    const onUrlUpdate = jest.fn<void, [UrlUpdateEvent]>();
    const { user, api } = setup("", onUrlUpdate);
    api.uploadImportFile.mockResolvedValue({ ok: true, existing: false, import: importView({ id: IMPORT_ID, status: "uploaded" }, null) });
    api.fetchImport.mockResolvedValue(loaded(importView({ status: "validating" }, null)));
    const file = csv();

    await user.upload(screen.getByLabelText("Choose a file"), file);

    expect(api.uploadImportFile).toHaveBeenCalledWith(file);
    await waitFor(() => {
      expect(onUrlUpdate.mock.lastCall?.[0].searchParams.get("import")).toBe(IMPORT_ID);
    });
    expect(onUrlUpdate.mock.lastCall?.[0].options.history).toBe("push");
    expect(await screen.findByText("products.csv")).toBeInTheDocument();
    expect(screen.queryByText(/uploaded before/)).not.toBeInTheDocument();
  });

  it("says when the same file was uploaded before", async () => {
    const { user, api } = setup("");
    api.uploadImportFile.mockResolvedValue({ ok: true, existing: true, import: importView({ id: IMPORT_ID }) });
    api.fetchImport.mockResolvedValue(loaded(importView()));

    await user.upload(screen.getByLabelText("Choose a file"), csv());

    expect(await screen.findByText(/This file was uploaded before/)).toBeInTheDocument();
  });

  it("refuses a file over the limit before sending a byte", async () => {
    const { user, api } = setup("");

    await user.upload(screen.getByLabelText("Choose a file"), csv("big.csv", MAX_BYTES + 1));

    expect(screen.getByRole("alert")).toHaveTextContent("larger than the 50 MB limit");
    expect(api.uploadImportFile).not.toHaveBeenCalled();
  });

  it.each([
    [failure(413), "larger than the 50 MB limit"],
    [failure(422, { detail: "the multipart field 'file' is required" }), "multipart field"],
    [failure(503, { retryAfterSeconds: 2 }), "Try again in 2 seconds"],
    [failure(null), "not available"],
  ])("shows an upload failure in plain language: %j", async (error, text) => {
    const { user, api } = setup("");
    api.uploadImportFile.mockResolvedValue(error);

    await user.upload(screen.getByLabelText("Choose a file"), csv());

    expect(await screen.findByRole("alert")).toHaveTextContent(text);
    expect(screen.getByLabelText("Choose a file")).toBeEnabled();
  });

  it("sends an expired session to the login page", async () => {
    const { user, api } = setup("");
    api.uploadImportFile.mockResolvedValue(failure(401));

    await user.upload(screen.getByLabelText("Choose a file"), csv());

    await waitFor(() => {
      expect(router.push).toHaveBeenCalledWith("/login?reason=expired");
    });
  });
});

describe("watching an import", () => {
  it("polls with a growing delay and stops on a final state", async () => {
    jest.useFakeTimers();
    const { api } = setup(undefined, undefined, true);
    const calledAt: number[] = [];
    const answers = [
      loaded(importView({ status: "uploaded" }, null)),
      loaded(importView({ status: "validating" }, null)),
      loaded(importView({ status: "validating" }, null)),
      loaded(importView({ status: "validating" }, null)),
      loaded(importView({ status: "validated" })),
    ];
    api.fetchImport.mockImplementation(() => {
      calledAt.push(Date.now());
      return Promise.resolve(answers[Math.min(calledAt.length, answers.length) - 1]);
    });
    const start = Date.now();

    await advance(30_000);

    expect(calledAt.map((time) => time - start)).toEqual([0, 1000, 2000, 3500, 5750]);
    expect(await screen.findByText(/Validation finished\. 88 rows can be imported, 4 rows with errors\./)).toBeInTheDocument();
    const calls = api.fetchImport.mock.calls.length;
    await advance(120_000);
    expect(api.fetchImport).toHaveBeenCalledTimes(calls);
  });

  it("announces status changes in a polite live region", async () => {
    const { api } = setup();
    api.fetchImport.mockResolvedValue(loaded(importView({ status: "validating" }, null)));

    const region = await screen.findByText("Validating the file.");

    expect(region).toHaveAttribute("aria-live", "polite");
    expect(region).toHaveAttribute("role", "status");
  });

  it("shows the report, with counts, once validation has finished, without accessibility violations", async () => {
    const { api, container } = setup();
    api.fetchImport.mockResolvedValue(loaded(importView({}, { unknown_categories: UNKNOWN })));
    api.fetchProblems.mockResolvedValue(problemsPage([PROBLEM]));

    await settled();
    const summary = await screen.findByRole("region", { name: "Summary" });

    expect(within(summary).getByText("To create").nextElementSibling).toHaveTextContent("88");
    expect(within(summary).getByText("Errors").nextElementSibling).toHaveTextContent("4");
    expect(within(summary).getByText("Warnings").nextElementSibling).toHaveTextContent("3");
    expect(await screen.findAllByText("unknown category Gardening")).not.toHaveLength(0);
    expect(screen.getByRole("link", { name: "Download problems.csv" })).toHaveAttribute(
      "href",
      `/admin/api/imports/${IMPORT_ID}/problems.csv`,
    );
    expect(await axe(container)).toHaveNoViolations();
  });

  it("filters the problems by severity and pages through them with the cursor", async () => {
    const { user, api } = setup();
    api.fetchImport.mockResolvedValue(loaded(importView()));
    api.fetchProblems
      .mockResolvedValueOnce(problemsPage([PROBLEM], "next-1"))
      .mockResolvedValue(problemsPage([{ ...PROBLEM, row: 9, reason: "second page problem" }]));

    await screen.findAllByText("unknown category Gardening");
    await user.click(screen.getByRole("button", { name: "Show more problems" }));
    expect(await screen.findAllByText("second page problem")).not.toHaveLength(0);
    expect(api.fetchProblems).toHaveBeenLastCalledWith(IMPORT_ID, { severity: null, cursor: "next-1", limit: 50 });
    expect(screen.queryByRole("button", { name: "Show more problems" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("combobox", { name: "Show" }));
    await user.click(await screen.findByRole("option", { name: "Warnings only" }));
    await waitFor(() => {
      expect(api.fetchProblems).toHaveBeenLastCalledWith(IMPORT_ID, { severity: "warning", cursor: null, limit: 50 });
    });
  });

  it("shows a message when the problems cannot be loaded", async () => {
    const { api } = setup();
    api.fetchImport.mockResolvedValue(loaded(importView()));
    api.fetchProblems.mockResolvedValue(failure(500));

    expect(await screen.findAllByText("The problems could not be loaded. Try again.")).not.toHaveLength(0);
  });

  it.each([
    [failure(404), "was not found", false],
    [failure(500), "could not be loaded", true],
  ])("explains a load failure: %j", async (error, text, canRetry) => {
    const { api } = setup();
    api.fetchImport.mockResolvedValue(error);

    expect(await screen.findByRole("alert")).toHaveTextContent(text);
    expect(screen.queryByRole("button", { name: "Try again" }) !== null).toBe(canRetry);
    expect(screen.getByRole("button", { name: "Upload another file" })).toBeInTheDocument();
  });

  it("tries again after a load failure", async () => {
    const { user, api } = setup();
    api.fetchImport.mockResolvedValueOnce(failure(500)).mockResolvedValue(loaded(importView()));

    await user.click(await screen.findByRole("button", { name: "Try again" }));

    expect(await screen.findByRole("region", { name: "Summary" })).toBeInTheDocument();
  });

  it("sends an expired session to the login page", async () => {
    const { api } = setup();
    api.fetchImport.mockResolvedValue(failure(401));

    await waitFor(() => {
      expect(router.push).toHaveBeenCalledWith("/login?reason=expired");
    });
  });

  it("goes back to the upload step and clears the import from the URL", async () => {
    const onUrlUpdate = jest.fn<void, [UrlUpdateEvent]>();
    const { user, api } = setup(undefined, onUrlUpdate);
    api.fetchImport.mockResolvedValue(loaded(importView()));

    await user.click(await screen.findByRole("button", { name: "Upload another file" }));

    expect(await screen.findByRole("group", { name: "Products CSV file" })).toBeInTheDocument();
    expect(onUrlUpdate.mock.lastCall?.[0].searchParams.has("import")).toBe(false);
  });

  it("ignores an import id that is not a UUID", () => {
    setup("?import=not-a-uuid");

    expect(screen.getByRole("group", { name: "Products CSV file" })).toBeInTheDocument();
  });
});

describe("unknown categories", () => {
  const withUnknown = () => importView({}, { unknown_categories: UNKNOWN, importable_rows: 3, error_rows: 2 });

  it("creates the missing category, then validates the same file again and follows the new result", async () => {
    jest.useFakeTimers();
    const { user, api, actions } = setup(undefined, undefined, true);
    api.fetchImport.mockResolvedValue(loaded(withUnknown()));
    actions.createCategory.mockResolvedValue({ ok: true, category: { ...CATEGORY, name: "Gardening", slug: "gardening" } });
    actions.revalidateImport.mockResolvedValue({ ok: true, import: importView({ status: "uploaded" }, null) });
    await advance(0);

    await user.click(await screen.findByRole("button", { name: "Create category Gardening" }));

    expect(actions.createCategory).toHaveBeenCalledWith({ name: "Gardening" });
    expect(await screen.findByText("Category created. Validate again to use it.")).toBeInTheDocument();
    expect(screen.getByText(/Categories were created\. Validate the file again/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Validate again" }).className).toContain("bg-accent-strong");
    expect(screen.getByRole("button", { name: "Import 3 rows" }).className).not.toContain("bg-accent-strong");

    api.fetchImport.mockResolvedValue(loaded(importView({}, { importable_rows: 5, error_rows: 0, error_count: 0 })));
    await user.click(screen.getByRole("button", { name: "Validate again" }));

    expect(actions.revalidateImport).toHaveBeenCalledWith(IMPORT_ID);
    expect(screen.getByText("File uploaded. Waiting for validation.")).toBeInTheDocument();
    await advance(1000);
    expect(await screen.findByRole("button", { name: "Import 5 rows" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Create category Gardening" })).not.toBeInTheDocument();
    expect(screen.queryByText(/Categories were created/)).not.toBeInTheDocument();
  });

  it("treats a category that already exists as available", async () => {
    const { user, api, actions } = setup();
    api.fetchImport.mockResolvedValue(loaded(withUnknown()));
    actions.createCategory.mockResolvedValue(failure(409));

    await user.click(await screen.findByRole("button", { name: "Create category Gardening" }));

    expect(await screen.findByText(/already exists\. Validate again to use it\./)).toBeInTheDocument();
    expect(screen.getByText(/Categories were created/)).toBeInTheDocument();
  });

  it("shows why a category could not be created and lets the user try again", async () => {
    const { user, api, actions } = setup();
    api.fetchImport.mockResolvedValue(loaded(withUnknown()));
    actions.createCategory.mockResolvedValue(failure(422, { fieldErrors: { name: "must contain letters or digits" } }));

    await user.click(await screen.findByRole("button", { name: "Create category Gardening" }));

    expect(await screen.findAllByText("must contain letters or digits")).not.toHaveLength(0);
    expect(screen.getByRole("button", { name: "Create category Gardening" })).toBeEnabled();
    expect(screen.queryByText(/Categories were created/)).not.toBeInTheDocument();
  });

  it("sends an expired session to the login page when creating a category", async () => {
    const { user, api, actions } = setup();
    api.fetchImport.mockResolvedValue(loaded(withUnknown()));
    actions.createCategory.mockResolvedValue(failure(401));

    await user.click(await screen.findByRole("button", { name: "Create category Gardening" }));

    await waitFor(() => {
      expect(router.push).toHaveBeenCalledWith("/login?reason=expired");
    });
  });

  it("explains a refused validation and refreshes the state", async () => {
    const { user, api, actions } = setup();
    api.fetchImport.mockResolvedValue(loaded(withUnknown()));
    actions.revalidateImport.mockResolvedValue(failure(409, { detail: "the import was already confirmed" }));
    await settled();

    await user.click(await screen.findByRole("button", { name: "Validate again" }));

    expect(await screen.findAllByText("the import was already confirmed")).not.toHaveLength(0);
    await waitFor(() => {
      expect(api.fetchImport).toHaveBeenCalledTimes(2);
    });
  });
});

describe("confirming", () => {
  it("asks first, then follows queued, processing and completed, and links back to the products", async () => {
    jest.useFakeTimers();
    const { user, api, actions } = setup(undefined, undefined, true);
    api.fetchImport.mockResolvedValue(loaded(importView()));
    actions.confirmImport.mockResolvedValue({ ok: true, import: importView({ status: "queued" }) });
    await advance(0);

    await user.click(await screen.findByRole("button", { name: "Import 88 rows" }));
    const dialog = await screen.findByRole("dialog", { name: "Import 88 products?" });
    expect(dialog).toHaveAccessibleDescription(expect.stringContaining("4 rows have errors and are skipped."));
    expect(actions.confirmImport).not.toHaveBeenCalled();

    api.fetchImport
      .mockResolvedValueOnce(loaded(importView({ status: "processing", progress: { processed_rows: 44, created_rows: 44, updated_rows: 0, restored_rows: 0, unchanged_rows: 0 } })))
      .mockResolvedValue(
        loaded(importView({ status: "completed", progress: { processed_rows: 88, created_rows: 80, updated_rows: 5, restored_rows: 2, unchanged_rows: 1 } })),
      );
    await user.click(within(dialog).getByRole("button", { name: "Import 88 rows" }));

    expect(actions.confirmImport).toHaveBeenCalledWith(IMPORT_ID);
    expect(await screen.findByText("Import confirmed and waiting to start.")).toBeInTheDocument();
    await advance(1000);
    expect(await screen.findByText("Importing products.")).toBeInTheDocument();
    const progress = screen.getByRole("progressbar", { name: "Import progress" });
    expect(progress).toHaveAttribute("value", "44");
    expect(progress).toHaveAttribute("max", "88");
    await advance(1000);
    expect(await screen.findByText("Import completed. 80 created, 5 updated, 2 restored, 1 unchanged.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View products" })).toHaveAttribute("href", "/admin/products");
    expect(screen.queryByRole("button", { name: /^Import \d+ rows$/ })).not.toBeInTheDocument();
    const calls = api.fetchImport.mock.calls.length;
    await advance(60_000);
    expect(api.fetchImport).toHaveBeenCalledTimes(calls);
  });

  it("shows an import that cannot be confirmed any more inside the dialog and refreshes it", async () => {
    const { user, api, actions } = setup();
    api.fetchImport.mockResolvedValue(loaded(importView()));
    actions.confirmImport.mockResolvedValue(failure(409, { detail: "the file has no valid rows to import" }));

    await user.click(await screen.findByRole("button", { name: "Import 88 rows" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Import 88 rows" }));

    expect(await within(screen.getByRole("dialog")).findByRole("alert")).toHaveTextContent("no valid rows");
    await waitFor(() => {
      expect(api.fetchImport).toHaveBeenCalledTimes(2);
    });
  });

  it("uses the singular for a single row", async () => {
    const { api } = setup();
    api.fetchImport.mockResolvedValue(loaded(importView({}, { importable_rows: 1, error_rows: 0 })));

    expect(await screen.findByRole("button", { name: "Import 1 row" })).toBeInTheDocument();
  });

  it("offers no import when no row is valid, but still lets the file be validated again", async () => {
    const { api } = setup();
    api.fetchImport.mockResolvedValue(loaded(importView({}, { importable_rows: 0, to_create: 0 })));

    expect(await screen.findByText(/No rows can be imported\. Fix the problems/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Import \d+ rows?$/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Validate again" })).toBeInTheDocument();
  });

  it("sends an expired session to the login page when confirming", async () => {
    const { user, api, actions } = setup();
    api.fetchImport.mockResolvedValue(loaded(importView()));
    actions.confirmImport.mockResolvedValue(failure(401));

    await user.click(await screen.findByRole("button", { name: "Import 88 rows" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Import 88 rows" }));

    await waitFor(() => {
      expect(router.push).toHaveBeenCalledWith("/login?reason=expired");
    });
  });
});

describe("other final states", () => {
  it("shows a rejected file with its problems and no import button", async () => {
    const { api, container } = setup();
    api.fetchImport.mockResolvedValue(loaded(importView({ status: "rejected" }, { rejected: true, importable_rows: 0 })));
    api.fetchProblems.mockResolvedValue(
      problemsPage([{ severity: "error", row: null, column: null, value: null, code: "missing_column", reason: "required column sku is missing" }]),
    );

    expect(await screen.findByText("The file was rejected. The problems are listed below.")).toBeInTheDocument();
    expect(await screen.findAllByText("required column sku is missing")).not.toHaveLength(0);
    expect(screen.queryByRole("button", { name: /^Import \d+/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Validate again" })).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("shows why an import failed and offers to upload again", async () => {
    const { user, api } = setup();
    api.fetchImport.mockResolvedValue(loaded(importView({ status: "failed", failure_reason: "worker error" })));

    expect(await screen.findAllByText(/worker error/)).not.toHaveLength(0);
    await user.click(screen.getByRole("button", { name: "Upload the file again" }));

    expect(await screen.findByRole("group", { name: "Products CSV file" })).toBeInTheDocument();
  });

  it("shows a generic message when a failed import has no reason", async () => {
    const { api } = setup();
    api.fetchImport.mockResolvedValue(loaded(importView({ status: "failed", failure_reason: null })));

    expect(await screen.findAllByText("The import failed.")).not.toHaveLength(0);
  });

  it("can start another import after a completed one", async () => {
    const { user, api } = setup();
    api.fetchImport.mockResolvedValue(loaded(importView({ status: "completed" })));

    await user.click(await screen.findByRole("button", { name: "Import another file" }));

    expect(await screen.findByRole("group", { name: "Products CSV file" })).toBeInTheDocument();
  });
});
