"use client";

import { useId, type ComponentProps } from "react";
import { cn } from "../../lib/cn";

export type TextareaProps = ComponentProps<"textarea"> & {
  label: string;
  hint?: string;
  error?: string;
};

export function Textarea({ label, hint, error, id, className, rows = 4, ...props }: TextareaProps) {
  const generatedId = useId();
  const textareaId = id ?? generatedId;
  const hintId = `${textareaId}-hint`;
  const errorId = `${textareaId}-error`;
  const describedBy = [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(" ");

  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={textareaId} className="text-sm font-medium text-primary">
        {label}
      </label>
      <textarea
        id={textareaId}
        rows={rows}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy || undefined}
        className={cn(
          "rounded-md border bg-surface px-3 py-2 text-base text-primary",
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
