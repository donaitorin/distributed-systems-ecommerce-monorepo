import { safeRedirectPath } from "@ecommerce/auth/redirect";
import { HOME_PATH, LOGIN_PATH, ZONE_PATH } from "./paths";

const ZONE_PREFIX = new RegExp(`^${ZONE_PATH}(?=[/?#]|$)`);

function insideZone(path: string): string {
  const stripped = path.replace(ZONE_PREFIX, "");
  if (stripped === "") {
    return HOME_PATH;
  }
  return stripped.startsWith("/") ? stripped : `/${stripped}`;
}

export function adminNextPath(candidate: string | null | undefined): string {
  const safe = safeRedirectPath(candidate, HOME_PATH);
  const local = safeRedirectPath(insideZone(safe), HOME_PATH);
  const loginLoop = local === LOGIN_PATH || local.startsWith(`${LOGIN_PATH}?`) || local.startsWith(`${LOGIN_PATH}/`);
  return loginLoop ? HOME_PATH : local;
}
