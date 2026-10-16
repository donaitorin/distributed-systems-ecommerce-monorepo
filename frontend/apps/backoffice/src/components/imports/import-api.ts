import { fetchImport, fetchProblems, uploadImportFile } from "../../lib/import-client";
import type { CategoryFormValues } from "../../lib/category-form";
import type { Failure } from "@ecommerce/web-core";
import type { ImportView } from "../../lib/types";
import type { CategoryCreated } from "../../server/category-actions";

export type ImportApi = {
  uploadImportFile: typeof uploadImportFile;
  fetchImport: typeof fetchImport;
  fetchProblems: typeof fetchProblems;
};

export const DEFAULT_IMPORT_API: ImportApi = { uploadImportFile, fetchImport, fetchProblems };

export type ImportActions = {
  confirmImport: (importId: string) => Promise<({ ok: true; import: ImportView }) | Failure>;
  revalidateImport: (importId: string) => Promise<({ ok: true; import: ImportView }) | Failure>;
  createCategory: (values: CategoryFormValues) => Promise<CategoryCreated | Failure>;
};
