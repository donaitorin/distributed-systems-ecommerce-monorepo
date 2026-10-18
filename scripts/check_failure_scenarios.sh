#!/bin/sh
set -eu

cd "$(dirname "$0")/.."
if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi

scenario="${1:-all}"
gateway="http://127.0.0.1:${GATEWAY_HTTP_PORT:-8000}"
saga_timeout="${ORDERS_SAGA_TIMEOUT_SECONDS:-60}"
poll_seconds=2
kafka_outage_seconds="${KAFKA_OUTAGE_SECONDS:-15}"
run_id="$(date +%s)"
body_file="$(mktemp)"
failed=0

cleanup() {
  rm -f "$body_file"
  docker compose start payments payments-worker kafka >/dev/null 2>&1 || true
}
trap cleanup EXIT

say() { printf '%s\n' "$*"; }
fail() { say "FAIL $*" >&2; failed=1; }

field() {
  python3 -c '
import json, sys
value = json.load(sys.stdin)
for part in sys.argv[1].split("."):
    value = value[int(part)] if part.isdigit() else value.get(part) if isinstance(value, dict) else None
print("" if value is None else value)
' "$1"
}

http() {
  method="$1"; path="$2"; token="${3:-}"; data="${4:-}"; key="${5:-}"
  set -- -s --max-time 20 -o "$body_file" -w '%{http_code}' -X "$method" "$gateway$path"
  [ -n "$token" ] && set -- "$@" -H "Authorization: Bearer $token"
  [ -n "$key" ] && set -- "$@" -H "Idempotency-Key: $key"
  [ -n "$data" ] && set -- "$@" -H 'content-type: application/json' -d "$data"
  curl "$@"
}

body() { cat "$body_file"; }

wait_for() {
  description="$1"; seconds="$2"; shift 2
  deadline=$(( $(date +%s) + seconds ))
  while :; do
    if "$@"; then say "ok   $description"; return 0; fi
    if [ "$(date +%s)" -ge "$deadline" ]; then fail "$description (waited ${seconds}s)"; return 1; fi
    sleep "$poll_seconds"
  done
}

admin_token() { ROLE=admin ./scripts/dev-token.sh; }
customer_token() { ROLE=customer ./scripts/dev-token.sh; }

create_product() {
  sku="SCEN-$run_id-$1"
  http POST /api/v1/products "$2" \
    "{\"name\":\"Scenario $sku\",\"sku\":\"$sku\",\"price\":\"10.00\",\"stock\":5}" >/dev/null
  echo "$sku"
}

stock_of() { http GET "/api/v1/products/$1" "" >/dev/null; body | field stock; }

place_order() {
  http POST /api/v1/orders "$1" \
    "{\"lines\":[{\"sku\":\"$2\",\"quantity\":2,\"unit_price\":\"10.00\"}],\"shipping_address\":{\"recipient_name\":\"Ada Lovelace\",\"line1\":\"12 Analytical St\",\"city\":\"London\",\"postal_code\":\"N1 9GU\",\"country\":\"GB\"},\"payment\":{\"card_number\":\"4929 1234 5678 1111\"}}" \
    "scen-$run_id-$3"
}

order_status() { http GET "/api/v1/orders/$2" "$1" >/dev/null; body | field status; }
order_reason() { http GET "/api/v1/orders/$2" "$1" >/dev/null; body | field cancel_reason; }
payment_status() { http GET "/api/v1/payments/$2" "$1" >/dev/null; body | field status; }

status_is() { [ "$(order_status "$1" "$2")" = "$3" ]; }
stock_is() { [ "$(stock_of "$1")" = "$2" ]; }
payment_is() { [ "$(payment_status "$1" "$2")" = "$3" ]; }

