#!/usr/bin/env bash
#
# Pre-deployment checks for the production stack (docs/deployment.md §4).
#
#   scripts/preflight.sh
#
# Reads .env and the rendered compose config and reports anything that would
# break, leak, or silently degrade once the tunnel is live. Every check exists
# because the corresponding mistake is either easy to make or invisible after
# the fact — a default password still in place, the admin port bound to
# 0.0.0.0, a dev API URL baked into the production bundle.
#
# Exits non-zero if any FAIL. Warnings do not block, but read them.
#
# Safe to run repeatedly; it changes nothing.

# No `set -u`: reporting unset variables is this script's job, so tripping
# over them would defeat it.
set -o pipefail
cd "$(dirname "$0")/.."

PASS=0 FAIL=0 WARN=0
pass() { printf '  \033[32mPASS\033[0m  %s\n' "$1"; PASS=$((PASS+1)); }
fail() { printf '  \033[31mFAIL\033[0m  %s\n' "$1"; FAIL=$((FAIL+1)); }
warn() { printf '  \033[33mWARN\033[0m  %s\n' "$1"; WARN=$((WARN+1)); }
section() { printf '\n\033[1m%s\033[0m\n' "$1"; }

# --- .env ------------------------------------------------------------------
section "Configuration"

if [[ ! -f .env ]]; then
  fail ".env does not exist — copy .env.example and fill it in"
  echo; echo "Cannot continue without .env."; exit 1
fi
pass ".env exists"

perms=$(stat -c '%a' .env)
[[ "$perms" == "600" ]] && pass ".env is chmod 600" \
  || warn ".env is chmod $perms — should be 600 (docs/security.md §8)"

set -a; . ./.env; set +a

require() {
  local name="$1" value="${!1:-}"
  [[ -n "$value" ]] && pass "$name is set" || fail "$name is empty"
}

reject_default() {
  local name="$1" value="${!1:-}" bad="$2"
  if [[ "$value" == "$bad" ]]; then
    fail "$name is still the example value ('$bad') — generate a real one"
  fi
}

for var in POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB DATABASE_URL \
           SESSION_SECRET_KEY ADMIN_USERNAME ADMIN_PASSWORD \
           DOMAIN CLOUDFLARE_TUNNEL_TOKEN TAILSCALE_IP NOC_DB_PASSWORD; do
  require "$var"
done

reject_default POSTGRES_PASSWORD "changeme"
reject_default ADMIN_PASSWORD "changeme"
reject_default SESSION_SECRET_KEY "changeme-random-64-char-string"
reject_default SESSION_SECRET_KEY "dev-secret-change-me"

