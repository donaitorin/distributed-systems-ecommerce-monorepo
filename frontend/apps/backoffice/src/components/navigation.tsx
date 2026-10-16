"use client";

import { createContext, useContext, useMemo, type ReactNode } from "react";
import { useRouter } from "next/navigation";

export type Navigation = {
  push: (path: string) => void;
  refresh: () => void;
};

export const NavigationContext = createContext<Navigation>({
  push: () => undefined,
  refresh: () => undefined,
});

export function useNavigation(): Navigation {
  return useContext(NavigationContext);
}

export function NavigationProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const navigation = useMemo<Navigation>(
    () => ({
      push: (path) => {
        router.push(path);
      },
      refresh: () => {
        router.refresh();
      },
    }),
    [router],
  );
  return <NavigationContext value={navigation}>{children}</NavigationContext>;
}
