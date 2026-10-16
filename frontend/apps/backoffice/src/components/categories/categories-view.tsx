"use client";

import { useEffect, useRef, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { Button, Input, Table, type TableColumn } from "@ecommerce/ui";
import { CATEGORY_NAME_FIELD_ID, categoryFormSchema, type CategoryFormValues } from "../../lib/category-form";
import { isSessionFailure, type Failure } from "../../lib/failure";
import { categoryFailureMessage } from "../../lib/messages";
import { LOGIN_PATH } from "../../lib/paths";
import type { Category } from "../../lib/types";
import type { CategoryCreated } from "../../server/category-actions";
import { useNavigation } from "../navigation";
import { useNotify } from "../notifications";

export type CategoriesViewProps = {
  categories: readonly Category[];
  failure: Failure | null;
  createCategory: (values: CategoryFormValues) => Promise<CategoryCreated | Failure>;
};

const COLUMNS: readonly TableColumn<Category>[] = [
  { key: "name", header: "Name", cell: (category) => category.name },
  { key: "slug", header: "Slug", cell: (category) => category.slug },
];

const DUPLICATE = 409;

export function CategoriesView({ categories, failure, createCategory }: CategoriesViewProps) {
  const navigation = useNavigation();
  const notify = useNotify();
  const alertRef = useRef<HTMLParagraphElement>(null);
  const [formError, setFormError] = useState<{ message: string; focus: boolean }>();
  const [createdCount, setCreatedCount] = useState(0);
  const {
    register,
    handleSubmit,
    reset,
    setError,
    setFocus,
    formState: { errors, isSubmitting, submitCount },
  } = useForm<CategoryFormValues>({
    resolver: zodResolver(categoryFormSchema),
    defaultValues: { name: "" },
    shouldFocusError: false,
  });

  useEffect(() => {
    if (createdCount > 0 || errors.name) {
      setFocus("name");
    }
  }, [createdCount, submitCount, errors.name, setFocus]);

  useEffect(() => {
    if (formError?.focus) {
      alertRef.current?.focus();
    }
  }, [formError]);

  const sorted = [...categories].sort((left, right) => left.name.localeCompare(right.name, "en"));

  const submit = async (values: CategoryFormValues) => {
    setFormError(undefined);
    const result = await createCategory(values);
    if (result.ok) {
      reset({ name: "" });
      setCreatedCount((count) => count + 1);
      notify({ title: "Category created", description: `${result.category.name} is available for products.`, variant: "success" });
      navigation.refresh();
      return;
    }
    if (isSessionFailure(result)) {
      navigation.push(`${LOGIN_PATH}?reason=expired`);
      return;
    }
    const message = categoryFailureMessage(result);
    const onField = result.status === DUPLICATE || result.status === 422;
    if (onField) {
      setError("name", { type: "server", message });
    }
    setFormError({ message, focus: !onField });
    notify({ title: "The category was not created", description: message, variant: "error" });
  };

  return (
    <div className="flex flex-col gap-8">
      <form
        aria-label="New category"
        noValidate
        className="flex max-w-xl flex-col gap-4"
        onSubmit={(event) => {
          void handleSubmit(submit)(event);
        }}
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
          label="New category name"
          id={CATEGORY_NAME_FIELD_ID}
          autoComplete="off"
          hint="Up to 100 characters. The URL slug is generated from the name."
          error={errors.name?.message}
          {...register("name")}
        />
        <div>
          <Button type="submit" loading={isSubmitting}>
            Create category
          </Button>
        </div>
      </form>
      <Table
        caption="Category list"
        columns={COLUMNS}
        rows={sorted}
        getRowKey={(category) => category.id}
        error={failure ? "The categories could not be loaded. Reload the page to try again." : undefined}
        emptyMessage="There are no categories yet."
        renderCard={(category) => (
          <div className="flex flex-col gap-1">
            <p className="font-medium">{category.name}</p>
            <p className="text-sm text-secondary">{category.slug}</p>
          </div>
        )}
      />
    </div>
  );
}
