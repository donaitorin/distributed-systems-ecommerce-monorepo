import { useId, type ComponentProps } from "react";
import { cn } from "../../lib/cn";

export type InputProps = ComponentProps<"input"> & {
  label: string;
  hint?: string;
  error?: string;
};

export function Input({ label, hint, error, id, className, ...props }: InputProps) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  const hintId = `${inputId}-hint`;
  const errorId = `${inputId}-error`;
  const describedBy = [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(" ");

  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={inputId} className="text-sm font-medium text-primary">
        {label}
      </label>
      <input
        id={inputId}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy || undefined}
        className={cn(
          "min-h-11 rounded-md border bg-surface px-3 text-base text-primary",
          "placeholder:text-secondary",
          "disabled:cursor-not-allowed disabled:border-border disabled:bg-surface-2 disabled:text-tertiary disabled:placeholder:text-tertiary",
          error ? "border-danger-strong" : "border-border-strong",
          className,
        )}
        {...props}
      />
      {hint ? (
        <p id={hintId} className="text-sm text-secondary">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={errorId} className="text-sm font-medium text-danger-strong">
          {error}
        </p>
      ) : null}
    </div>
  );
}
