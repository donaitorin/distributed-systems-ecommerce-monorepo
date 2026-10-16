import { act, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactElement } from "react";
import type { ImportActions, ImportApi } from "../../src/components/imports/import-api";
import type { Failure } from "../../src/lib/failure";
import type { ImportProblemsPage, ImportView } from "../../src/lib/types";
import { importView } from "./api";
import { renderApp, type RenderOptions } from "./render";

export const IMPORT_ID = "9f0c1d2e-3a4b-4c5d-8e6f-7a8b9c0d1e2f";

export type Mocks = {
  api: { [Name in keyof ImportApi]: jest.Mock };
  actions: { [Name in keyof ImportActions]: jest.Mock };
};

export function mocks(): Mocks {
  return {
    api: {
      uploadImportFile: jest.fn(),
      fetchImport: jest.fn(),
      fetchProblems: jest.fn().mockResolvedValue(problemsPage([])),
    },
    actions: { confirmImport: jest.fn(), revalidateImport: jest.fn(), createCategory: jest.fn() },
  };
}

export function deferred(api: Mocks["api"]): ImportApi {
  return {
    uploadImportFile: (...args) => Promise.resolve().then(() => api.uploadImportFile(...args) as unknown) as ReturnType<ImportApi["uploadImportFile"]>,
    fetchImport: (...args) => Promise.resolve().then(() => api.fetchImport(...args) as unknown) as ReturnType<ImportApi["fetchImport"]>,
    fetchProblems: (...args) => Promise.resolve().then(() => api.fetchProblems(...args) as unknown) as ReturnType<ImportApi["fetchProblems"]>,
  };
}

export function loaded(view: ImportView) {
  return { ok: true as const, import: view };
}

export function problemsPage(items: ImportProblemsPage["items"], next_cursor: string | null = null) {
  return { ok: true as const, page: { items, next_cursor } };
}

export function failure(status: number | null, extra: Partial<Failure> = {}): Failure {
  return { ok: false, status, title: "Problem", fieldErrors: {}, ...extra };
}

export function renderWithQueries(ui: ReactElement, options: RenderOptions = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
  return { client, ...renderApp(<QueryClientProvider client={client}>{ui}</QueryClientProvider>, options) };
}

export async function advance(milliseconds: number): Promise<void> {
  await act(async () => {
    await jest.advanceTimersByTimeAsync(milliseconds);
    for (let turn = 0; turn < 5; turn += 1) {
      await jest.advanceTimersByTimeAsync(0);
    }
  });
}

export async function settled(): Promise<void> {
  await waitFor(() => {
    expect(screen.queryByText("Loading the import")).not.toBeInTheDocument();
  });
}

export { importView };
