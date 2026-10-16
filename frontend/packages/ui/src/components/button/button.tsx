"use client";

import type { ComponentProps } from "react";
import { cn } from "../../lib/cn";
import { SpinnerIcon } from "../../lib/icons";
import { buttonClasses, type ButtonVariant } from "./button-classes";

export type { ButtonVariant };

export type ButtonProps = ComponentProps<"button"> & {
  variant?: ButtonVariant;
  loading?: boolean;
};

const DISABLED_CLASSES =
  "cursor-not-allowed border-border bg-surface-2 text-tertiary hover:bg-surface-2";

export function Button({
  variant = "primary",
  loading = false,
  disabled = false,
  type = "button",
  className,
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cn(
        buttonClasses(variant),
        loading && "cursor-wait",
        disabled && DISABLED_CLASSES,
        className,
      )}
      {...props}
    >
      {loading ? <SpinnerIcon /> : null}
      {children}
    </button>
  );
}
