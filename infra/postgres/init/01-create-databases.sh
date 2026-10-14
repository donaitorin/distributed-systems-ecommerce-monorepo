#!/bin/sh
set -eu

create_service_database() {
  service="$1"
  password="$2"
  psql -v ON_ERROR_STOP=1 \
    -v role="${service}_user" -v database="${service}_db" -v password="$password" \
    --username "$POSTGRES_USER" --dbname postgres <<'SQL'
CREATE ROLE :"role" LOGIN PASSWORD :'password';
CREATE DATABASE :"database" OWNER :"role";
REVOKE ALL ON DATABASE :"database" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"database" TO :"role";
SQL
}

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<'SQL'
REVOKE CONNECT ON DATABASE postgres FROM PUBLIC;
REVOKE CONNECT ON DATABASE template1 FROM PUBLIC;
SQL

create_service_database auth "$AUTH_DB_PASSWORD"
create_service_database accounts "$ACCOUNTS_DB_PASSWORD"
create_service_database catalog "$CATALOG_DB_PASSWORD"
create_service_database orders "$ORDERS_DB_PASSWORD"
create_service_database payments "$PAYMENTS_DB_PASSWORD"
