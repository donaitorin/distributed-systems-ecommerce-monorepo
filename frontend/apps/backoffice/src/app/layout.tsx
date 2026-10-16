import type { Metadata } from "next";
import { headers } from "next/headers";
import { connection } from "next/server";
import type { ReactNode } from "react";
import { getSession, NONCE_HEADER } from "@ecommerce/auth/next";
import { NuqsAdapter } from "nuqs/adapters/next/app";
import { AppShell, Button, StyleNonceProvider } from "@ecommerce/ui";
import { NavigationProvider } from "@ecommerce/web-core/client";
import { NotificationsProvider } from "../components/notifications";
import { ADMIN_NAVIGATION } from "../lib/shell-links";
import { signOutAction } from "./session-actions";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Backoffice", template: "%s | Backoffice" },
  robots: { index: false, follow: false },
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
              <NotificationsProvider>
                <AppShell
                  brand={{ label: "Backoffice", href: "/admin" }}
                  navigation={session ? ADMIN_NAVIGATION : []}
                  navigationLabel="Admin"
                  actions={
                    session ? (
                      <form action={signOutAction}>
                        <Button type="submit" variant="secondary">
                          Sign out
                        </Button>
                      </form>
                    ) : undefined
                  }
                  footer="Distributed systems e-commerce challenge, administration"
                >
                  {children}
                </AppShell>
              </NotificationsProvider>
            </NavigationProvider>
          </NuqsAdapter>
        </StyleNonceProvider>
      </body>
    </html>
  );
}
