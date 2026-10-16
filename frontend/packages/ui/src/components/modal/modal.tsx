"use client";

import { useRef, type ReactNode } from "react";
import { Dialog } from "radix-ui";
import { CloseIcon } from "../../lib/icons";

export type ModalProps = {
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  trigger?: ReactNode;
  title: string;
  description?: string;
  children?: ReactNode;
  footer?: ReactNode;
  variant?: "dialog" | "drawer";
};

const CONTENT_CLASSES = {
  dialog:
    "fixed inset-x-4 top-1/2 z-50 mx-auto flex max-h-dvh max-w-lg -translate-y-1/2 flex-col gap-4 overflow-y-auto rounded-lg border border-border bg-surface p-6 text-primary",
  drawer:
    "fixed inset-y-0 left-0 z-50 flex w-full max-w-sm flex-col gap-4 overflow-y-auto border-r border-border bg-surface p-6 text-primary",
} as const;

export function Modal({
  open,
  onOpenChange,
  trigger,
  title,
  description,
  children,
  footer,
  variant = "dialog",
}: ModalProps) {
  const openedFrom = useRef<HTMLElement | null>(null);
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      {trigger ? <Dialog.Trigger asChild>{trigger}</Dialog.Trigger> : null}
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-overlay" />
        <Dialog.Content
          {...(description ? {} : { "aria-describedby": undefined })}
          onOpenAutoFocus={() => {
            openedFrom.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
          }}
          onCloseAutoFocus={(event) => {
            const origin = openedFrom.current;
            if (!trigger && origin?.isConnected) {
              event.preventDefault();
              origin.focus();
            }
          }}
          className={CONTENT_CLASSES[variant]}
        >
          <div className="flex items-start justify-between gap-4">
            <Dialog.Title className="text-xl font-semibold">{title}</Dialog.Title>
            <Dialog.Close
              aria-label="Close"
              className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-md hover:bg-surface-2"
            >
              <CloseIcon />
            </Dialog.Close>
          </div>
          {description ? (
            <Dialog.Description className="text-sm text-secondary">
              {description}
            </Dialog.Description>
          ) : null}
          {children}
          {footer ? <div className="flex flex-wrap justify-end gap-2">{footer}</div> : null}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
