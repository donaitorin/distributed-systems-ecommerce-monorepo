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

expect "store: GET / redirects to the product search with a temporary redirect" 307 "location: /products" "$(fetch "$GATEWAY/")"
expect "store: GET / keeps the query string when redirecting" 307 "location: /products?q=shoes&in_stock=true" "$(fetch "$GATEWAY/?q=shoes&in_stock=true")"
reaches_store /products "products-heading"
reaches_store "/products?q=runing+shoes&category=footwear&min_price=10&in_stock=true&sort=price_asc&limit=12" 'role="search"'
reaches_store "/products?min_price=abc&limit=7&sort=oldest&cursor=" "products-heading"
sample_sku=$(curl -s --max-time 10 "$GATEWAY/api/v1/products?limit=12" | grep -o '"sku":"[^"]*"' | head -1 | cut -d'"' -f4)
if [ -n "$sample_sku" ]; then
  expect "store: GET /products/$sample_sku shows the product" 200 "product-heading" "$(fetch "$GATEWAY/products/$sample_sku")"
  lower_sku=$(printf '%s' "$sample_sku" | tr '[:upper:]' '[:lower:]')
  if [ "$lower_sku" != "$sample_sku" ]; then
    expect "store: a SKU in lower case redirects to the canonical address" 307 "location: /products/$sample_sku" "$(fetch "$GATEWAY/products/$lower_sku")"
  fi
else
  pass "store: no product in the catalog, detail page checks skipped"
fi
expect "store: an unknown SKU is a real 404 page" 404 "Product not found" "$(fetch "$GATEWAY/products/NO-SUCH-SKU-0000")"
expect "store: a malformed address is refused with 400, not a server error" 400 "" "$(fetch "$GATEWAY/products/%E0%A4%A")"
reaches_store /login "Sign in"
reaches_store /register "Create an account"
expect "store: /login keeps an internal next page" 200 'name="next" value="/account"' "$(fetch "$GATEWAY/login?next=%2Faccount")"
expect "store: /login drops an absolute next URL" 200 'name="next" value="/products"' "$(fetch "$GATEWAY/login?next=https%3A%2F%2Fevil.example")"
expect "store: /login drops a protocol relative next URL" 200 'name="next" value="/products"' "$(fetch "$GATEWAY/login?next=%2F%2Fevil.example")"
expect "store: /register drops a backslash next URL" 200 'name="next" value="/products"' "$(fetch "$GATEWAY/register?next=%2F%5Cevil.example")"
expect "store: the header offers Sign in to a visitor" 200 'href="/login"' "$(fetch "$GATEWAY/products")"
if grep -qi 'Sign out' /tmp/gateway-check.body; then fail "store: a visitor must not see Sign out"; else pass "store: a visitor does not see Sign out"; fi
expect "store: GET /account (no session) redirects to the store login" 307 "location: /login?next=%2Faccount" "$(fetch "$GATEWAY/account")"
expect "store: GET /cart (no session) reaches the store and redirects to its login" 307 "location: /login?next=%2Fcart" "$(fetch "$GATEWAY/cart")"
expect "store: GET /cart/ is the store (it normalises to /cart), not the cart service" 308 "location: /cart" "$(fetch "$GATEWAY/cart/")"
unknown_order="00000000-0000-4000-8000-000000000000"
expect "store: GET /orders (no session) reaches the store and redirects to its login" 307 "location: /login?next=%2Forders" "$(fetch "$GATEWAY/orders")"
expect "store: GET /checkout (no session) reaches the store and redirects to its login" 307 "location: /login?next=%2Fcheckout" "$(fetch "$GATEWAY/checkout")"
expect "store: GET /orders/{id} (no session) reaches the store and redirects to its login" 307 "location: /login?next=%2Forders%2F$unknown_order" "$(fetch "$GATEWAY/orders/$unknown_order")"
expect "store: GET /api/orders/{id} (no session) is the store route, not the orders API" 307 "location: /login" "$(fetch "$GATEWAY/api/orders/$unknown_order")"
expect "store: unknown page is the store 404" 404 "could not be found" "$(fetch "$GATEWAY/does-not-exist")"

