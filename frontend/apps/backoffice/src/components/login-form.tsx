"use client";

import { useActionState, useEffect, useRef } from "react";
import { Button, Input } from "@ecommerce/ui";
import type { LoginState } from "../lib/login-form";

export type LoginAction = (previous: LoginState, formData: FormData) => Promise<LoginState>;

export type LoginFormProps = {
  action: LoginAction;
  next: string;
};

export function LoginForm({ action, next }: LoginFormProps) {
  const [state, formAction, pending] = useActionState(action, {});
  const formRef = useRef<HTMLFormElement>(null);
  const errorRef = useRef<HTMLParagraphElement>(null);

  useEffect(() => {
    if (state.fieldErrors?.email) {
      formRef.current?.querySelector<HTMLInputElement>("input[name='email']")?.focus();
    } else if (state.fieldErrors?.password) {
      formRef.current?.querySelector<HTMLInputElement>("input[name='password']")?.focus();
    } else if (state.error) {
      errorRef.current?.focus();
    }
  }, [state]);

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
