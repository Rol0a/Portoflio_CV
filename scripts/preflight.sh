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

# CLOUDFLARE_TUNNEL_TOKEN is deliberately absent: the public path is Tailscale
# Funnel, and the cloudflared service is profile-gated in docker-compose.yml.
# It is only required when running `docker compose --profile cloudflare up`,
# which is checked separately in the Public ingress section below.
for var in POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB DATABASE_URL \
           SESSION_SECRET_KEY ADMIN_USERNAME ADMIN_PASSWORD \
           DOMAIN TAILSCALE_IP NOC_DB_PASSWORD; do
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
elif [[ "${DOMAIN}" == *trycloudflare.com ]]; then
  fail "DOMAIN is a quick-tunnel hostname (${DOMAIN}) — it changes every time the tunnel restarts, so anything pinned to it breaks silently (docs/CLAUDE.md §4)"
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
# CONTACT_TO_EMAIL and SMTP_USERNAME are deliberately NOT in this list. On a
# CV site the owner's contact address is published on purpose — it is in
# frontend/src/config/profile.ts, the i18n bundles and the README because
# recruiters are meant to read it. Treating it as a leaked secret produced a
# FAIL on every run, and a check that always fails is a check nobody reads.
#
# What actually protects that mailbox is the Gmail App Password
# (SMTP_PASSWORD), which IS checked below. The address being public is a
# scraping/spam trade-off the owner already accepted by putting a CV online;
# it is not a credential. See the separate advisory further down.
leaked=""
for secret in "${SMTP_PASSWORD:-}" "${CLOUDFLARE_TUNNEL_TOKEN:-}" "${POSTGRES_PASSWORD:-}" "${NOC_DB_PASSWORD:-}" "${SESSION_SECRET_KEY:-}" "${ADMIN_PASSWORD:-}" "${ADMIN_ENTRY_TOKEN:-}"; do
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

# Advisory, not a failure: the address is published by design (see above), but
# it is worth knowing that it is in the built bundle where scrapers find it.
if [[ -n "${CONTACT_TO_EMAIL:-}" ]] && grep -rqs --exclude-dir=node_modules --exclude-dir=.git \
     --fixed-strings "$CONTACT_TO_EMAIL" frontend/src 2>/dev/null; then
  warn "CONTACT_TO_EMAIL is hardcoded in frontend/src — it ships in the public bundle and will be scraped. Intended on a CV site; if not, remove it and let the contact form relay instead."
fi

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
  # Two host bindings are legitimate: the tailnet address (admin site) and
  # loopback (the public site, reached only by `tailscale funnel` running on
  # the host). Anything else — above all a bare 0.0.0.0 — puts a service on
  # the home LAN, which is the failure this whole exposure model exists to
  # prevent.
  bad_bind=$(grep -E '^\s+host_ip:' <<<"$rendered" \
    | grep -v "${TAILSCALE_IP:-__unset__}" | grep -v '127\.0\.0\.1')
  if [[ -n "$bad_bind" ]]; then
    fail "a port is published somewhere other than ${TAILSCALE_IP:-the tailnet address} or loopback:"
    sed 's/^/          /' <<<"$bad_bind"
  else
    pass "every published port is tailnet-only or loopback-only"
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

# --- Defence in depth ------------------------------------------------------
# The deny rules above are the primary control; the backend's exposure guard
# is the second lock behind them (backend/app/middleware/exposure.py). Both
# halves have to be present, and a check that only looked at one would report
# a single point of failure as healthy.
section "Defence in depth"

grep -q "header_up X-Portfolio-Entry public" infrastructure/caddy/Caddyfile \
  && pass "Caddy marks public-block requests as publicly entered" \
  || fail "the public block does not stamp X-Portfolio-Entry — the backend guard cannot tell where a request entered"

grep -q "header_up X-Portfolio-Entry {\$ADMIN_ENTRY_TOKEN" infrastructure/caddy/Caddyfile \
  && pass "Caddy stamps the admin marker on the admin block" \
  || fail "the admin block does not stamp X-Portfolio-Entry — admin requests would be refused by the backend guard"

