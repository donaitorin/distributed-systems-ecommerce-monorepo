import type { Metadata } from "next";
import { headers } from "next/headers";
import { connection } from "next/server";
import type { ReactNode } from "react";
import { NONCE_HEADER } from "@ecommerce/auth/next";
import { AppShell, StyleNonceProvider } from "@ecommerce/ui";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Store", template: "%s | Store" },
  description: "Distributed systems e-commerce store",
};

const NAVIGATION = [
  { label: "Account", href: "/account" },
  { label: "Sign in", href: "/login" },
];

export default async function RootLayout({ children }: { children: ReactNode }) {
  await connection();
  const nonce = (await headers()).get(NONCE_HEADER) ?? undefined;
  return (
    <html lang="en">
      <body>
        <StyleNonceProvider nonce={nonce}>
          <AppShell
            brand={{ label: "Store", href: "/" }}
            navigation={NAVIGATION}
            footer="Distributed systems e-commerce challenge"
          >
            {children}
          </AppShell>
        </StyleNonceProvider>
      </body>
    </html>
  );
}
