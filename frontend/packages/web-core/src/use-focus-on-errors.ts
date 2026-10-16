"use client";

import { useEffect, type RefObject } from "react";

export type FocusOnErrorsOptions = {
  formRef: RefObject<HTMLFormElement | null>;
  errorRef: RefObject<HTMLElement | null>;
  state: { fieldErrors?: Partial<Record<string, string>>; error?: string };
  order: readonly string[];
};

export function useFocusOnErrors({ formRef, errorRef, state, order }: FocusOnErrorsOptions): void {
  useEffect(() => {
    const field = order.find((name) => state.fieldErrors?.[name]);
    if (field !== undefined) {
      formRef.current?.querySelector<HTMLInputElement>(`[name='${field}']`)?.focus();
    } else if (state.error) {
      errorRef.current?.focus();
    }
  }, [state, order, formRef, errorRef]);
}
