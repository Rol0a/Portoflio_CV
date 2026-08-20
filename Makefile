.PHONY: dev dev-build dev-down dev-logs backend-shell frontend-shell db-shell db-migrate db-migration db-seed test noc-role noc-role-prod preflight harden harden-apply funnel funnel-status funnel-off check-smtp prod-up prod-down prod-logs tunnel-status

dev:
	docker compose -f docker-compose.dev.yml up

dev-build:
	docker compose -f docker-compose.dev.yml up --build

dev-down:
	docker compose -f docker-compose.dev.yml down

dev-logs:
	docker compose -f docker-compose.dev.yml logs -f

backend-shell:
	docker compose -f docker-compose.dev.yml exec backend bash

frontend-shell:
	docker compose -f docker-compose.dev.yml exec frontend sh

db-shell:
	docker compose -f docker-compose.dev.yml exec postgres psql -U $${POSTGRES_USER:-portfolio} -d $${POSTGRES_DB:-portfolio}

db-migrate:
	docker compose -f docker-compose.dev.yml exec backend alembic upgrade head

db-migration:
	docker compose -f docker-compose.dev.yml exec backend alembic revision --autogenerate -m "$(m)"

db-seed:
	docker compose -f docker-compose.dev.yml exec backend python -m scripts.seed

test:
	docker compose -f docker-compose.dev.yml exec backend pytest
	docker compose -f docker-compose.dev.yml exec frontend npm run test

# Create (or rotate the password of) the least-privilege noc_writer role.
# Idempotent — see scripts/create_noc_role.sql. Requires NOC_DB_PASSWORD.
noc-role:
	@test -n "$${NOC_DB_PASSWORD:-}" || { echo "NOC_DB_PASSWORD is not set (see .env.example)"; exit 1; }
	docker compose -f docker-compose.dev.yml exec -T postgres psql -U $${POSTGRES_USER:-portfolio} -d $${POSTGRES_DB:-portfolio} \
		-v noc_password="$$NOC_DB_PASSWORD" -v db_name=$${POSTGRES_DB:-portfolio} < scripts/create_noc_role.sql

noc-role-prod:
	@test -n "$${NOC_DB_PASSWORD:-}" || { echo "NOC_DB_PASSWORD is not set (see .env.example)"; exit 1; }
	docker compose exec -T postgres psql -U $${POSTGRES_USER:-portfolio} -d $${POSTGRES_DB:-portfolio} \
		-v noc_password="$$NOC_DB_PASSWORD" -v db_name=$${POSTGRES_DB:-portfolio} < scripts/create_noc_role.sql

# --- Deployment (production stack; see docs/deployment.md) -------------------

# Configuration and exposure checks. Run before every deploy.
preflight:
	./scripts/preflight.sh

# Show what host hardening (docs/security.md §4, §6) would change. Read-only.
harden:
	./scripts/harden_host.sh

# Apply it. Prompts before removing any SSH rule, because one of them may be
# the rule your current session is using — reconnect over Tailscale after.
harden-apply:
	./scripts/harden_host.sh --apply

# Verify the contact relay's Gmail App Password without emailing anyone.
# Add ARGS=--send to deliver one test message to CONTACT_TO_EMAIL.
check-smtp:
	docker compose exec -T backend python -m scripts.check_smtp $(ARGS)

prod-up:
	docker compose up -d
	docker compose ps

prod-down:
	docker compose down

prod-logs:
	docker compose logs -f --tail=100

# --- Public ingress (Tailscale Funnel) --------------------------------------
# Funnel is the public path: free, no domain, outbound-only, home IP never
# published. It forwards to Caddy's public block, which docker-compose.yml
# publishes on loopback only. See docs/security.md §2.
#
# ONLY ever 443. Funnel also supports 8443, which is the admin site's port —
# funnelling that would publish the admin dashboard to the internet.
# scripts/preflight.sh fails loudly if that ever happens.
funnel:
	tailscale funnel --bg --https=443 http://127.0.0.1:8080
	@$(MAKE) --no-print-directory funnel-status

funnel-status:
	@tailscale funnel status

funnel-off:
	tailscale funnel --https=443 off

# Cloudflare path — only meaningful under the `cloudflare` compose profile,
# which is not the default. Kept for the day a real domain exists.
tunnel-status:
	docker compose exec -T cloudflared cloudflared tunnel ready && echo "tunnel: READY"
	docker compose ps cloudflared
