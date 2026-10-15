#!/bin/sh
set -eu

cd "$(dirname "$0")/.."
if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi

gateway="http://127.0.0.1:${GATEWAY_HTTP_PORT:-8000}/api/v1/auth"
role="${ROLE:-admin}"

case "$role" in
  admin)
    email="${AUTH_ADMIN_EMAIL:?AUTH_ADMIN_EMAIL is not set in .env}"
    password="${AUTH_ADMIN_PASSWORD:?AUTH_ADMIN_PASSWORD is not set in .env}"
    ;;
  customer)
    email="${DEV_CUSTOMER_EMAIL:-dev-customer@example.com}"
    password="${DEV_CUSTOMER_PASSWORD:-demo-customer-change-me}"
    ;;
  *)
    echo "ROLE must be admin or customer" >&2
    exit 1
    ;;
esac

output=$(mktemp)
trap 'rm -f "$output"' EXIT

body="{\"email\": \"$email\", \"password\": \"$password\"}"

post() {
  curl -s -o "$output" -w "%{http_code}" -X POST "$gateway/$1" \
    -H "Content-Type: application/json" -d "$body"
}

status=$(post login)
if [ "$status" = "401" ] && [ "$role" = "customer" ]; then
  post register >/dev/null
  status=$(post login)
fi

response=$(cat "$output")

if [ "$status" != "200" ]; then
  echo "login failed with HTTP $status: $response" >&2
  exit 1
fi

printf '%s\n' "$response" | sed -n 's/.*"access_token":"\([^"]*\)".*/\1/p'
