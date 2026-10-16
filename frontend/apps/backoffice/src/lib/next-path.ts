import { nextPath } from "@ecommerce/web-core";
import { HOME_PATH, LOGIN_PATH, ZONE_PATH } from "./paths";

export function adminNextPath(candidate: string | null | undefined): string {
  return nextPath(candidate, { fallback: HOME_PATH, loopPaths: [LOGIN_PATH], zonePath: ZONE_PATH });
}
