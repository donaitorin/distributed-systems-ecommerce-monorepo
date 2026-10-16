"use client";

import { useActionState, useRef } from "react";
import { Button, Input } from "@ecommerce/ui";
import { useFocusOnErrors } from "@ecommerce/web-core/client";
import type { LoginState } from "../lib/login-form";

const FIELD_ORDER = ["email", "password"] as const;

export type LoginAction = (previous: LoginState, formData: FormData) => Promise<LoginState>;

export type LoginFormProps = {
  action: LoginAction;
  next: string;
};

export function LoginForm({ action, next }: LoginFormProps) {
  const [state, formAction, pending] = useActionState(action, {});
  const formRef = useRef<HTMLFormElement>(null);
  const errorRef = useRef<HTMLParagraphElement>(null);

  useFocusOnErrors({ formRef, errorRef, state, order: FIELD_ORDER });

  return (
    <form ref={formRef} action={formAction} noValidate className="flex max-w-md flex-col gap-4">
      <input type="hidden" name="next" value={next} />
      {state.error ? (
        <p
          ref={errorRef}
          role="alert"
          tabIndex={-1}
          className="rounded-md border-2 border-danger-strong p-3 text-sm font-medium text-danger-strong"
        >
          {state.error}
        </p>
      ) : null}
      <Input
        label="Email"
        name="email"
        type="email"
        autoComplete="username"
        defaultValue={state.email}
        error={state.fieldErrors?.email}
        required
      />
      <Input
        label="Password"
        name="password"
        type="password"
        autoComplete="current-password"
        error={state.fieldErrors?.password}
        required
      />
      <Button type="submit" loading={pending}>
        Sign in
      </Button>
    </form>
  );
}
