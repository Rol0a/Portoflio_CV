#!/usr/bin/env bash
#
# Renews the Tailscale-issued TLS cert for the admin site (:8443).
#
#   scripts/renew_admin_cert.sh
#
# `tailscale cert` re-issues unconditionally on every call (it doesn't check
# local expiry first — Tailscale's own backend decides whether a fresh cert
# is actually needed), so this is safe to run on a schedule regardless of
# how close to expiry the current one is. Caddy is reloaded (not restarted)
# so the new cert takes effect with no connection drop on the public site,
# which shares this container.
set -euo pipefail
cd "$(dirname "$0")/.."

DOMAIN=$(tailscale status --json | python3 -c \
  "import json,sys; print(json.load(sys.stdin)['Self']['DNSName'].rstrip('.'))")

sudo tailscale cert \
  --cert-file infrastructure/caddy/certs/admin.crt \
  --key-file infrastructure/caddy/certs/admin.key \
  "$DOMAIN"

docker compose exec -T caddy caddy reload --config /etc/caddy/Caddyfile

echo "renewed admin cert for $DOMAIN, caddy reloaded"