grep -q "ExposureGuardMiddleware" backend/app/main.py \
  && pass "the backend wires its exposure guard" \
  || fail "ExposureGuardMiddleware is not wired in backend/app/main.py — Caddy is the only thing protecting the admin surface"

if [[ -z "${ADMIN_ENTRY_TOKEN:-}" ]]; then
  warn "ADMIN_ENTRY_TOKEN is unset — the entry marker falls back to the guessable literal 'admin'. Generate one: openssl rand -hex 32"
elif [[ ${#ADMIN_ENTRY_TOKEN} -lt 16 ]]; then
  warn "ADMIN_ENTRY_TOKEN is only ${#ADMIN_ENTRY_TOKEN} chars — use 64 (openssl rand -hex 32)"
else
  pass "ADMIN_ENTRY_TOKEN is set to a non-trivial value"
fi

grep -q "sanitize_metadata" backend/app/schemas/analytics.py \
  && pass "analytics metadata is allowlisted server-side (performance fields only)" \
  || fail "backend/app/schemas/analytics.py has no allowlist — the public beacon accepts arbitrary JSON into the database"

# --- Host ------------------------------------------------------------------
section "Host"

for tool in docker restic; do
  command -v "$tool" >/dev/null && pass "$tool installed" || warn "$tool not installed"
done

if command -v ufw >/dev/null; then
  ufw_status=$(sudo -n ufw status verbose 2>/dev/null)
  if grep -q "Status: active" <<<"$ufw_status"; then
    pass "ufw is active"

    grep -qE '^(80|443)/tcp\s+ALLOW' <<<"$ufw_status" \
      && fail "ufw allows 80/443 inbound — the tunnel makes that unnecessary (security.md §4)" \
      || pass "ufw does not open 80/443"

    grep -q "Default: deny (incoming)" <<<"$ufw_status" \
      && pass "ufw default policy is deny incoming" \
      || fail "ufw's default incoming policy is not deny (security.md §4)"

    # security.md §3/§4: SSH is supposed to be reachable over Tailscale only.
    # An interface-scoped rule shows the interface in the "To" column
    # ("22/tcp on tailscale0"); a rule without one is open to every network
    # the host is attached to, which on this machine includes the LAN.
    # Both spellings: `ufw status` names the rule by app profile ("SSH"),
    # `status verbose` by port ("22/tcp (SSH)"). Matching only one would
    # report an exposed port as closed.
    ssh_open=$(grep -E '^(22(/tcp)?|SSH)[[:space:](]' <<<"$ufw_status" | grep -v 'tailscale0' | grep 'ALLOW')
    if [[ -n "$ssh_open" ]]; then
      fail "ufw allows SSH from outside the tailnet — security.md §4 restricts it to tailscale0:"
      sed 's/^/          /' <<<"$ssh_open"
      echo "          fix with: scripts/harden_host.sh --apply   (read it first)"
    else
      pass "SSH is not open beyond the tailnet"
    fi
  else
    warn "ufw is not active (or needs sudo) — see docs/deployment.md §1.3"
  fi

  # The IPv6 leak docs/security.md §2 singles out. ufw's default-deny only
  # covers IPv6 when ufw is managing IPv6 at all; with IPV6=no the v6 stack is
  # unfiltered, and this host has a globally-routable delegated prefix, so
  # "inbound is denied" would be false in exactly the way that matters most.
  if [[ -r /etc/default/ufw ]]; then
    grep -qi '^IPV6=yes' /etc/default/ufw \
      && pass "ufw manages IPv6 (so default-deny covers inbound v6)" \
      || fail "IPV6 is not enabled in /etc/default/ufw — inbound IPv6 bypasses ufw entirely (security.md §2)"
  else
    warn "cannot read /etc/default/ufw — confirm IPV6=yes by hand (security.md §2)"
  fi
else
  warn "ufw not installed — see docs/deployment.md §1.3"
fi

# security.md §6. Behind the Caddy denies and the exposure guard this is a
# third layer, not the front line — but it is the only one that reacts to a
# sustained attempt rather than just refusing each request in isolation.
if systemctl is-active --quiet fail2ban 2>/dev/null; then
  pass "fail2ban is running"
else
  warn "fail2ban is not running — security.md §6 wants it on SSH and the admin login endpoint"
fi

# --- Public ingress --------------------------------------------------------
# The public path is Tailscale Funnel: free, no domain required, outbound-only,
# and the home IP is never published (docs/security.md §2). The checks below
# are ordered by how badly each failure hurts.
section "Public ingress (Tailscale Funnel)"

if ! command -v tailscale >/dev/null; then
  fail "tailscale is not installed — there is no public path at all"
else
  funnel_status=$(tailscale funnel status 2>&1)

  if grep -q "Funnel on" <<<"$funnel_status"; then
    pass "Funnel is on"
  else
    fail "Funnel is NOT on — the site is unreachable from the internet. Run: make funnel"
  fi

  # THE critical check. Funnel supports 443, 8443 and 10000, and the admin site
  # is bound to 8443. Funnelling 8443 would publish the admin dashboard to the
  # entire internet — the single worst misconfiguration available here, and one
  # that leaves every other control in this document intact and irrelevant.
  if grep -qE ':8443|:10000' <<<"$funnel_status"; then
    fail "Funnel is serving a port other than 443. If that is 8443 the ADMIN SITE IS PUBLIC. Fix now: tailscale funnel --https=8443 off"
    sed 's/^/          /' <<<"$funnel_status"
  else
    pass "Funnel serves 443 only — the admin site on 8443 is not published"
  fi

  # Caddy's public block matches on $DOMAIN. If Funnel's hostname and DOMAIN
  # disagree, every public request falls through to the catch-all and the whole
  # site answers 404 while every container still reports healthy.
  ts_host=$(tailscale status --json 2>/dev/null \
    | python3 -c "import json,sys; print(json.load(sys.stdin).get('Self',{}).get('DNSName','').rstrip('.'))" 2>/dev/null)
  if [[ -z "$ts_host" ]]; then
    warn "could not read this node's tailnet DNS name — cannot confirm DOMAIN matches Funnel"
  elif [[ "$DOMAIN" == "$ts_host" ]]; then
    pass "DOMAIN matches the Funnel hostname ($ts_host)"
  else
    fail "DOMAIN ($DOMAIN) != the Funnel hostname ($ts_host) — Caddy's public block would never match, so every public request 404s"
  fi

  # Funnel runs on the host and forwards to a host port; that port is published
  # by the caddy service on loopback only.
  if grep -q '127.0.0.1:8080' <<<"$funnel_status"; then
    pass "Funnel forwards to the loopback-published Caddy port"
  else
    warn "Funnel's target is not 127.0.0.1:8080 — confirm it points at Caddy's public block"
    sed 's/^/          /' <<<"$funnel_status"
  fi
fi

# A quick tunnel alongside Funnel means two public front doors, one of them
# ephemeral and unmonitored.
if docker ps --no-trunc --format '{{.Names}} {{.Command}}' 2>/dev/null | grep -qi 'trycloudflare\|--url'; then
  fail "a Cloudflare QUICK tunnel is still running — a second, ephemeral public entrance. Remove it: docker rm -f portfolio-quicktunnel"
else
  pass "no quick tunnel is running"
fi

if docker ps --format '{{.Names}}' 2>/dev/null | grep -q cloudflared; then
  if [[ -z "${CLOUDFLARE_TUNNEL_TOKEN:-}" ]]; then
    fail "the cloudflared service is running with an empty CLOUDFLARE_TUNNEL_TOKEN — it will crashloop"
  else
    pass "cloudflared is running with a token set"
  fi
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
