/**
 * @jest-environment node
 */
import { entityTag } from "../src/lib/entity-tag";
import {
  apiFieldName,
  changedFields,
  EMPTY_PRODUCT_VALUES,
  fieldErrorsFromApi,
  firstInvalidField,
  productFieldId,
  productFormSchema,
  productToFormValues,
  toCreateBody,
  toWriteBody,
  type ProductFormValues,
} from "../src/lib/product-form";
import { product } from "./support/api";

const VALID: ProductFormValues = {
  sku: "rs-001",
  name: "Running shoes",
  description: "",
  categoryId: "",
  price: "59.00",
  stock: "24",
  weightKg: "",
};

function errorOf(values: Partial<ProductFormValues>, field: keyof ProductFormValues): string | undefined {
  const result = productFormSchema.safeParse({ ...VALID, ...values });
  return result.success ? undefined : result.error.issues.find((issue) => issue.path[0] === field)?.message;
}

describe("product form schema", () => {
  it("accepts a valid product and a fully filled one", () => {
    expect(productFormSchema.safeParse(VALID).success).toBe(true);
    expect(
      productFormSchema.safeParse({
        ...VALID,
        categoryId: "7d9f8a5e-0f1c-4b0e-9a5d-2f6a4c1b3e10",
        weightKg: "1.250",
        description: "Light",
        price: "9999999999.99",
        stock: "2147483647",
      }).success,
    ).toBe(true);
  });

  it.each([
    ["sku", "", "SKU is required"],
    ["sku", "-bad", "Use 1 to 64 letters"],
    ["sku", "has space", "Use 1 to 64 letters"],
    ["sku", "A".repeat(65), "Use 1 to 64 letters"],
    ["name", "   ", "Name is required"],
    ["name", "n".repeat(256), "at most 255"],
    ["description", "d".repeat(5001), "at most 5000"],
    ["categoryId", "not-a-uuid", "Choose a category"],
    ["price", "", "Price is required"],
    ["price", "-1", "Enter a price"],
    ["price", "1.999", "Enter a price"],
    ["price", "12345678901", "Enter a price"],
    ["price", "1e3", "Enter a price"],
    ["stock", "", "Stock is required"],
    ["stock", "-1", "whole number"],
    ["stock", "1.5", "whole number"],
    ["stock", "2147483648", "at most 2147483647"],
    ["weightKg", "1.2345", "Enter a weight"],
    ["weightKg", "100000", "Enter a weight"],
    ["weightKg", "abc", "Enter a weight"],
  ] as const)("rejects %s = %j", (field, value, message) => {
    expect(errorOf({ [field]: value }, field)).toContain(message);
  });

  it("accepts the lowest and highest valid SKUs after upper casing", () => {
    expect(productFormSchema.safeParse({ ...VALID, sku: "a" }).success).toBe(true);
    expect(productFormSchema.safeParse({ ...VALID, sku: `a${"b".repeat(63)}` }).success).toBe(true);
    expect(productFormSchema.safeParse({ ...VALID, sku: "a.b_c-d" }).success).toBe(true);
  });
});


describe("product form mapping", () => {
  it("builds the write body keeping money and weight as decimal strings", () => {
    expect(
      toWriteBody({ ...VALID, name: " Shoes ", description: " Fast ", categoryId: "c", price: " 59.90 ", weightKg: " 0.800 " }),
    ).toEqual({
      name: "Shoes",
      description: "Fast",
      category_id: "c",
      price: "59.90",
      stock: 24,
      weight_kg: "0.800",
    });
    expect(toWriteBody(VALID)).toMatchObject({ description: null, category_id: null, weight_kg: null });
  });

  it("upper cases the SKU only when creating", () => {
    expect(toCreateBody({ ...VALID, sku: " rs-001 " })).toMatchObject({ sku: "RS-001", stock: 24 });
    expect(toWriteBody(VALID)).not.toHaveProperty("sku");
  });

  it("reads a product into form values", () => {
    expect(productToFormValues(product())).toEqual({
      sku: "RS-001",
      name: "Running shoes",
      description: "Light and fast",
      categoryId: "7d9f8a5e-0f1c-4b0e-9a5d-2f6a4c1b3e10",
      price: "59.00",
      stock: "24",
      weightKg: "0.800",
    });
    expect(productToFormValues(product({ description: null, category: null, weight_kg: null }))).toMatchObject({
      description: "",
      categoryId: "",
      weightKg: "",
    });
  });

  it("maps API field names to form fields and back", () => {
    expect(fieldErrorsFromApi({ category_id: "bad", weight_kg: "bad", name: "bad", unknown: "x" })).toEqual({
      categoryId: "bad",
      weightKg: "bad",
      name: "bad",
    });
    expect(apiFieldName("categoryId")).toBe("category_id");
    expect(apiFieldName("price")).toBe("price");
    expect(productFieldId("weightKg")).toBe("product-weightKg");
  });

  it("finds the first invalid field in form order", () => {
    expect(firstInvalidField({ stock: 1, name: 1 })).toBe("name");
    expect(firstInvalidField({})).toBeUndefined();
  });

  it("compares decimal values numerically and ignores the SKU", () => {
    const base = { ...EMPTY_PRODUCT_VALUES, price: "59.00", weightKg: "0.800", stock: "5" };

    expect(changedFields(base, { ...base, price: "59", weightKg: "0.8", sku: "OTHER" })).toEqual([]);
    expect(changedFields(base, { ...base, price: "59.50", stock: "6", name: "New" })).toEqual(["name", "price", "stock"]);
    expect(changedFields({ ...base, stock: " 5 " }, base)).toEqual([]);
  });
});


describe("entity tags", () => {
  it("formats an entity tag from a version", () => {
    expect(entityTag(3)).toBe('"3"');
  });
});
