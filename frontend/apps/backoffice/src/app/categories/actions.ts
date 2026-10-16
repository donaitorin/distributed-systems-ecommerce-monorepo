"use server";

import type { CategoryFormValues } from "../../lib/category-form";
import type { Failure } from "@ecommerce/web-core";
import { createCategory, type CategoryCreated } from "../../server/category-actions";

export async function createCategoryAction(values: CategoryFormValues): Promise<CategoryCreated | Failure> {
  return createCategory(values);
}
