import type { ComponentProps } from "react";
import { cn } from "../../lib/cn";
import { SpinnerIcon } from "../../lib/icons";

export type ButtonVariant = "primary" | "secondary" | "danger";

export type ButtonProps = ComponentProps<"button"> & {
  variant?: ButtonVariant;
  loading?: boolean;
};

const DISABLED_CLASSES =
  "cursor-not-allowed border-border bg-surface-2 text-tertiary hover:bg-surface-2";

const VARIANT_CLASSES: Record<ButtonVariant, string> = {
  primary: "border-transparent bg-accent-strong text-on-accent hover:bg-accent-hover",
  secondary: "border-border-strong bg-surface text-primary hover:bg-surface-2",
  danger: "border-transparent bg-danger-strong text-on-accent hover:bg-danger-hover",
};

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
        "inline-flex min-h-11 min-w-11 items-center justify-center gap-2 rounded-md border px-4 text-sm font-medium",
        VARIANT_CLASSES[variant],
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
