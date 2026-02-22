#!/usr/bin/env bash
set -euo pipefail

DB_HOST=${DB_HOST:-localhost}
DB_PORT=${DB_PORT:-5432}
DB_USER=${DB_USER:-wallet}
DB_PASSWORD=${DB_PASSWORD:-wallet}
DB_NAME=${DB_NAME:-wallet}

export PGPASSWORD="$DB_PASSWORD"

psql "host=$DB_HOST port=$DB_PORT user=$DB_USER dbname=$DB_NAME" -f sql/schema.sql
psql "host=$DB_HOST port=$DB_PORT user=$DB_USER dbname=$DB_NAME" -f sql/seed.sql

echo "Database seeded successfully."

