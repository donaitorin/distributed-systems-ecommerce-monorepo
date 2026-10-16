import type { NavigationLink } from "@ecommerce/ui";
import { PRODUCTS_PATH, ZONE_PATH } from "./paths";

export const ADMIN_NAVIGATION: readonly NavigationLink[] = [
  { label: "Products", href: `${ZONE_PATH}${PRODUCTS_PATH}` },
];
