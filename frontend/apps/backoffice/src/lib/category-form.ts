import "./zod-config";
import { z } from "zod";

export const CATEGORY_NAME_MAX_LENGTH = 100;

export function normalizeCategoryName(raw: string): string {
  return raw.replace(/\s+/g, " ").trim();
}

export const categoryFormSchema = z.object({
  name: z.string().superRefine((value, context) => {
    const name = normalizeCategoryName(value);
    if (name === "") {
      context.addIssue({ code: "custom", message: "Name is required" });
    } else if (name.length > CATEGORY_NAME_MAX_LENGTH) {
      context.addIssue({ code: "custom", message: `Name must be at most ${CATEGORY_NAME_MAX_LENGTH} characters` });
    } else if (!/[a-z0-9]/i.test(name.normalize("NFKD"))) {
      context.addIssue({ code: "custom", message: "Name must contain letters or digits" });
    }
  }),
});

export type CategoryFormValues = z.infer<typeof categoryFormSchema>;
export const CATEGORY_NAME_FIELD_ID = "category-name";
