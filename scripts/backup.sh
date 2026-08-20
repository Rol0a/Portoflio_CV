#!/usr/bin/env bash
#
# PostgreSQL backup via restic (M16; tool chosen in docs/security.md §10).
#
# restic encrypts client-side, so the backup destination never sees plaintext —
# which is what makes an off-site or cheap-storage target acceptable for a
# database holding admin password hashes and session tokens.
#
# Usage:
#   scripts/backup.sh                 # dump, back up, prune
#   scripts/backup.sh --no-prune      # keep every snapshot
#
# Requires in the environment (or .env):
#   RESTIC_REPOSITORY      e.g. /mnt/backup/portfolio, or s3:..., sftp:...
#   RESTIC_PASSWORD_FILE   path to a file containing the repo password (chmod 600)
#   POSTGRES_USER, POSTGRES_DB
#
# Cron (nightly, per docs/security.md §10):
#   0 3 * * * cd /srv/portfolio && ./scripts/backup.sh >> /var/log/portfolio-backup.log 2>&1
#
# NOTE: .env is deliberately NOT included here. It holds the SMTP app password,
# the session secret and the database password — restoring a database is
# useless without it, but it is a different class of secret and belongs in a
# separate, `age`-encrypted copy (docs/security.md §8). Backing it up into the
# same repository would put every secret behind one password.

set -euo pipefail

PRUNE=1
[[ "${1:-}" == "--no-prune" ]] && PRUNE=0

cd "$(dirname "$0")/.."
[[ -f .env ]] && set -a && . ./.env && set +a

: "${RESTIC_REPOSITORY:?set RESTIC_REPOSITORY (see docs/security.md §10)}"
: "${RESTIC_PASSWORD_FILE:?set RESTIC_PASSWORD_FILE}"
: "${POSTGRES_USER:?}"
: "${POSTGRES_DB:?}"
export RESTIC_REPOSITORY RESTIC_PASSWORD_FILE

command -v restic >/dev/null || { echo "restic is not installed" >&2; exit 1; }

# Initialise on first run; harmless afterwards.
restic snapshots >/dev/null 2>&1 || {
  echo "==> initialising restic repository at $RESTIC_REPOSITORY"
  restic init
}

COMPOSE="docker compose"
[[ -f docker-compose.yml ]] || COMPOSE="docker compose -f docker-compose.dev.yml"

echo "==> dumping $POSTGRES_DB"
# Streamed straight into restic: no plaintext dump ever lands on disk, and
# nothing needs cleaning up if this fails partway.
# pipefail is set, so a pg_dump failure fails the whole pipeline rather than
# silently storing a truncated dump.
$COMPOSE exec -T postgres pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists \
  | restic backup --stdin --stdin-filename postgres.sql --tag portfolio --tag postgres

if [[ $PRUNE -eq 1 ]]; then
  echo "==> pruning old snapshots"
  restic forget --tag portfolio --keep-daily 7 --keep-weekly 4 --keep-monthly 6 --prune
fi

echo "==> verifying repository integrity"
restic check --read-data-subset=5%

echo "==> current snapshots"
restic snapshots --tag portfolio --compact

cat <<'EOF'

Done. A backup you have never restored is a hypothesis, not a backup —
run scripts/restore.sh against a throwaway database to test it.
EOF
