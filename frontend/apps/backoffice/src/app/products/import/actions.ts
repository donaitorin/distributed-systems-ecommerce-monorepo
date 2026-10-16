"use server";

import type { Failure } from "@ecommerce/web-core";
import { confirmImport, revalidateImport, type ImportChanged } from "../../../server/import-actions";

export async function confirmImportAction(importId: string): Promise<ImportChanged | Failure> {
  return confirmImport(importId);
}

export async function revalidateImportAction(importId: string): Promise<ImportChanged | Failure> {
  return revalidateImport(importId);
}