store_css=$(fetch "$GATEWAY/products" >/dev/null; grep -o '/_next/static/[^"]*\.css' /tmp/gateway-check.body | head -1)
expect "store: static asset $store_css" 200 "" "$(fetch "$GATEWAY$store_css")"

expect "backoffice: GET /admin (no session) redirects to the backoffice login" 307 "location: /admin/login?next=%2F" "$(fetch "$GATEWAY/admin")"
expect "backoffice: GET /admin/ is normalised to /admin" 308 "location: /admin" "$(fetch "$GATEWAY/admin/")"
expect "backoffice: GET /admin/orders (no session) is guarded" 307 "location: /admin/login?next=%2Forders" "$(fetch "$GATEWAY/admin/orders")"
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
  expect "store: /account shows the profile form" 200 'name="name"' "$(fetch -H "cookie: ecommerce_access=$customer_token" "$GATEWAY/account")"
  expect "store: the header offers Account and Sign out to a customer" 200 "Sign out" "$(fetch -H "cookie: ecommerce_access=$customer_token" "$GATEWAY/products")"
  if grep -q 'href="/login"' /tmp/gateway-check.body; then fail "store: a customer must not see the Sign in link"; else pass "store: a customer does not see the Sign in link"; fi
  expect "store: /cart with a customer session is the store cart page" 200 "Your cart" "$(fetch -H "cookie: ecommerce_access=$customer_token" "$GATEWAY/cart")"
  if grep -qi 'swagger' /tmp/gateway-check.body; then fail "store: /cart must not be the cart service documentation"; else pass "store: /cart is not the cart service documentation"; fi
  expect "store: /checkout with a customer session is the store checkout page" 200 "Checkout" "$(fetch -H "cookie: ecommerce_access=$customer_token" "$GATEWAY/checkout")"
  if grep -qi 'swagger' /tmp/gateway-check.body; then fail "store: /checkout must not be an API documentation page"; else pass "store: /checkout is not an API documentation page"; fi
  expect "store: an unknown order is the store 404 page, not an orders API problem" 404 "Order not found" "$(fetch -H "cookie: ecommerce_access=$customer_token" "$GATEWAY/orders/$unknown_order")"
  if [ "$(header content-type)" = "application/problem+json" ] || grep -qi 'swagger' /tmp/gateway-check.body; then fail "store: /orders/{id} must stay with the store"; else pass "store: /orders/{id} is served by the store as a page"; fi
  expect "store: /api/orders/{id} answers from the store route handler (problem+json)" 404 "Order not found" "$(fetch -H "cookie: ecommerce_access=$customer_token" "$GATEWAY/api/orders/$unknown_order")"
  expect "store: /api/orders/{id} refuses a malformed id" 404 "problem+json" "$(fetch -H "cookie: ecommerce_access=$customer_token" "$GATEWAY/api/orders/not-an-id")"
  expect "store: /orders with a customer session is the order history page" 200 "orders-heading" "$(fetch -H "cookie: ecommerce_access=$customer_token" "$GATEWAY/orders")"
  if [ "$(header content-type)" = "application/problem+json" ] || grep -qi 'swagger' /tmp/gateway-check.body; then fail "store: /orders must stay with the store"; else pass "store: /orders is served by the store as a page"; fi
  expect "store: /orders keeps a forward cursor in the address" 200 "orders-heading" "$(fetch -H "cookie: ecommerce_access=$customer_token" "$GATEWAY/orders?cursor=not-a-cursor")"
  expect "store: the header offers the order history to a customer" 200 'href="/orders"' "$(fetch -H "cookie: ecommerce_access=$customer_token" "$GATEWAY/products")"
  expect "store: /account links to the order history" 200 'View your orders' "$(fetch -H "cookie: ecommerce_access=$customer_token" "$GATEWAY/account")"
  expect "store: /account lists the shipping addresses section" 200 "addresses-heading" "$(fetch -H "cookie: ecommerce_access=$customer_token" "$GATEWAY/account")"
  expect "store: the header offers the cart to a customer" 200 'href="/cart"' "$(fetch -H "cookie: ecommerce_access=$customer_token" "$GATEWAY/products")"
  expect "store: /login sends a signed in customer on to the next page" 307 "location: /account" "$(fetch -H "cookie: ecommerce_access=$customer_token" "$GATEWAY/login?next=%2Faccount")"
  expect "store: /register sends a signed in customer to the products page" 307 "location: /products" "$(fetch -H "cookie: ecommerce_access=$customer_token" "$GATEWAY/register")"
  expect "backoffice: /admin/products renders for an admin" 200 "products-heading" "$(fetch -H "cookie: ecommerce_access=$admin_token" "$GATEWAY/admin/products")"
  expect "backoffice: the products page links to the CSV import route" 200 'href="/admin/products/import"' "$(fetch -H "cookie: ecommerce_access=$admin_token" "$GATEWAY/admin/products")"
  if grep -qi 'href="/admin/imports"' /tmp/gateway-check.body; then fail "backoffice: the shell must not link to a separate imports page"; else pass "backoffice: the shell has no separate imports link"; fi
  expect "backoffice: /admin/categories renders for an admin" 200 "categories-heading" "$(fetch -H "cookie: ecommerce_access=$admin_token" "$GATEWAY/admin/categories")"
  expect "backoffice: /admin/users renders for an admin" 200 "users-heading" "$(fetch -H "cookie: ecommerce_access=$admin_token" "$GATEWAY/admin/users")"
  expect "backoffice: /admin/orders renders for an admin" 200 "orders-heading" "$(fetch -H "cookie: ecommerce_access=$admin_token" "$GATEWAY/admin/orders")"
  if [ "$(header content-type)" = "application/problem+json" ] || grep -qi 'swagger' /tmp/gateway-check.body; then fail "backoffice: /admin/orders must stay with the backoffice"; else pass "backoffice: /admin/orders is served by the backoffice as a page"; fi
  expect "backoffice: /admin/orders with filters in the address" 200 "orders-heading" "$(fetch -H "cookie: ecommerce_access=$admin_token" "$GATEWAY/admin/orders?status=CANCELLED&from=2026-10-01&to=2026-10-17&limit=50")"
  expect "backoffice: /admin/orders ignores invalid filters instead of failing" 200 "orders-heading" "$(fetch -H "cookie: ecommerce_access=$admin_token" "$GATEWAY/admin/orders?status=SHIPPED&from=abc&to=2026-02-30&limit=7")"
  expect "backoffice: /admin/orders explains an end date before the start date" 200 "on or after the start date" "$(fetch -H "cookie: ecommerce_access=$admin_token" "$GATEWAY/admin/orders?from=2026-10-17&to=2026-10-01")"
  expect "backoffice: /admin/orders/{id} is a real 404 page for an unknown order" 404 "Page not found" "$(fetch -H "cookie: ecommerce_access=$admin_token" "$GATEWAY/admin/orders/$unknown_order")"
  expect "backoffice: the shell links to the orders" 200 'href="/admin/orders"' "$(fetch -H "cookie: ecommerce_access=$admin_token" "$GATEWAY/admin/products")"
  expect "backoffice: /admin/orders with a customer session is sent back to login" 307 "reason=forbidden" "$(fetch -H "cookie: ecommerce_access=$customer_token" "$GATEWAY/admin/orders")"
  expect "backoffice: /admin/orders/{id} with a customer session is sent back to login" 307 "reason=forbidden" "$(fetch -H "cookie: ecommerce_access=$customer_token" "$GATEWAY/admin/orders/$unknown_order")"
  for section in categories users; do
    expect "backoffice: the shell links to $section" 200 "href=\"/admin/$section\"" "$(fetch -H "cookie: ecommerce_access=$admin_token" "$GATEWAY/admin/products")"
    expect "backoffice: /admin/$section with a customer session is sent back to login" 307 "reason=forbidden" "$(fetch -H "cookie: ecommerce_access=$customer_token" "$GATEWAY/admin/$section")"
  done
  expect "backoffice: /admin/products/import renders for an admin (the static route, not a SKU page)" 200 "Import products from CSV" "$(fetch -H "cookie: ecommerce_access=$admin_token" "$GATEWAY/admin/products/import")"
  expect "backoffice: /admin/products/import with a customer session is sent back to login" 307 "reason=forbidden" "$(fetch -H "cookie: ecommerce_access=$customer_token" "$GATEWAY/admin/products/import")"
  import_upload() {
    fetch -X POST -H "content-type: text/plain" --data x "$@" "$GATEWAY/admin/api/stream/imports"
  }
  expect "backoffice: CSV upload route without a session answers 401 problem+json" 401 "problem+json" "$(import_upload)"
  expect "backoffice: CSV upload route with a customer session answers 403" 403 "problem+json" "$(import_upload -H "cookie: ecommerce_access=$customer_token")"
  expect "backoffice: CSV upload route reaches the catalog API for an admin" 415 "Unsupported media type" "$(import_upload -H "cookie: ecommerce_access=$admin_token")"
  unknown_import="00000000-0000-4000-8000-000000000000"
  expect "backoffice: import status route without a session is sent to login" 307 "location: /admin/login" "$(fetch "$GATEWAY/admin/api/imports/$unknown_import")"
  expect "backoffice: import status route answers 404 problem+json for an unknown import" 404 "problem+json" "$(fetch -H "cookie: ecommerce_access=$admin_token" "$GATEWAY/admin/api/imports/$unknown_import")"
  expect "backoffice: problems.csv route answers 404 problem+json for an unknown import" 404 "problem+json" "$(fetch -H "cookie: ecommerce_access=$admin_token" "$GATEWAY/admin/api/imports/$unknown_import/problems.csv")"
  expect "backoffice: /admin/products/new renders for an admin" 200 "New product" "$(fetch -H "cookie: ecommerce_access=$admin_token" "$GATEWAY/admin/products/new")"
  expect "backoffice: /admin/products with a customer session is sent back to login" 307 "reason=forbidden" "$(fetch -H "cookie: ecommerce_access=$customer_token" "$GATEWAY/admin/products")"
  upload() {
    fetch -X PUT -H "content-type: text/plain" -H 'if-match: "1"' --data x "$@" "$GATEWAY/admin/api/stream/products/NO-SUCH-SKU/image"
  }
  expect "backoffice: image upload route without a session answers 401 problem+json, not a login redirect" 401 "problem+json" "$(upload)"
  expect "backoffice: image upload route with a customer session answers 403" 403 "problem+json" "$(upload -H "cookie: ecommerce_access=$customer_token")"
  expect "backoffice: image upload route reaches the catalog API for an admin" 404 "No product with SKU" "$(upload -H "cookie: ecommerce_access=$admin_token")"
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

