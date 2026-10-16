import type { Metadata } from "next";
import { connection } from "next/server";
import type { ReactNode } from "react";
import { AppShell } from "@ecommerce/ui";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Backoffice", template: "%s | Backoffice" },
  robots: { index: false, follow: false },
};

const NAVIGATION = [
  { label: "Products", href: "/admin/products" },
  { label: "Imports", href: "/admin/imports" },
];

export default async function RootLayout({ children }: { children: ReactNode }) {
  await connection();
  return (
    <html lang="en">
      <body>
        <AppShell
          brand={{ label: "Backoffice", href: "/admin" }}
          navigation={NAVIGATION}
          navigationLabel="Admin"
          footer="Distributed systems e-commerce challenge, administration"
        >
          {children}
        </AppShell>
      </body>
    </html>
  );
}
