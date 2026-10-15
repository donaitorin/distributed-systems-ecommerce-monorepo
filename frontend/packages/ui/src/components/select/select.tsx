import { useId } from "react";
import { Select as RadixSelect } from "radix-ui";
import { cn } from "../../lib/cn";
import { CheckIcon, ChevronDownIcon } from "../../lib/icons";

export type SelectOption = {
  value: string;
  label: string;
  disabled?: boolean;
};

export type SelectProps = {
  label: string;
  options: readonly SelectOption[];
  value?: string;
  defaultValue?: string;
  onValueChange?: (value: string) => void;
  placeholder?: string;
  hint?: string;
  error?: string;
  disabled?: boolean;
  required?: boolean;
  name?: string;
  id?: string;
};

export function Select({
  label,
  options,
  placeholder = "Select an option",
  hint,
  error,
  id,
  ...rootProps
}: SelectProps) {
  const generatedId = useId();
  const triggerId = id ?? generatedId;
  const hintId = `${triggerId}-hint`;
  const errorId = `${triggerId}-error`;
  const describedBy = [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(" ");

  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={triggerId} className="text-sm font-medium text-foreground">
        {label}
      </label>
      <RadixSelect.Root {...rootProps}>
        <RadixSelect.Trigger
          id={triggerId}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy || undefined}
          className={cn(
            "flex min-h-11 items-center justify-between gap-2 rounded-md border bg-background px-3 text-base text-foreground",
            "data-placeholder:text-muted-foreground disabled:cursor-not-allowed disabled:bg-muted disabled:opacity-60",
            error ? "border-danger" : "border-control-border",
          )}
        >
          <RadixSelect.Value placeholder={placeholder} />
          <RadixSelect.Icon>
            <ChevronDownIcon />
          </RadixSelect.Icon>
        </RadixSelect.Trigger>
        <RadixSelect.Portal>
          <RadixSelect.Content
            position="popper"
            sideOffset={4}
            className="z-50 max-h-80 min-w-(--radix-select-trigger-width) overflow-hidden rounded-md border border-control-border bg-background text-foreground"
          >
            <RadixSelect.Viewport className="p-1">
              {options.map((option) => (
                <RadixSelect.Item
                  key={option.value}
                  value={option.value}
                  disabled={option.disabled}
                  className="flex min-h-11 cursor-pointer items-center justify-between gap-2 rounded-sm px-3 text-base data-disabled:cursor-not-allowed data-disabled:opacity-60 data-highlighted:bg-muted"
                >
                  <RadixSelect.ItemText>{option.label}</RadixSelect.ItemText>
                  <RadixSelect.ItemIndicator>
                    <CheckIcon />
                  </RadixSelect.ItemIndicator>
                </RadixSelect.Item>
              ))}
            </RadixSelect.Viewport>
          </RadixSelect.Content>
        </RadixSelect.Portal>
      </RadixSelect.Root>
      {hint ? (
        <p id={hintId} className="text-sm text-muted-foreground">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={errorId} className="text-sm font-medium text-danger">
          {error}
        </p>
      ) : null}
    </div>
  );
}