expect "cart: GET /api/v1/cart needs a token" 401 "problem+json" "$(fetch "$GATEWAY/api/v1/cart")"
expect "cart: GET /cart-service/health" 200 '"status":"ok"' "$(fetch "$GATEWAY/cart-service/health")"
expect "cart: GET /cart-service/ready" 200 '"redis":"ok"' "$(fetch "$GATEWAY/cart-service/ready")"

expect "orders: GET /api/v1/orders needs a token" 401 "problem+json" "$(fetch "$GATEWAY/api/v1/orders")"
expect "orders: POST /api/v1/orders needs a token" 401 "problem+json" "$(fetch -X POST -H "content-type: application/json" --data '{}' "$GATEWAY/api/v1/orders")"
expect "orders: GET /api/v1/admin/orders needs a token" 401 "problem+json" "$(fetch "$GATEWAY/api/v1/admin/orders")"
expect "orders: GET /orders-service/health" 200 '"status":"ok"' "$(fetch "$GATEWAY/orders-service/health")"
expect "orders: GET /orders-service/ready" 200 '"database":"ok"' "$(fetch "$GATEWAY/orders-service/ready")"
expect "orders: GET /orders-service/docs" 200 "swagger" "$(fetch "$GATEWAY/orders-service/docs")"
fetch "$GATEWAY/orders" >/dev/null
if grep -qi 'swagger' /tmp/gateway-check.body || [ "$(header content-type)" = "application/problem+json" ]; then
  fail "orders: /orders must stay with the store, not the orders service"
