import type { NavigationLink } from "@ecommerce/ui";
import { CATEGORIES_PATH, ORDERS_PATH, PRODUCTS_PATH, USERS_PATH, ZONE_PATH } from "./paths";

export const ADMIN_NAVIGATION: readonly NavigationLink[] = [
  { label: "Products", href: `${ZONE_PATH}${PRODUCTS_PATH}` },
  { label: "Categories", href: `${ZONE_PATH}${CATEGORIES_PATH}` },
  { label: "Orders", href: `${ZONE_PATH}${ORDERS_PATH}` },
  { label: "Users", href: `${ZONE_PATH}${USERS_PATH}` },
];
