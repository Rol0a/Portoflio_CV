#!/usr/bin/env bash
#
# Restore a PostgreSQL backup taken by scripts/backup.sh (M16).
#
# Defaults to restoring into a THROWAWAY database rather than the live one,
# because the common reason to run this is to test that backups actually work
# — and a restore script whose easiest path overwrites production is a script
# that will eventually overwrite production.
#
# Usage:
#   scripts/restore.sh                          # latest snapshot -> portfolio_restore_test
#   scripts/restore.sh --snapshot <id>          # a specific snapshot
#   scripts/restore.sh --target mydb            # a different throwaway database
#   scripts/restore.sh --target "$POSTGRES_DB" --i-understand-this-overwrites-live
#
# Requires RESTIC_REPOSITORY and RESTIC_PASSWORD_FILE, as scripts/backup.sh does.

set -euo pipefail

SNAPSHOT="latest"
TARGET=""
ALLOW_LIVE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --snapshot) SNAPSHOT="$2"; shift 2 ;;
    --target) TARGET="$2"; shift 2 ;;
    --i-understand-this-overwrites-live) ALLOW_LIVE=1; shift ;;
    *) echo "unknown argument: $1" >&2; exit 1 ;;
  esac
done

cd "$(dirname "$0")/.."
[[ -f .env ]] && set -a && . ./.env && set +a

: "${RESTIC_REPOSITORY:?set RESTIC_REPOSITORY}"
: "${RESTIC_PASSWORD_FILE:?set RESTIC_PASSWORD_FILE}"
: "${POSTGRES_USER:?}"
: "${POSTGRES_DB:?}"
export RESTIC_REPOSITORY RESTIC_PASSWORD_FILE

TARGET="${TARGET:-${POSTGRES_DB}_restore_test}"

if [[ "$TARGET" == "$POSTGRES_DB" && $ALLOW_LIVE -ne 1 ]]; then
  cat >&2 <<EOF
Refusing to restore over the live database ($POSTGRES_DB).

Restore into a throwaway copy and compare it first:
    scripts/restore.sh
If you really mean to overwrite live data, re-run with
    --target "$POSTGRES_DB" --i-understand-this-overwrites-live
EOF
  exit 1
fi

command -v restic >/dev/null || { echo "restic is not installed" >&2; exit 1; }

COMPOSE="docker compose"
[[ -f docker-compose.yml ]] || COMPOSE="docker compose -f docker-compose.dev.yml"

echo "==> restoring snapshot '$SNAPSHOT' into database '$TARGET'"

# Recreate the target so the restore starts from a known-empty state; the dump
# is taken with --clean --if-exists, but a stray table added since would
# otherwise survive and quietly corrupt the comparison.
$COMPOSE exec -T postgres psql -U "$POSTGRES_USER" -d postgres \
  -c "DROP DATABASE IF EXISTS \"$TARGET\";" \
  -c "CREATE DATABASE \"$TARGET\";"

restic dump "$SNAPSHOT" postgres.sql \
  | $COMPOSE exec -T postgres psql -U "$POSTGRES_USER" -d "$TARGET" -v ON_ERROR_STOP=1 --quiet

echo "==> row counts in the restored database"
$COMPOSE exec -T postgres psql -U "$POSTGRES_USER" -d "$TARGET" -t -c "
SELECT relname, n_live_tup
FROM pg_stat_user_tables
ORDER BY relname;"

cat <<EOF

Restored into '$TARGET'. Compare against the live database before trusting it:

  docker compose exec postgres psql -U $POSTGRES_USER -d $POSTGRES_DB \\
    -c 'SELECT count(*) FROM projects;'
  docker compose exec postgres psql -U $POSTGRES_USER -d $TARGET \\
    -c 'SELECT count(*) FROM projects;'

Drop it when finished:
  docker compose exec postgres psql -U $POSTGRES_USER -d postgres \\
    -c 'DROP DATABASE "$TARGET";'
EOF