else
  pass "orders: /orders is not shadowed by the orders service"
fi
if [ -n "${admin_token:-}" ] && [ -n "${customer_token:-}" ]; then
  expect "orders: a customer lists their orders" 200 '"items"' "$(fetch -H "authorization: Bearer $customer_token" "$GATEWAY/api/v1/orders")"
  order_body='{"lines":[{"sku":"X-1","quantity":1,"unit_price":"1.00"}],"shipping_address":{"recipient_name":"Ada","line1":"1 St","city":"London","postal_code":"N1","country":"GB"},"payment":{"card_number":"4111111111111111"}}'
  expect "orders: placing an order without an Idempotency-Key is a 400" 400 "idempotency_key_invalid" "$(fetch -X POST -H "authorization: Bearer $customer_token" -H "content-type: application/json" --data "$order_body" "$GATEWAY/api/v1/orders")"
  expect "orders: a customer cannot use the admin list" 403 "problem+json" "$(fetch -H "authorization: Bearer $customer_token" "$GATEWAY/api/v1/admin/orders")"
  expect "orders: an admin lists every order" 200 '"items"' "$(fetch -H "authorization: Bearer $admin_token" "$GATEWAY/api/v1/admin/orders")"
  expect "orders: an unknown order is a 404 problem" 404 "problem+json" "$(fetch -H "authorization: Bearer $admin_token" "$GATEWAY/api/v1/admin/orders/00000000-0000-4000-8000-000000000000")"
