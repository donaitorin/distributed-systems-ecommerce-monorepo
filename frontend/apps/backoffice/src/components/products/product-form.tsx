"use client";

import { useEffect, useRef, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { Controller, useForm } from "react-hook-form";
import { Button, ButtonLink, Input, Select, Textarea, type SelectOption } from "@ecommerce/ui";
import { isSessionFailure } from "../../lib/failure";
import { saveFailureMessage } from "../../lib/messages";
import { LOGIN_PATH, PRODUCTS_PATH, ZONE_PATH } from "../../lib/paths";
import {
  changedFields,
  EMPTY_PRODUCT_VALUES,
  fieldErrorsFromApi,
  firstInvalidField,
  productFieldId,
  productFormSchema,
  productToFormValues,
  type ProductField,
  type ProductFormValues,
} from "../../lib/product-form";
import type { Category, Product, WithEtag } from "../../lib/types";
import type { UpdateResult } from "../../server/product-actions";
import { useNotify } from "../notifications";
import { ConflictDialog, type Difference } from "./conflict-dialog";
import { useNavigation } from "../navigation";

const NO_CATEGORY = "none";
const FIELD_LABELS: Record<ProductField, string> = {
  sku: "SKU",
  name: "Name",
  description: "Description",
  categoryId: "Category",
  price: "Price",
  stock: "Stock",
  weightKg: "Weight (kg)",
};
const DUPLICATE_SKU_FIELD_MESSAGE = "This SKU is already in use, possibly by a deleted product";
const CONFLICT = 412;
const DUPLICATE = 409;

export type ProductFormProps = {
  mode: "create" | "edit";
  categories: readonly Category[];
  product?: Product;
  submit: (values: ProductFormValues) => Promise<UpdateResult>;
  onSaved?: (product: Product, etag: string) => void;
};

type Conflict = { latest: WithEtag<Product> | undefined; differences: Difference[] };

function focusField(field: ProductField): void {
  document.getElementById(productFieldId(field))?.focus();
}

export function ProductForm({
  mode,
  categories,
  product,
  submit,
  onSaved,
}: ProductFormProps) {
  const router = useNavigation();
  const notify = useNotify();
  const alertRef = useRef<HTMLParagraphElement>(null);
  const [formError, setFormError] = useState<{ message: string; focus: boolean }>();
  const [conflict, setConflict] = useState<Conflict | null>(null);
  const {
    register,
    control,
    handleSubmit,
    reset,
    setError,
    getValues,
    formState: { errors, isSubmitting },
  } = useForm<ProductFormValues>({
    resolver: zodResolver(productFormSchema),
    defaultValues: product ? productToFormValues(product) : EMPTY_PRODUCT_VALUES,
    shouldFocusError: false,
  });

  useEffect(() => {
    if (formError?.focus) {
      alertRef.current?.focus();
    }
  }, [formError]);

  const categoryOptions: SelectOption[] = [
    { value: NO_CATEGORY, label: "No category" },
    ...categories.map(({ id, name }) => ({ value: id, label: name })),
  ];
  const categoryName = (id: string) => categories.find((category) => category.id === id)?.name ?? "";

  const describeConflict = (latest: WithEtag<Product> | undefined): Conflict => {
    if (!latest) {
      return { latest, differences: [] };
    }
    const mine = getValues();
    const theirs = productToFormValues(latest.value);
    const display = (field: ProductField, values: ProductFormValues) =>
      field === "categoryId" ? categoryName(values.categoryId) : values[field];
    return {
      latest,
      differences: changedFields(mine, theirs).map((field) => ({
        label: FIELD_LABELS[field],
        mine: display(field, mine),
        latest: display(field, theirs),
      })),
    };
  };

  const showFailure = (result: Extract<UpdateResult, { ok: false }>) => {
    const apiErrors = fieldErrorsFromApi(result.fieldErrors);
    if (mode === "create" && result.status === DUPLICATE) {
      apiErrors.sku = DUPLICATE_SKU_FIELD_MESSAGE;
    }
    for (const [field, message] of Object.entries(apiErrors)) {
      setError(field as ProductField, { type: "server", message });
    }
    const first = firstInvalidField(apiErrors);
    const message = saveFailureMessage(result);
    setFormError({ message, focus: !first });
    notify({ title: "The product was not saved", description: message, variant: "error" });
    if (first) {
      focusField(first);
    }
  };

  const saveValues = async (values: ProductFormValues) => {
    setFormError(undefined);
    const result = await submit(values);
    if (result.ok) {
      if (mode === "create") {
        notify({
          title: "Product created",
          description: `${result.product.sku} is in the catalog. You can add an image now.`,
          variant: "success",
        });
        router.push(`${PRODUCTS_PATH}/${encodeURIComponent(result.product.sku)}`);
        return;
      }
      reset(productToFormValues(result.product));
      onSaved?.(result.product, result.etag);
      notify({ title: "Product saved", description: `${result.product.sku} was updated.`, variant: "success" });
      return;
    }
    if (isSessionFailure(result)) {
      router.push(`${LOGIN_PATH}?reason=expired`);
      return;
    }
    if (result.status === CONFLICT) {
      setConflict(describeConflict(result.latest));
      return;
    }
    showFailure(result);
  };

  const focusFirstInvalid = (invalid: Partial<Record<ProductField, unknown>>) => {
    const first = firstInvalidField(invalid);
    if (first) {
      focusField(first);
    }
  };

  const adoptLatest = (keepInput: boolean) => {
    const latest = conflict?.latest;
    if (!latest) {
      return;
    }
    if (!keepInput) {
      reset(productToFormValues(latest.value));
    }
    onSaved?.(latest.value, latest.etag);
    setConflict(null);
    notify({
      title: keepInput ? "Your changes were kept" : "Latest version loaded",
      description: keepInput ? "Save again to overwrite the other change." : "The form shows the current values.",
      variant: "info",
    });
  };

  return (
    <>
      <form
        onSubmit={(event) => {
          void handleSubmit(saveValues, focusFirstInvalid)(event);
        }}
        noValidate
        className="flex max-w-xl flex-col gap-4"
        aria-label={mode === "create" ? "New product" : "Edit product"}
      >
        {formError ? (
          <p
            ref={alertRef}
            role="alert"
            tabIndex={-1}
            className="rounded-md border-2 border-danger-strong p-3 text-sm font-medium text-danger-strong"
          >
            {formError.message}
          </p>
        ) : null}
        <Input
          label="SKU"
          id={productFieldId("sku")}
          autoComplete="off"
          readOnly={mode === "edit"}
          hint={mode === "edit" ? "The SKU cannot be changed." : "Letters, digits, dots, underscores and hyphens. Stored in upper case."}
          error={errors.sku?.message}
          {...register("sku")}
        />
        <Input
          label="Name"
          id={productFieldId("name")}
          autoComplete="off"
          error={errors.name?.message}
          {...register("name")}
        />
        <Textarea
          label="Description"
          id={productFieldId("description")}
          hint="Optional."
          error={errors.description?.message}
          {...register("description")}
        />
        <Controller
          control={control}
          name="categoryId"
          render={({ field }) => (
            <Select
              label="Category"
              id={productFieldId("categoryId")}
              options={categoryOptions}
              value={field.value === "" ? NO_CATEGORY : field.value}
              onValueChange={(value) => {
                field.onChange(value === NO_CATEGORY ? "" : value);
              }}
              error={errors.categoryId?.message}
            />
          )}
        />
        <Input
          label="Price"
          id={productFieldId("price")}
          inputMode="decimal"
          autoComplete="off"
          hint="In dollars, for example 19.99."
          error={errors.price?.message}
          {...register("price")}
        />
        <Input
          label="Stock"
          id={productFieldId("stock")}
          inputMode="numeric"
          autoComplete="off"
          error={errors.stock?.message}
          {...register("stock")}
        />
        <Input
          label="Weight (kg)"
          id={productFieldId("weightKg")}
          inputMode="decimal"
          autoComplete="off"
          hint="Optional."
          error={errors.weightKg?.message}
          {...register("weightKg")}
        />
        <div className="flex flex-wrap gap-2">
          <Button type="submit" loading={isSubmitting}>
            {mode === "create" ? "Create product" : "Save changes"}
          </Button>
          <ButtonLink variant="secondary" href={`${ZONE_PATH}${PRODUCTS_PATH}`}>
            Back to products
          </ButtonLink>
        </div>
      </form>
      <ConflictDialog
        open={conflict !== null}
        differences={conflict?.differences ?? []}
        latestAvailable={conflict?.latest !== undefined}
        onLoadLatest={() => {
          adoptLatest(false);
        }}
        onKeepMine={() => {
          adoptLatest(true);
        }}
        onDismiss={() => {
          setConflict(null);
        }}
      />
    </>
  );
}
