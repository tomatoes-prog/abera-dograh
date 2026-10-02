#!/bin/sh
# Offline smoke check: isolated local PostgreSQL and pgvector backup/restore.
set -eu
for tool in gcc g++ make git; do
    if command -v "$tool"; then
        echo "Build tool leaked into runtime: $tool" >&2
        exit 1
    fi
done
initdb -D /tmp/review-pg > /tmp/init.log
pg_ctl -D /tmp/review-pg -o "-k /tmp -p 55432" -l /tmp/pg.log start
trap 'pg_ctl -D /tmp/review-pg stop' EXIT
psql -h /tmp -p 55432 -d postgres -v ON_ERROR_STOP=1 <<'SQL'
CREATE EXTENSION vector;
CREATE TABLE review (value vector(2));
INSERT INTO review VALUES ('[1,2]');
SQL
pg_dump -h /tmp -p 55432 -d postgres -Fc -f /tmp/backup.dump
createdb -h /tmp -p 55432 restored
pg_restore -h /tmp -p 55432 -d restored --exit-on-error /tmp/backup.dump
test "$(psql -h /tmp -p 55432 -d restored -Atc 'SELECT count(*) FROM review')" = 1
echo "Admin runtime passed: pgvector, backup, restore, no build tools"
