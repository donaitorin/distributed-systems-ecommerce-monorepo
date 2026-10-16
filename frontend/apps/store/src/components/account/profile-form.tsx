"use client";

import { useEffect, useRef, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { Button, Input } from "@ecommerce/ui";
import type { Failure } from "@ecommerce/web-core";
import {
  PROFILE_FIELDS,
  profileFormSchema,
  profileToFormValues,
  type Profile,
  type ProfileFormValues,
} from "../../lib/account-form";
import type { ProfileSaved } from "../../server/profile";

export type ProfileFormProps = {
  profile: Pick<Profile, "name" | "phone">;
  submit: (values: ProfileFormValues) => Promise<ProfileSaved | Failure>;
};

function failureMessage(failure: Failure): string {
  if (failure.status === 422) {
    return "Some fields need attention. Check the highlighted fields and try again.";
  }
  if (failure.status === 429) {
    return "Too many requests. Wait a moment and try again.";
  }
  return "Your profile could not be saved right now. Try again in a moment.";
}

export function ProfileForm({ profile, submit }: ProfileFormProps) {
  const alertRef = useRef<HTMLParagraphElement>(null);
  const [formError, setFormError] = useState<{ message: string; focus: boolean }>();
  const [saved, setSaved] = useState(false);
  const {
    register,
    handleSubmit,
    reset,
    setError,
    setFocus,
    formState: { errors, isSubmitting },
  } = useForm<ProfileFormValues>({
    resolver: zodResolver(profileFormSchema),
    defaultValues: profileToFormValues(profile),
  });

  useEffect(() => {
    if (formError?.focus) {
      alertRef.current?.focus();
    }
  }, [formError]);

  const save = async (values: ProfileFormValues) => {
    setFormError(undefined);
    setSaved(false);
    const result = await submit(values);
    if (result.ok) {
      reset(profileToFormValues(result.profile));
      setSaved(true);
      return;
    }
    const firstInvalid = PROFILE_FIELDS.find((field) => result.fieldErrors[field] !== undefined);
    for (const field of PROFILE_FIELDS) {
      const message = result.fieldErrors[field];
      if (message !== undefined) {
        setError(field, { type: "server", message });
      }
    }
    setFormError({ message: failureMessage(result), focus: !firstInvalid });
    if (firstInvalid) {
      setFocus(firstInvalid);
    }
  };

  return (
    <form
      onSubmit={(event) => {
        void handleSubmit(save)(event);
      }}
      noValidate
      className="flex max-w-md flex-col gap-4"
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
        label="Name"
        autoComplete="name"
        error={errors.name?.message}
        required
        {...register("name")}
      />
      <Input
        label="Phone"
        type="tel"
        autoComplete="tel"
        hint="Optional. Include the country code, like +34 600 123 456."
        error={errors.phone?.message}
        {...register("phone")}
      />
      <div className="flex flex-wrap items-center gap-4">
        <Button type="submit" loading={isSubmitting}>
          Save profile
        </Button>
        <p role="status" className="text-sm font-medium text-success-strong">
          {saved ? "Profile saved." : ""}
        </p>
      </div>
    </form>
  );
}