if [[ -n "${SESSION_SECRET_KEY:-}" && ${#SESSION_SECRET_KEY} -lt 32 ]]; then
  fail "SESSION_SECRET_KEY is only ${#SESSION_SECRET_KEY} chars — use 64 (openssl rand -hex 32)"
fi

# --- Network identity ------------------------------------------------------
section "Network identity"

if [[ -z "${DOMAIN:-}" ]]; then
  fail "DOMAIN is empty — the public Caddy site block matches on it"
elif [[ "${DOMAIN}" == *example.com ]]; then
  fail "DOMAIN is still a placeholder (${DOMAIN})"
else
  pass "DOMAIN is ${DOMAIN}"
fi

if [[ "${TAILSCALE_IP:-}" =~ ^100\.([0-9]{1,3}\.){2}[0-9]{1,3}$ ]]; then
  pass "TAILSCALE_IP looks like a tailnet address ($TAILSCALE_IP)"
  if command -v tailscale >/dev/null; then
    actual=$(tailscale ip -4 2>/dev/null | head -1)
    [[ "$actual" == "$TAILSCALE_IP" ]] \
      && pass "TAILSCALE_IP matches this host's current address" \
      || fail "TAILSCALE_IP ($TAILSCALE_IP) != this host's address ($actual) — the admin site would bind to the wrong IP or fail to start"
  else
    warn "tailscale not installed — cannot confirm TAILSCALE_IP is this host"
  fi
else
  fail "TAILSCALE_IP is not a 100.x.y.z address ('${TAILSCALE_IP:-}') — run: tailscale ip -4"
fi

# --- Contact relay ---------------------------------------------------------
section "Contact form relay"

if [[ -z "${CONTACT_TO_EMAIL:-}" ]]; then
  warn "CONTACT_TO_EMAIL is empty — the contact form will return 503 (by design)"
else
  pass "CONTACT_TO_EMAIL is set"
  [[ -n "${SMTP_USERNAME:-}" ]] && pass "SMTP_USERNAME is set" || fail "SMTP_USERNAME is empty"
  if [[ -z "${SMTP_PASSWORD:-}" ]]; then
    fail "SMTP_PASSWORD is empty — every submission will 502. Generate a Gmail App Password."
  elif [[ "$SMTP_PASSWORD" == *" "* ]]; then
    fail "SMTP_PASSWORD contains spaces — store the 16 App Password characters unspaced"
  elif [[ "${SMTP_HOST:-}" == *gmail.com && ${#SMTP_PASSWORD} -ne 16 ]]; then
    warn "SMTP_PASSWORD is ${#SMTP_PASSWORD} chars; Gmail App Passwords are 16"
  else
    pass "SMTP_PASSWORD looks well-formed"
  fi
  echo "        verify for real: docker compose exec backend python -m scripts.check_smtp"
fi

# --- Secret containment ----------------------------------------------------
section "Secret containment"

if git check-ignore -q .env 2>/dev/null; then
  pass ".env is gitignored"
else
  fail ".env is NOT gitignored — it holds every secret"
fi

if git ls-files --error-unmatch .env >/dev/null 2>&1; then
  fail ".env is TRACKED BY GIT — remove it from the index immediately"
else
  pass ".env is not tracked by git"
fi

# Short or placeholder values are skipped: "changeme" legitimately appears in
# .env.example, and matching it would report a leak on every fresh checkout.
# Real secrets are long, so a length floor separates the two reliably.
leaked=""
for secret in "${CONTACT_TO_EMAIL:-}" "${SMTP_PASSWORD:-}" "${CLOUDFLARE_TUNNEL_TOKEN:-}" "${POSTGRES_PASSWORD:-}" "${NOC_DB_PASSWORD:-}"; do
  [[ ${#secret} -lt 12 ]] && continue
  case "$secret" in changeme*|dev-*|*example.com) continue ;; esac
  hits=$(grep -rl --exclude-dir=node_modules --exclude-dir=.git --exclude=.env \
           --fixed-strings "$secret" . 2>/dev/null)
  if [[ -n "$hits" ]]; then
    leaked="yes"
    fail "a value from .env appears outside it, in:"
    sed 's/^/          /' <<<"$hits"
  fi
done
[[ -z "$leaked" ]] && pass "no .env secret appears elsewhere in the repo"

# --- Compose ---------------------------------------------------------------
section "Production compose"

if ! docker compose -f docker-compose.yml config >/dev/null 2>&1; then
  fail "docker-compose.yml does not render — run: docker compose config"
else
  pass "docker-compose.yml renders"
  rendered=$(docker compose -f docker-compose.yml config 2>/dev/null)

  # Only `host_ip:` lines describe published bindings; matching 0.0.0.0
  # anywhere in the rendered file would also hit TUNNEL_METRICS, which is an
  # in-network listen address and not published at all.
  bad_bind=$(grep -E '^\s+host_ip:' <<<"$rendered" | grep -v "${TAILSCALE_IP:-__unset__}")
  if [[ -n "$bad_bind" ]]; then
    fail "a port is published somewhere other than ${TAILSCALE_IP:-the tailnet address}:"
    sed 's/^/          /' <<<"$bad_bind"
  else
    pass "no service publishes to 0.0.0.0"
  fi

  if grep -q "host_ip: ${TAILSCALE_IP}" <<<"$rendered"; then
    pass "the admin port is bound to the Tailscale address only"
  else
    fail "the admin port is not bound to ${TAILSCALE_IP}"
  fi

  if grep -qE 'VITE_API_URL: (""|null)' <<<"$rendered"; then
    pass "the frontend build arg VITE_API_URL is empty (same-origin)"
  else
    warn "check VITE_API_URL in the frontend build args — it must be empty in production"
  fi

  grep -q 'published: "5432"' <<<"$rendered" \
    && fail "Postgres publishes a port in production" \
    || pass "Postgres publishes no port"
fi

# --- Caddy -----------------------------------------------------------------
section "Reverse proxy"

if command -v docker >/dev/null; then
  if docker run --rm -e DOMAIN="${DOMAIN:-portfolio.example.com}" \
      -v "$PWD/infrastructure/caddy/Caddyfile:/etc/caddy/Caddyfile:ro" \
      caddy:2-alpine caddy validate --config /etc/caddy/Caddyfile >/dev/null 2>&1; then
    pass "Caddyfile validates"
  else
    fail "Caddyfile does not validate"
  fi
fi

for path in "/internal/*" "/api/v1/admin/*" "/api/v1/auth/*" "/admin*"; do
  grep -q -- "handle ${path}" infrastructure/caddy/Caddyfile \
    && pass "public block denies ${path}" \
    || fail "public block is missing the deny for ${path}"
done

# --- Host ------------------------------------------------------------------
section "Host"

for tool in docker restic; do
  command -v "$tool" >/dev/null && pass "$tool installed" || warn "$tool not installed"
done

if command -v ufw >/dev/null; then
  if sudo -n ufw status 2>/dev/null | grep -q "Status: active"; then
    pass "ufw is active"
    sudo -n ufw status 2>/dev/null | grep -qE '^(80|443)/tcp\s+ALLOW' \
      && fail "ufw allows 80/443 inbound — the tunnel makes that unnecessary (security.md §4)" \
      || pass "ufw does not open 80/443"
  else
    warn "ufw is not active (or needs sudo) — see docs/deployment.md §1.3"
  fi
else
  warn "ufw not installed — see docs/deployment.md §1.3"
fi

# --- Summary ---------------------------------------------------------------
printf '\n\033[1mSummary:\033[0m %d passed, %d failed, %d warnings\n' "$PASS" "$FAIL" "$WARN"

if [[ $FAIL -gt 0 ]]; then
  echo
  echo "Not ready to deploy. Fix the failures above, then re-run."
  exit 1
fi

cat <<'EOF'

Configuration checks passed. Still to do by hand, from docs/deployment.md §4:
  - load the site and confirm the webfonts render (a CSP mistake is invisible to curl)
  - confirm two visitors from different networks produce two distinct ip_hash values
  - send a contact message and confirm it arrives with a working Reply-To
  - run scripts/backup.sh, then scripts/restore.sh into a throwaway database
EOF
