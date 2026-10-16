"use client";

import { createContext, useContext, useState, type ReactNode } from "react";
import { setNonce } from "get-nonce";

const StyleNonceContext = createContext<string | undefined>(undefined);

export function useStyleNonce(): string | undefined {
  return useContext(StyleNonceContext);
}

export function StyleNonceProvider({ nonce, children }: { nonce: string | undefined; children: ReactNode }) {
  const [documentNonce] = useState(nonce);
  if (documentNonce && typeof window !== "undefined") {
    setNonce(documentNonce);
  }
  return <StyleNonceContext value={documentNonce}>{children}</StyleNonceContext>;
}
