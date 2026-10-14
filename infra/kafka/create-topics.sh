#!/bin/sh
set -eu

BOOTSTRAP_SERVER="${KAFKA_BOOTSTRAP_SERVER:-kafka:9092}"
PARTITIONS="${KAFKA_TOPIC_PARTITIONS:-6}"
TOPICS="orders.events inventory.events payments.events catalog.events imports.jobs auth.events"

create_topic() {
  /opt/kafka/bin/kafka-topics.sh --bootstrap-server "$BOOTSTRAP_SERVER" \
    --create --if-not-exists --topic "$1" \
    --partitions "$PARTITIONS" --replication-factor 1
}

for topic in $TOPICS; do
  create_topic "$topic"
  create_topic "$topic.dlq"
done
