import type { Failure } from "@ecommerce/web-core";
import type { ImportView } from "../lib/types";
import { gatewayApi } from "./gateway";
import { guarded } from "./guarded";

export type ImportChanged = { ok: true; import: ImportView };

export async function confirmImport(importId: string): Promise<ImportChanged | Failure> {
  return guarded(async () => {
    const { data } = await gatewayApi().post("/api/v1/imports/{import_id}/confirm", {
      params: { import_id: importId },
    });
    return { ok: true as const, import: data };
  });
}

export async function revalidateImport(importId: string): Promise<ImportChanged | Failure> {
  return guarded(async () => {
    const { data } = await gatewayApi().post("/api/v1/imports/{import_id}/revalidate", {
      params: { import_id: importId },
    });
    return { ok: true as const, import: data };
  });
}
