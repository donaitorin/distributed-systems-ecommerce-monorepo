import { categoryFormSchema, normalizeCategoryName, type CategoryFormValues } from "../lib/category-form";
import type { Failure } from "../lib/failure";
import type { Category } from "../lib/types";
import { catalogApi } from "./catalog";
import { guarded } from "./guarded";

export type CategoryCreated = { ok: true; category: Category };

const UNPROCESSABLE = 422;

export async function createCategory(values: CategoryFormValues): Promise<CategoryCreated | Failure> {
  const parsed = categoryFormSchema.safeParse(values);
  if (!parsed.success) {
    return {
      ok: false,
      status: UNPROCESSABLE,
      title: "Validation failed",
      fieldErrors: { name: parsed.error.issues[0]?.message ?? "Name is not valid" },
    };
  }
  return guarded(async () => {
    const { data } = await catalogApi().post("/api/v1/categories", {
      body: { name: normalizeCategoryName(parsed.data.name) },
    });
    return { ok: true as const, category: data };
  });
}
