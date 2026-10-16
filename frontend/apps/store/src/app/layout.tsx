import type { Metadata } from "next";
import { connection } from "next/server";
import type { ReactNode } from "react";
import { AppShell } from "@ecommerce/ui";
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
  return (
    <html lang="en">
      <body>
        <AppShell
          brand={{ label: "Store", href: "/" }}
          navigation={NAVIGATION}
          footer="Distributed systems e-commerce challenge"
        >
          {children}
        </AppShell>
      </body>
    </html>
  );
}
