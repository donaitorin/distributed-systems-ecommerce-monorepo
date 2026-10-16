import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, userEvent, within } from "storybook/test";
import type { ImportView } from "../../lib/types";
import type { ImportActions, ImportApi } from "./import-api";
import { ImportPanel } from "./import-panel";
import { STORY_IMPORT, STORY_PROBLEMS, withAppProviders, withQueries } from "../story-support";

const view = (overrides: Record<string, unknown> = {}, summary: Record<string, unknown> | null = {}): ImportView =>
  ({ ...STORY_IMPORT, ...overrides, summary: summary === null ? null : { ...STORY_IMPORT.summary, ...summary } });

const api = (current: ImportView): ImportApi => ({
  uploadImportFile: () => Promise.reject(new Error("unused")),
  fetchImport: () => Promise.resolve({ ok: true, import: current }),
  fetchProblems: () => Promise.resolve({ ok: true, page: STORY_PROBLEMS as never }),
});

const actions: ImportActions = {
  confirmImport: () => Promise.resolve({ ok: true, import: view({ status: "queued" }) }),
  revalidateImport: () => Promise.resolve({ ok: true, import: view({ status: "uploaded" }, null) }),
  createCategory: () => Promise.resolve({ ok: true, category: { id: "c", name: "Gardening", slug: "gardening" } }),
};

const meta = {
  title: "Backoffice/Imports/ImportPanel",
  component: ImportPanel,
  parameters: { layout: "padded" },
  decorators: [withAppProviders(), withQueries],
  args: { importId: STORY_IMPORT.id, existing: false, api: api(view()), actions, onRestart: () => undefined },
} satisfies Meta<typeof ImportPanel>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Validated: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await expect(await canvas.findByRole("button", { name: "Import 88 rows" })).toBeVisible();
    await expect(await canvas.findByRole("button", { name: "Create category Gardening" })).toBeVisible();
  },
};

export const Validating: Story = { args: { api: api(view({ status: "validating" }, null)) } };

export const Rejected: Story = {
  args: { api: api(view({ status: "rejected" }, { rejected: true, importable_rows: 0, unknown_categories: [] })) },
};

export const NothingToImport: Story = {
  args: { api: api(view({}, { importable_rows: 0, unknown_categories: [] })) },
};

export const ExistingFile: Story = { args: { existing: true } };

export const ConfirmDialog: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(await canvas.findByRole("button", { name: "Import 88 rows" }));
    await expect(await within(canvasElement.ownerDocument.body).findByRole("dialog", { name: "Import 88 products?" })).toBeVisible();
  },
};

export const Importing: Story = {
  args: {
    api: api(view({ status: "processing", progress: { processed_rows: 40, created_rows: 40, updated_rows: 0, restored_rows: 0, unchanged_rows: 0 } })),
  },
};

export const Completed: Story = {
  args: {
    api: api(view({ status: "completed", progress: { processed_rows: 88, created_rows: 80, updated_rows: 5, restored_rows: 2, unchanged_rows: 1 } })),
  },
};

export const Failed: Story = { args: { api: api(view({ status: "failed", failure_reason: "ImportFileChangedError" })) } };

export const NotFound: Story = {
  args: {
    api: {
      ...api(view()),
      fetchImport: () => Promise.resolve({ ok: false, status: 404, title: "Not found", fieldErrors: {} }),
    },
  },
};

export const Mobile: Story = {
  globals: { viewport: { value: "mobile", isRotated: false } },
};
