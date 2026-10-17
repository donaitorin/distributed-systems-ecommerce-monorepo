#!/bin/sh
set -eu

cd "$(dirname "$0")/.."

topics="orders.events inventory.events payments.events catalog.events imports.jobs auth.events"
run_id="check-$(date +%s)"
timeout_seconds="${DLQ_CHECK_TIMEOUT_SECONDS:-60}"
failed=0

for topic in $topics; do
  printf '%s:{"not":"an event","run":"%s"}\n' "$run_id-$topic" "$run_id" \
    | docker compose exec -T kafka /opt/kafka/bin/kafka-console-producer.sh \
        --bootstrap-server kafka:9092 --topic "$topic" \
        --property parse.key=true --property key.separator=: >/dev/null
done

deadline=$(( $(date +%s) + timeout_seconds ))
for topic in $topics; do
  while :; do
    if docker compose run --rm --no-deps -T orders-worker \
        python -m ecommerce_messaging.dlq_cli inspect "$topic.dlq" 2>/dev/null \
        | grep -q "\"key\": \"$run_id-$topic\""; then
      echo "ok   $topic.dlq received the malformed message"
      break
    fi
    if [ "$(date +%s)" -ge "$deadline" ]; then
      echo "FAIL $topic.dlq did not receive the malformed message within ${timeout_seconds}s" >&2
      failed=1
      break
    fi
    sleep 2
  done
done

exit "$failed"
