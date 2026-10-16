#!/usr/bin/env bash
set -u

GATEWAY="http://127.0.0.1:${GATEWAY_HTTP_PORT:-8000}"
DASHBOARD="http://127.0.0.1:${GATEWAY_DASHBOARD_PORT:-8001}"
failures=0

fetch() {
  curl -s -S --max-time 10 -o /tmp/gateway-check.body -D /tmp/gateway-check.headers -w '%{http_code}' "$@"
}

header() {
  grep -i "^$1:" /tmp/gateway-check.headers | head -1 | cut -d: -f2- | tr -d '\r' | sed 's/^ *//'
}

pass() { printf 'PASS  %s\n' "$1"; }
fail() { printf 'FAIL  %s\n' "$1"; failures=$((failures + 1)); }

expect() {
  local label=$1 want_status=$2 want_text=$3 got_status=$4
  if [ "$got_status" != "$want_status" ]; then
    fail "$label: status $got_status, expected $want_status"
  elif [ -n "$want_text" ] && ! grep -qi -- "$want_text" /tmp/gateway-check.body /tmp/gateway-check.headers; then
    fail "$label: response does not contain '$want_text'"
  else
    pass "$label"
  fi
}

reaches_store() {
  expect "store: GET $1" 200 "$2" "$(fetch "$GATEWAY$1")"
}

expect "store: GET /" 200 "Welcome to the store" "$(fetch "$GATEWAY/")"
reaches_store /login "Sign in"
expect "store: GET /account (no session) redirects to the store login" 307 "location: /login?next=%2Faccount" "$(fetch "$GATEWAY/account")"
expect "store: unknown page is the store 404" 404 "could not be found" "$(fetch "$GATEWAY/does-not-exist")"

store_css=$(fetch "$GATEWAY/" >/dev/null; grep -o '/_next/static/[^"]*\.css' /tmp/gateway-check.body | head -1)
expect "store: static asset $store_css" 200 "" "$(fetch "$GATEWAY$store_css")"

expect "backoffice: GET /admin (no session) redirects to the backoffice login" 307 "location: /admin/login?next=%2F" "$(fetch "$GATEWAY/admin")"
expect "backoffice: GET /admin/ is normalised to /admin" 308 "location: /admin" "$(fetch "$GATEWAY/admin/")"
expect "backoffice: GET /admin/products is guarded" 307 "location: /admin/login" "$(fetch "$GATEWAY/admin/products")"
expect "backoffice: GET /admin/login" 200 "Administrator sign in" "$(fetch "$GATEWAY/admin/login")"
backoffice_css=$(grep -o '/admin/_next/static/[^"]*\.css' /tmp/gateway-check.body | head -1)
expect "backoffice: static asset $backoffice_css" 200 "" "$(fetch "$GATEWAY$backoffice_css")"
expect "backoffice: /admin/robots.txt is behind the guard, not served by the store" 307 "location: /admin/login" "$(fetch "$GATEWAY/admin/robots.txt")"
expect "store: robots allows crawling" 200 "Allow: /" "$(fetch "$GATEWAY/robots.txt")"

here=$(dirname "$0")
admin_token=$(ROLE=admin "$here/dev-token.sh" 2>/dev/null)
customer_token=$(ROLE=customer "$here/dev-token.sh" 2>/dev/null)
if [ -n "$admin_token" ] && [ -n "$customer_token" ]; then
  expect "backoffice: /admin with an admin session" 200 "Backoffice" "$(fetch -H "cookie: ecommerce_access=$admin_token" "$GATEWAY/admin")"
  expect "backoffice: /admin with a customer session is sent back to login" 307 "reason=forbidden" "$(fetch -H "cookie: ecommerce_access=$customer_token" "$GATEWAY/admin")"
  expect "store: /account with a customer session" 200 "Signed in as" "$(fetch -H "cookie: ecommerce_access=$customer_token" "$GATEWAY/account")"
else
  fail "sessions: could not log in through the gateway (is the stack up and .env present?)"
fi

status=$(fetch "$GATEWAY/api/v1/products?limit=12")
expect "catalog: GET /api/v1/products is not shadowed" 200 '"items"' "$status"
[ "$(header content-type)" = "application/json" ] && pass "catalog: products answer JSON" || fail "catalog: products content type is '$(header content-type)'"
expect "catalog: GET /api/v1/categories" 200 "" "$(fetch "$GATEWAY/api/v1/categories")"
expect "catalog: GET /api/v1/imports/{id} needs a token (not a Next page)" 401 "problem+json" "$(fetch "$GATEWAY/api/v1/imports/00000000-0000-0000-0000-000000000000")"
expect "catalog: GET /catalog/health" 200 '"status":"ok"' "$(fetch "$GATEWAY/catalog/health")"
expect "catalog: GET /catalog/docs" 200 "swagger" "$(fetch "$GATEWAY/catalog/docs")"
expect "auth: GET /api/v1/auth/.well-known/jwks.json" 200 '"keys"' "$(fetch "$GATEWAY/api/v1/auth/.well-known/jwks.json")"
expect "auth: GET /api/v1/auth/login is a 405 from the API, not a store 404" 405 "" "$(fetch "$GATEWAY/api/v1/auth/login")"
expect "auth: GET /auth/health" 200 '"status":"ok"' "$(fetch "$GATEWAY/auth/health")"
expect "auth: GET /auth/ready" 200 "" "$(fetch "$GATEWAY/auth/ready")"
expect "accounts: GET /api/v1/accounts/me needs a token" 401 "problem+json" "$(fetch "$GATEWAY/api/v1/accounts/me")"
expect "accounts: GET /accounts/health" 200 '"status":"ok"' "$(fetch "$GATEWAY/accounts/health")"

status=$(fetch "$GATEWAY/media/media/nonexistent.webp")
if { [ "$status" = 404 ] || [ "$status" = 403 ]; } && ! grep -qi "html" /tmp/gateway-check.headers; then
  pass "media: GET /media/... goes to object storage ($status, $(header content-type))"
else
  fail "media: GET /media/... answered $status $(header content-type)"
fi

routers=$(curl -s -S --max-time 10 "$DASHBOARD/api/http/routers") || routers=""
if [ -z "$routers" ]; then
  fail "dashboard: could not read the router table"
else
  disabled=$(printf '%s' "$routers" | python3 -c "
import json, sys
print(sum(1 for r in json.load(sys.stdin) if r['status'] != 'enabled'))")
  [ "$disabled" = 0 ] && pass "router table: every router is enabled" || fail "router table: $disabled router(s) are disabled (see the gateway logs)"
  lowest=$(printf '%s' "$routers" | python3 -c "
import json, sys
routers = [r for r in json.load(sys.stdin) if r['provider'] == 'file']
print(min(routers, key=lambda r: r['priority'])['name'])")
  [ "$lowest" = "store@file" ] && pass "router table: the store catch-all has the lowest priority" || fail "router table: lowest priority router is $lowest"
  zone_overlap=$(printf '%s' "$routers" | python3 -c "
import json, sys
routers = [r for r in json.load(sys.stdin) if r['provider'] == 'file']
zones = {'store@file', 'backoffice@file'}
print(sum(1 for r in routers if r['name'] not in zones and r['priority'] <= 10))")
  [ "$zone_overlap" = 0 ] && pass "router table: every API, docs and media router outranks the zone routers" || fail "router table: $zone_overlap router(s) rank at or below the backoffice zone"
fi

if [ "$failures" -gt 0 ]; then
  printf '\n%s check(s) failed\n' "$failures"
  exit 1
fi
printf '\nall gateway route checks passed\n'
