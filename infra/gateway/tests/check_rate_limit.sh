#!/usr/bin/env bash
set -u

here=$(cd "$(dirname "$0")" && pwd)
gateway_config="$here/.."
project=(docker compose -f "$here/docker-compose.yml")
failures=0

workdir=$(mktemp -d)
cleanup() {
  "${project[@]}" down --remove-orphans >/dev/null 2>&1
  rm -rf "$workdir"
}
trap cleanup EXIT

proof_dynamic_files=(auth.yml)

mkdir -p "$workdir/dynamic"
sed 's/10\.250\.10\./10.250.20./g' "$gateway_config/traefik.yml" > "$workdir/traefik.yml"
for name in "${proof_dynamic_files[@]}"; do
  sed 's/10\.250\.10\./10.250.20./g' "$gateway_config/dynamic/$name" > "$workdir/dynamic/$name"
done
export PROOF_CONFIG_DIR=$workdir

pass() { printf 'PASS  %s\n' "$1"; }
fail() { printf 'FAIL  %s\n' "$1"; failures=$((failures + 1)); }

run() {
  local container=$1
  shift
  "${project[@]}" exec -T "$container" "$@"
}

address_of() {
  run "$1" hostname -i | tr -d '\r\n'
}

status() {
  local container=$1 path=$2 forwarded=${3:-}
  local args=(-s -o /dev/null -w '%{http_code}' -X POST)
  [ -n "$forwarded" ] && args+=(-H "X-Forwarded-For: $forwarded")
  run "$container" curl "${args[@]}" "http://gateway$path"
}

upstream_forwarded_for() {
  local container=$1 forwarded=${2:-}
  local args=(-s)
  [ -n "$forwarded" ] && args+=(-H "X-Forwarded-For: $forwarded")
  run "$container" curl "${args[@]}" http://gateway/api/v1/auth/echo \
    | tr -d '\r' | awk -F': ' 'tolower($1) == "x-forwarded-for" { print $2 }'
}

count_limited() {
  local container=$1 path=$2 attempts=$3 forwarded=${4:-} limited=0 code
  for _ in $(seq 1 "$attempts"); do
    code=$(status "$container" "$path" "$forwarded")
    [ "$code" = 429 ] && limited=$((limited + 1))
  done
  printf '%s' "$limited"
}

check() {
  local label=$1 expected=$2 actual=$3
  if [ "$expected" = "$actual" ]; then
    pass "$label"
  else
    fail "$label (expected '$expected', got '$actual')"
  fi
}

start_stack() {
  local output="$workdir/up.log" code=0
  echo "+ ${project[*]} up -d --wait"
  "${project[@]}" up -d --wait >"$output" 2>&1 || code=$?
  if [ "$code" -eq 0 ]; then
    return 0
  fi
  echo "could not start the proof stack: 'docker compose up -d --wait' exited with $code"
  echo "--- output of the command"
  cat "$output"
  echo "--- docker version"
  docker version 2>&1 || true
  echo "--- docker compose version"
  docker compose version 2>&1 || true
  echo "--- proof configuration in $workdir"
  ls -l "$workdir" "$workdir/dynamic" 2>&1 || true
  echo "--- docker compose config"
  "${project[@]}" config 2>&1 || true
  echo "--- docker compose ps -a"
  "${project[@]}" ps -a 2>&1 || true
  echo "--- docker compose logs"
  "${project[@]}" logs --no-color --tail=200 2>&1 || true
  exit 2
}

start_stack

login=/api/v1/auth/login
register=/api/v1/auth/register
a_ip=$(address_of client-a)
b_ip=$(address_of client-b)
c_ip=$(address_of client-c)
intruder_ip=$(address_of frontend-intruder)

echo "sources: client-a=$a_ip client-b=$b_ip client-c=$c_ip frontend-intruder=$intruder_ip store-standin=10.250.20.2"
echo
echo "1. Traefik does not accept X-Forwarded-For from untrusted sources"
check "outside client: a spoofed header is replaced by the real source address" "$a_ip" "$(upstream_forwarded_for client-a 6.6.6.6)"
check "outside client: a spoofed chain is replaced as well" "$a_ip" "$(upstream_forwarded_for client-a '6.6.6.6, 7.7.7.7')"
check "outside client without a header: the real address is added" "$a_ip" "$(upstream_forwarded_for client-a)"
check "container on the frontend network that is not store or backoffice is not trusted" "$intruder_ip" "$(upstream_forwarded_for frontend-intruder 6.6.6.6)"

alias_seen=$(run client-a curl -s -H "X_Forwarded_For: 6.6.6.6" http://gateway/api/v1/auth/echo | grep -ci "6.6.6.6")
check "outside client: the underscore alias X_Forwarded_For is deleted before it reaches the backend" 0 "$alias_seen"

echo
echo "2. The store and backoffice hop is trusted and its header is kept"
check "store address: the forwarded client is kept and the hop is appended" "203.0.113.7, 10.250.20.2" "$(upstream_forwarded_for store-standin 203.0.113.7)"

echo
echo "3. Two different clients get separate buckets"
check "client-a: 10 logins pass, the 11th and 12th are limited" 2 "$(count_limited client-a $login 12)"
check "client-b: its first login is not limited by client-a's traffic" 0 "$(count_limited client-b $login 1)"

echo
echo "4. A spoofed header cannot pick or drain a bucket"
check "client-a (already limited) keeps being limited with 5 different spoofed addresses" 5 "$(
  limited=0
  for spoof in 198.51.100.1 198.51.100.2 198.51.100.3 198.51.100.4 198.51.100.5; do
    [ "$(status client-a $login $spoof)" = 429 ] && limited=$((limited + 1))
  done
  printf '%s' "$limited"
)"
check "client-c spoofing client-b's address is limited on its own bucket (11th request on)" 5 "$(count_limited client-c $login 15 "$b_ip")"
check "client-b's bucket was not drained by client-c's spoofing" 0 "$(count_limited client-b $login 5)"

echo
echo "5. Behind the trusted hop the bucket is the forwarded client, not the store"
check "client 203.0.113.7 through the store hop: limited after 10 logins" 2 "$(count_limited store-standin $login 12 203.0.113.7)"
check "client 203.0.113.8 through the same hop has its own bucket" 0 "$(count_limited store-standin $login 5 203.0.113.8)"
check "client 203.0.113.9 spoofing the same chain from an untrusted source stays on the real source's bucket" 0 "$(count_limited frontend-intruder $login 5 203.0.113.7)"

check "store hop without a forwarded address: one shared bucket (degraded, never unlimited)" 2 "$(count_limited store-standin $login 12)"

echo
echo "6. Register has its own, stricter bucket"
check "client-b: 5 registers pass, the 6th is limited" 1 "$(count_limited client-b $register 6)"

if [ "$failures" -gt 0 ]; then
  printf '\n%s check(s) failed\n' "$failures"
  exit 1
fi
printf '\nall rate limit checks passed\n'
