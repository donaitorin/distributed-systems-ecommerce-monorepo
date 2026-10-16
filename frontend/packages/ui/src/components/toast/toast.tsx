"use client";

import type { ReactNode } from "react";
import { Toast as RadixToast } from "radix-ui";
import { cn } from "../../lib/cn";
import { AlertIcon, CheckIcon, CloseIcon, InfoIcon } from "../../lib/icons";

export type ToastVariant = "success" | "error" | "info";

export type ToastProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  variant?: ToastVariant;
  duration?: number;
};

const VARIANTS = {
  success: {
    label: "Success",
    icon: <CheckIcon className="size-4 shrink-0 text-success-strong" />,
    classes: "border-success-strong",
  },
  error: {
    label: "Error",
    icon: <AlertIcon className="size-4 shrink-0 text-danger-strong" />,
    classes: "border-danger-strong",
  },
  info: {
    label: "Notice",
    icon: <InfoIcon className="size-4 shrink-0 text-accent-strong" />,
    classes: "border-accent-strong",
  },
} satisfies Record<ToastVariant, { label: string; icon: ReactNode; classes: string }>;

export function ToastProvider({ children }: { children: ReactNode }) {
  return (
    <RadixToast.Provider label="Notifications" swipeDirection="right">
      {children}
      <RadixToast.Viewport className="fixed right-0 bottom-0 z-50 m-0 flex w-full max-w-sm list-none flex-col gap-2 p-4 outline-none" />
    </RadixToast.Provider>
  );
}

export function Toast({
  open,
  onOpenChange,
  title,
  description,
  variant = "info",
  duration = 5000,
}: ToastProps) {
  const { label, icon, classes } = VARIANTS[variant];

  return (
    <RadixToast.Root
      open={open}
      onOpenChange={onOpenChange}
      duration={duration}
      type={variant === "error" ? "foreground" : "background"}
      className={cn("flex items-start gap-3 rounded-md border-2 bg-surface p-4 text-primary", classes)}
    >
      {icon}
      <div className="flex-1">
        <RadixToast.Title className="text-sm font-semibold">
          <span className="sr-only">{label}: </span>
          {title}
        </RadixToast.Title>
        {description ? (
          <RadixToast.Description className="mt-1 text-sm">{description}</RadixToast.Description>
        ) : null}
      </div>
      <RadixToast.Close
        aria-label="Dismiss"
        className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-md hover:bg-surface-2"
      >
        <CloseIcon />
      </RadixToast.Close>
    </RadixToast.Root>
  );
}
