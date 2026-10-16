import type { Metadata } from "next";
import { headers } from "next/headers";
import { connection } from "next/server";
import type { ReactNode } from "react";
import { getSession, NONCE_HEADER } from "@ecommerce/auth/next";
import { NavigationProvider } from "@ecommerce/web-core/client";
import { NuqsAdapter } from "nuqs/adapters/next/app";
import { AppShell, Button, StyleNonceProvider } from "@ecommerce/ui";
import { navigationFor } from "../lib/shell-links";
import { signOutAction } from "./session-actions";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Store", template: "%s | Store" },
  description: "Distributed systems e-commerce store",
};

export default async function RootLayout({ children }: { children: ReactNode }) {
  await connection();
  const session = await getSession();
  const nonce = (await headers()).get(NONCE_HEADER) ?? undefined;
  return (
    <html lang="en">
      <body>
        <StyleNonceProvider nonce={nonce}>
          <NuqsAdapter>
            <NavigationProvider>
              <AppShell
                brand={{ label: "Store", href: "/" }}
                navigation={navigationFor(session !== null)}
                actions={
                  session ? (
                    <form action={signOutAction}>
                      <Button type="submit" variant="secondary">
                        Sign out
                      </Button>
                    </form>
                  ) : undefined
                }
                footer="Distributed systems e-commerce challenge"
              >
                {children}
              </AppShell>
            </NavigationProvider>
          </NuqsAdapter>
        </StyleNonceProvider>
      </body>
    </html>
  );
}
