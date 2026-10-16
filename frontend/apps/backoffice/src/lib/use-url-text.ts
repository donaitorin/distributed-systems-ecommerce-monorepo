"use client";

import { useEffect, useEffectEvent, useState } from "react";

export const URL_DEBOUNCE_MS = 300;

export type UrlTextOptions = {
  value: string | null;
  commit: (next: string | null) => void;
  accept?: (text: string) => boolean;
  delay?: number;
};

export function useUrlText({ value, commit, accept, delay = URL_DEBOUNCE_MS }: UrlTextOptions) {
  const [draft, setDraft] = useState(value ?? "");
  const [committed, setCommitted] = useState(value);
  const [seen, setSeen] = useState(value);
  const publish = useEffectEvent((next: string | null) => {
    setCommitted(next);
    commit(next);
  });
  const acceptable = useEffectEvent((text: string) => accept?.(text) ?? true);

  if (value !== seen) {
    setSeen(value);
    if (value !== committed) {
      setCommitted(value);
      setDraft(value ?? "");
    }
  }

  useEffect(() => {
    const text = draft.trim();
    const next = text === "" ? null : text;
    if (next === committed || (next !== null && !acceptable(next))) {
      return;
    }
    const timer = setTimeout(() => {
      publish(next);
    }, delay);
    return () => {
      clearTimeout(timer);
    };
  }, [draft, committed, delay]);

  return [draft, setDraft] as const;
}
