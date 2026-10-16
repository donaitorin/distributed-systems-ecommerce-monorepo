import type { ReactNode } from "react";

export type NavigationLink = {
  label: string;
  href: string;
};

export type AppShellProps = {
  brand: NavigationLink;
  navigation?: readonly NavigationLink[];
  navigationLabel?: string;
  footer?: ReactNode;
  children: ReactNode;
};

export const MAIN_CONTENT_ID = "main-content";

export function AppShell({
  brand,
  navigation = [],
  navigationLabel = "Main",
  footer,
  children,
}: AppShellProps) {
  return (
    <div className="flex min-h-dvh flex-col bg-background text-primary">
      <a
        href={`#${MAIN_CONTENT_ID}`}
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded-md focus:bg-surface focus:px-4 focus:py-3 focus:text-sm focus:font-medium focus:text-accent-strong"
      >
        Skip to content
      </a>
      <header className="border-b border-border bg-surface">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-4 py-3">
          <a href={brand.href} className="font-serif text-xl font-semibold text-primary">
            {brand.label}
          </a>
          {navigation.length > 0 ? (
            <nav aria-label={navigationLabel}>
              <ul className="flex flex-wrap gap-2">
                {navigation.map((link) => (
                  <li key={link.href}>
                    <a
                      href={link.href}
                      className="inline-flex min-h-11 items-center rounded-md px-3 text-sm font-medium text-primary hover:bg-surface-2"
                    >
                      {link.label}
                    </a>
                  </li>
                ))}
              </ul>
            </nav>
          ) : null}
        </div>
      </header>
      <main id={MAIN_CONTENT_ID} tabIndex={-1} className="mx-auto w-full max-w-6xl flex-1 px-4 py-8">
        {children}
      </main>
      <footer className="border-t border-border bg-surface">
        <div className="mx-auto max-w-6xl px-4 py-6 text-sm text-secondary">{footer}</div>
      </footer>
    </div>
  );
}
