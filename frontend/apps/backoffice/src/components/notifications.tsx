"use client";

import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";
import { Toast, ToastProvider, type ToastVariant } from "@ecommerce/ui";

export type Notice = {
  title: string;
  description?: string;
  variant?: ToastVariant;
};

type Notify = (notice: Notice) => void;

type Entry = Notice & { id: number };

const NotifyContext = createContext<Notify>(() => undefined);

export function useNotify(): Notify {
  return useContext(NotifyContext);
}

export function NotificationsProvider({ children }: { children: ReactNode }) {
  const [entries, setEntries] = useState<Entry[]>([]);
  const nextId = useRef(0);

  const notify = useCallback<Notify>((notice) => {
    const id = nextId.current++;
    setEntries((current) => [...current, { ...notice, id }]);
  }, []);

  return (
    <ToastProvider>
      <NotifyContext value={notify}>{children}</NotifyContext>
      {entries.map((entry) => (
        <Toast
          key={entry.id}
          open
          onOpenChange={(open) => {
            if (!open) {
              setEntries((current) => current.filter((candidate) => candidate.id !== entry.id));
            }
          }}
          title={entry.title}
          description={entry.description}
          variant={entry.variant ?? "info"}
        />
      ))}
    </ToastProvider>
  );
}
