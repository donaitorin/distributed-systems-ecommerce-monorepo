"use client";

import { useState } from "react";
import { Button, type ReportUnknownCategory } from "@ecommerce/ui";
import type { CategoryFormValues } from "../../lib/category-form";
import { isSessionFailure, type Failure } from "../../lib/failure";
import { categoryFailureMessage } from "../../lib/messages";
import { LOGIN_PATH } from "../../lib/paths";
import type { CategoryCreated } from "../../server/category-actions";
import { useNavigation } from "../navigation";
import { useNotify } from "../notifications";

export type UnknownCategoryActionProps = {
  category: ReportUnknownCategory;
  createCategory: (values: CategoryFormValues) => Promise<CategoryCreated | Failure>;
  onAvailable: (value: string) => void;
};

type State = { kind: "idle" } | { kind: "creating" } | { kind: "available"; note: string } | { kind: "failed"; message: string };

const DUPLICATE = 409;

export function UnknownCategoryAction({ category, createCategory, onAvailable }: UnknownCategoryActionProps) {
  const navigation = useNavigation();
  const notify = useNotify();
  const [state, setState] = useState<State>({ kind: "idle" });

  const create = async () => {
    setState({ kind: "creating" });
    const result = await createCategory({ name: category.value });
    if (result.ok) {
      setState({ kind: "available", note: "Category created. Validate again to use it." });
      notify({ title: "Category created", description: `${result.category.name} is available. Validate the file again.`, variant: "success" });
      onAvailable(category.value);
      return;
    }
    if (isSessionFailure(result)) {
      navigation.push(`${LOGIN_PATH}?reason=expired`);
      return;
    }
    if (result.status === DUPLICATE) {
      setState({ kind: "available", note: "A category with this name already exists. Validate again to use it." });
      onAvailable(category.value);
      return;
    }
    const message = categoryFailureMessage(result);
    setState({ kind: "failed", message });
    notify({ title: "The category was not created", description: message, variant: "error" });
  };

  if (state.kind === "available") {
    return (
      <p role="status" className="text-sm font-medium text-success-strong">
        {state.note}
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-1 sm:items-end">
      <Button
        variant="secondary"
        loading={state.kind === "creating"}
        aria-label={`Create category ${category.value}`}
        onClick={() => {
          void create();
        }}
      >
        Create category
      </Button>
      {state.kind === "failed" ? (
        <p role="alert" className="text-sm font-medium text-danger-strong">
          {state.message}
        </p>
      ) : null}
    </div>
  );
}
