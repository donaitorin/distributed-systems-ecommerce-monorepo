import type { NavigationLink } from "@ecommerce/ui";
import { ACCOUNT_PATH, LOGIN_PATH, PRODUCTS_PATH } from "./paths";

export function navigationFor(signedIn: boolean): NavigationLink[] {
  return [
    { label: "Products", href: PRODUCTS_PATH },
    signedIn ? { label: "Account", href: ACCOUNT_PATH } : { label: "Sign in", href: LOGIN_PATH },
  ];
}
