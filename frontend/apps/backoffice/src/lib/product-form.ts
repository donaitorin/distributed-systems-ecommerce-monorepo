import "./zod-config";
import { z } from "zod";
import type { Product } from "./types";

export const NAME_MAX_LENGTH = 255;
export const DESCRIPTION_MAX_LENGTH = 5000;
export const STOCK_MAX = 2_147_483_647;
const SKU_PATTERN = /^[A-Z0-9][A-Z0-9._-]{0,63}$/;
const PRICE_PATTERN = /^\d{1,10}(\.\d{1,2})?$/;
const WEIGHT_PATTERN = /^\d{1,5}(\.\d{1,3})?$/;
const WHOLE_NUMBER = /^\d+$/;

export const productFormSchema = z.object({
  sku: z
    .string()
    .trim()
    .min(1, "SKU is required")
    .refine(
      (value) => SKU_PATTERN.test(value.toUpperCase()),
      "Use 1 to 64 letters, digits, dots, underscores or hyphens, starting with a letter or digit",
    ),
  name: z
    .string()
    .trim()
    .min(1, "Name is required")
    .max(NAME_MAX_LENGTH, `Name must be at most ${NAME_MAX_LENGTH} characters`),
  description: z
    .string()
    .trim()
    .max(DESCRIPTION_MAX_LENGTH, `Description must be at most ${DESCRIPTION_MAX_LENGTH} characters`),
  categoryId: z.union([z.literal(""), z.uuid("Choose a category from the list")]),
  price: z
    .string()
    .trim()
    .min(1, "Price is required")
    .regex(PRICE_PATTERN, "Enter a price like 19.99: digits with at most 2 decimals, up to 9999999999.99"),
  stock: z
    .string()
    .trim()
    .min(1, "Stock is required")
    .regex(WHOLE_NUMBER, "Stock must be a whole number, zero or more")
    .refine((value) => Number(value) <= STOCK_MAX, `Stock must be at most ${STOCK_MAX}`),
  weightKg: z
    .string()
    .trim()
    .refine(
      (value) => value === "" || WEIGHT_PATTERN.test(value),
      "Enter a weight like 1.250: digits with at most 3 decimals, up to 99999.999",
    ),
});

export type ProductFormValues = z.infer<typeof productFormSchema>;
export type ProductField = keyof ProductFormValues;

export const FIELD_ORDER: readonly ProductField[] = [
  "sku",
  "name",
  "description",
  "categoryId",
  "price",
  "stock",
  "weightKg",
];

export const EMPTY_PRODUCT_VALUES: ProductFormValues = {
  sku: "",
  name: "",
  description: "",
  categoryId: "",
  price: "",
  stock: "",
  weightKg: "",
};

const API_FIELDS: Record<string, ProductField> = {
  sku: "sku",
  name: "name",
  description: "description",
  category_id: "categoryId",
  price: "price",
  stock: "stock",
  weight_kg: "weightKg",
};

const FORM_TO_API = Object.fromEntries(Object.entries(API_FIELDS).map(([api, form]) => [form, api])) as Record<
  ProductField,
  string
>;

export function apiFieldName(field: ProductField): string {
  return FORM_TO_API[field];
}

export function productFieldId(field: ProductField): string {
  return `product-${field}`;
}

export function fieldErrorsFromApi(fieldErrors: Record<string, string>): Partial<Record<ProductField, string>> {
  const result: Partial<Record<ProductField, string>> = {};
  for (const [apiField, message] of Object.entries(fieldErrors)) {
    const field = API_FIELDS[apiField];
    if (field !== undefined) {
      result[field] = message;
    }
  }
  return result;
}

export function firstInvalidField(errors: Partial<Record<ProductField, unknown>>): ProductField | undefined {
  return FIELD_ORDER.find((field) => errors[field] !== undefined);
}

export function productToFormValues(product: Product): ProductFormValues {
  return {
    sku: product.sku,
    name: product.name,
    description: product.description ?? "",
    categoryId: product.category?.id ?? "",
    price: product.price,
    stock: String(product.stock),
    weightKg: product.weight_kg ?? "",
  };
}

export function toWriteBody(values: ProductFormValues) {
  const description = values.description.trim();
  const weight = values.weightKg.trim();
  return {
    name: values.name.trim(),
    description: description === "" ? null : description,
    category_id: values.categoryId === "" ? null : values.categoryId,
    price: values.price.trim(),
    stock: Number(values.stock.trim()),
    weight_kg: weight === "" ? null : weight,
  };
}

export function toCreateBody(values: ProductFormValues) {
  return { sku: values.sku.trim().toUpperCase(), ...toWriteBody(values) };
}

const COMPARED_FIELDS: readonly ProductField[] = FIELD_ORDER.filter((field) => field !== "sku");
const DECIMAL_FIELDS: readonly ProductField[] = ["price", "weightKg"];

function canonical(field: ProductField, raw: string): string {
  const value = raw.trim();
  if (!DECIMAL_FIELDS.includes(field) || !value.includes(".")) {
    return value;
  }
  return value.replace(/0+$/, "").replace(/\.$/, "");
}

export function changedFields(left: ProductFormValues, right: ProductFormValues): ProductField[] {
  return COMPARED_FIELDS.filter((field) => canonical(field, left[field]) !== canonical(field, right[field]));
}