payments_scenario() {
  say "== payments stopped during a purchase (saga timeout ${saga_timeout}s)"
  admin="$(admin_token)"; customer="$(customer_token)"
  sku="$(create_product payments "$admin")"
  docker compose stop payments payments-worker >/dev/null
  code="$(place_order "$customer" "$sku" payments-1)"
  [ "$code" = 202 ] && say "ok   order accepted while payments is down (HTTP $code)" || fail "order answered HTTP $code"
  order_id="$(body | field id)"
  wait_for "stock reserved, order waiting for payment" 30 status_is "$customer" "$order_id" STOCK_RESERVED || return 0
  wait_for "stock taken (3 left)" 10 stock_is "$sku" 3 || true
  wait_for "order cancelled by the saga timeout" $(( saga_timeout + 40 )) status_is "$customer" "$order_id" CANCELLED || return 0
  [ "$(order_reason "$customer" "$order_id")" = saga_timeout ] && say "ok   cancel reason is saga_timeout" || fail "cancel reason is not saga_timeout"
  wait_for "stock released (5 again)" 20 stock_is "$sku" 5 || true
  docker compose start payments payments-worker >/dev/null
  wait_for "payments back: the queued charge is refunded, not kept" 90 payment_is "$customer" "$order_id" REFUNDED || true
  [ "$(order_status "$customer" "$order_id")" = CANCELLED ] && say "ok   the order stays cancelled" || fail "the order did not stay cancelled"
  second="$(place_order "$customer" "$sku" payments-2)"
  [ "$second" = 202 ] || fail "new order answered HTTP $second"
  new_id="$(body | field id)"
  wait_for "a new order is confirmed" 60 status_is "$customer" "$new_id" CONFIRMED || true
  wait_for "stock taken once (3 left)" 10 stock_is "$sku" 3 || true
}

profile_has_email() { http GET /api/v1/accounts/me "$1" >/dev/null; [ "$(body | field email)" = "$2" ]; }

registration_events() {
  docker compose exec -T kafka /opt/kafka/bin/kafka-console-consumer.sh \
    --bootstrap-server kafka:9092 --topic auth.events --from-beginning --timeout-ms 8000 2>/dev/null \
    | grep -c "\"$1\"" || true
}

registration_published() { [ "$(registration_events "$1")" -ge 1 ]; }

kafka_scenario() {
  say "== Kafka stopped during a registration and an order"
  admin="$(admin_token)"; customer="$(customer_token)"
  sku="$(create_product kafka "$admin")"
  docker compose stop kafka >/dev/null
  email="scenario-$run_id@example.com"
  code="$(http POST /api/v1/auth/register "" "{\"email\":\"$email\",\"password\":\"scenario-pass-$run_id-xyz\"}")"
  [ "$code" = 201 ] && say "ok   registration accepted while Kafka is down (HTTP $code)" || fail "registration answered HTTP $code"
  login="$(http POST /api/v1/auth/login "" "{\"email\":\"$email\",\"password\":\"scenario-pass-$run_id-xyz\"}")"
  new_token="$(body | field access_token)"
  [ "$login" = 200 ] || fail "login answered HTTP $login"
  code="$(place_order "$customer" "$sku" kafka-1)"
  [ "$code" = 202 ] && say "ok   order accepted while Kafka is down (HTTP $code)" || fail "order answered HTTP $code"
  order_id="$(body | field id)"
  sleep "$kafka_outage_seconds"
  [ "$(order_status "$customer" "$order_id")" = PENDING ] && say "ok   the order waits as PENDING, its event is in the outbox" || fail "the order is not PENDING during the outage"
  docker compose start kafka >/dev/null
  wait_for "the order completes after Kafka returns" 150 status_is "$customer" "$order_id" CONFIRMED || true
  wait_for "user.registered reached auth.events after the restart" 150 registration_published "$email" || true
  say "info user.registered copies in auth.events: $(registration_events "$email") (the relay is at least once; consumers skip repeats)"
  wait_for "the new user has a profile in accounts" 60 profile_has_email "$new_token" "$email" || true
  wait_for "stock taken exactly once (3 left)" 10 stock_is "$sku" 3 || true
}

case "$scenario" in
  payments) payments_scenario ;;
  kafka) kafka_scenario ;;
  all) payments_scenario; kafka_scenario ;;
  *) say "usage: $0 [payments|kafka|all]" >&2; exit 2 ;;
esac

exit "$failed"