fi

expect "payments: GET /api/v1/payments/{order_id} needs a token" 401 "problem+json" "$(fetch "$GATEWAY/api/v1/payments/00000000-0000-4000-8000-000000000000")"
expect "payments: GET /payments-service/health" 200 '"status":"ok"' "$(fetch "$GATEWAY/payments-service/health")"
expect "payments: GET /payments-service/ready" 200 '"database":"ok"' "$(fetch "$GATEWAY/payments-service/ready")"
expect "payments: GET /payments-service/docs" 200 "swagger" "$(fetch "$GATEWAY/payments-service/docs")"
fetch "$GATEWAY/payments" >/dev/null
if grep -qi 'swagger' /tmp/gateway-check.body || [ "$(header content-type)" = "application/problem+json" ]; then
  fail "payments: /payments must stay with the store, not the payments service"
else
  pass "payments: /payments is not shadowed by the payments service"
fi
if [ -n "${customer_token:-}" ]; then
  expect "payments: an order without a payment is a 404 problem" 404 "problem+json" "$(fetch -H "authorization: Bearer $customer_token" "$GATEWAY/api/v1/payments/00000000-0000-4000-8000-000000000000")"
fi

LOCALHOST="http://localhost:${GATEWAY_HTTP_PORT:-8000}"
expect "localhost: backoffice login page" 200 "Administrator sign in" "$(fetch "$LOCALHOST/admin/login")"
expect "localhost: /admin/products is guarded with a host-relative redirect" 307 "location: /admin/login?next=%2Fproducts" "$(fetch "$LOCALHOST/admin/products")"
expect "localhost: store home redirects to the product search" 307 "location: /products" "$(fetch "$LOCALHOST/")"
expect "localhost: store product search" 200 "products-heading" "$(fetch "$LOCALHOST/products")"
if [ -n "${admin_token:-}" ]; then
  expect "localhost: /admin/products renders for an admin session" 200 "products-heading" "$(fetch -H "cookie: ecommerce_access=$admin_token" "$LOCALHOST/admin/products")"
fi
status=$(fetch "$LOCALHOST/media/media/nonexistent.webp")
if { [ "$status" = 404 ] || [ "$status" = 403 ]; } && ! grep -qi "html" /tmp/gateway-check.headers; then
  pass "localhost: /media/... is served by the same host (same-origin images)"
else
  fail "localhost: /media/... answered $status $(header content-type)"
fi

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
