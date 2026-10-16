"use client";

import { useActionState, useRef } from "react";
import { Button, Input } from "@ecommerce/ui";
import { useFocusOnErrors } from "@ecommerce/web-core/client";
import type { RegisterState } from "../../lib/auth-form";
import { authPageHref, LOGIN_PATH } from "../../lib/paths";

const FIELD_ORDER = ["email", "password"] as const;
const PASSWORD_HINT = "At least 10 characters. A few unrelated words make a strong password.";

export type RegisterAction = (previous: RegisterState, formData: FormData) => Promise<RegisterState>;

export type RegisterFormProps = {
  action: RegisterAction;
  next: string;
};

export function RegisterForm({ action, next }: RegisterFormProps) {
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
      {state.emailTaken ? (
        <p className="text-sm">
          <a href={authPageHref(LOGIN_PATH, next)} className="text-accent-strong underline">
            Sign in with this email instead
          </a>
        </p>
      ) : null}
      <Input
        label="Password"
        name="password"
        type="password"
        autoComplete="new-password"
        hint={PASSWORD_HINT}
        error={state.fieldErrors?.password}
        required
      />
      <Button type="submit" loading={pending}>
        Create account
      </Button>
    </form>
  );
}
