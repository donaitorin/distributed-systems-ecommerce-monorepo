import { cn } from "../../lib/cn";

export type ButtonVariant = "primary" | "secondary" | "danger";

const BASE_CLASSES =
  "inline-flex min-h-11 min-w-11 items-center justify-center gap-2 rounded-md border px-4 text-sm font-medium";

const VARIANT_CLASSES: Record<ButtonVariant, string> = {
  primary: "border-transparent bg-accent-strong text-on-accent hover:bg-accent-hover",
  secondary: "border-border-strong bg-surface text-primary hover:bg-surface-2",
  danger: "border-transparent bg-danger-strong text-on-accent hover:bg-danger-hover",
};

export function buttonClasses(variant: ButtonVariant = "primary"): string {
  return cn(BASE_CLASSES, VARIANT_CLASSES[variant]);
}
