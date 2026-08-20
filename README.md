# Portfolio
<!-- Tech Stack -->
<p align="center">
  <a href="https://github.com/Rol0a/Portoflio_CV/search?l=python">
    <img src="https://img.shields.io/badge/Python-56%25-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  </a>
  <a href="https://github.com/Rol0a/Portoflio_CV/search?l=typescript">
    <img src="https://img.shields.io/badge/TypeScript-27%25-3178C6?style=for-the-badge&logo=typescript&logoColor=white" alt="TypeScript">
  </a>
  <a href="https://github.com/Rol0a/Portoflio_CV/search?l=css">
    <img src="https://img.shields.io/badge/CSS-11.3%25-663399?style=for-the-badge&logo=css&logoColor=white" alt="CSS">
  </a>
  <a href="https://github.com/Rol0a/Portoflio_CV/search?l=shell">
    <img src="https://img.shields.io/badge/Shell-3.9%25-4EAA25?style=for-the-badge&logo=gnubash&logoColor=white" alt="Shell">
  </a>
  <a href="https://github.com/Rol0a/Portoflio_CV/search?l=makefile">
    <img src="https://img.shields.io/badge/Makefile-0.7%25-6D00CC?style=for-the-badge&logo=gnu&logoColor=white" alt="Makefile">
  </a>
  <a href="https://github.com/Rol0a/Portoflio_CV/search?l=dockerfile">
    <img src="https://img.shields.io/badge/Dockerfile-0.5%25-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Dockerfile">
  </a>
</p>

<p align="center">
  <a href="https://github.com/Rol0a/Portoflio_CV/search?l=python">
    <img src="https://img.shields.io/badge/Python-56%25-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  </a>
  <a href="https://github.com/Rol0a/Portoflio_CV/search?l=typescript">
    <img src="https://img.shields.io/badge/TypeScript-27%25-3178C6?style=for-the-badge&logo=typescript&logoColor=white" alt="TypeScript">
  </a>
  <a href="https://github.com/Rol0a/Portoflio_CV/search?l=css">
    <img src="https://img.shields.io/badge/CSS-11.3%25-663399?style=for-the-badge&logo=css&logoColor=white" alt="CSS">
  </a>
  <a href="https://github.com/Rol0a/Portoflio_CV/search?l=shell">
    <img src="https://img.shields.io/badge/Shell-3.9%25-4EAA25?style=for-the-badge&logo=gnubash&logoColor=white" alt="Shell">
  </a>
  <a href="https://github.com/Rol0a/Portoflio_CV/search?l=makefile">
    <img src="https://img.shields.io/badge/Makefile-0.7%25-6D00CC?style=for-the-badge&logo=gnu&logoColor=white" alt="Makefile">
  </a>
  <a href="https://github.com/Rol0a/Portoflio_CV/search?l=dockerfile">
    <img src="https://img.shields.io/badge/Dockerfile-0.5%25-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Dockerfile">
  </a>
</p>


Bilingual (EN/ES) CV/portfolio site for Rodrigo López, self-hosted on a home
server behind Cloudflare Tunnel — no port forwarding, no public IP exposure.
Public content (projects, skills, certifications, CV download, contact form)
is served to anyone; an authenticated admin dashboard with first-party
analytics is reachable only over Tailscale.

## Features

- Project showcase with detailed case-study pages (problem, architecture,
  implementation, decisions, results) per project
- Skills grouped by discipline, certifications list
- CV download, tracked as an analytics event
- Contact form that relays to email over SMTP — messages are never stored,
  so the database holds no visitor PII (`backend/app/services/contact_service.py`)
- English/Spanish i18n, language persists between visits
- Admin dashboard: aggregate visitor analytics and live network-health
  samples from the NOC service, authenticated, Tailscale-only
- Privacy-conscious first-party analytics with a retention sweep
  (`backend/app/services/retention_service.py`) — no third-party trackers

## Tech stack

| Layer | Choice |
|---|---|
| Frontend | React 18 + TypeScript, Vite, React Router, i18next, Recharts, `motion` |
| Backend | FastAPI, SQLAlchemy 2.0 (async), Alembic, Pydantic v2 |
| Database | PostgreSQL 16 |
| Reverse proxy | Caddy 2 |
| Public ingress | Cloudflare Tunnel (outbound-only from the host) |
| Admin access | Tailscale |
| Monitoring | Custom NOC service (`noc/monitor.py`) sampling network health |
| Containerization | Docker Compose (separate dev/prod compose files) |
| CI | GitHub Actions — typecheck, tests, dependency audit, image builds |

## Architecture at a glance

```
Visitor ──HTTPS──▶ Cloudflare edge ──Tunnel──▶ cloudflared ──▶ Caddy :80
                                                                  │
                                                    ┌─────────────┼──────────────┐
                                                    ▼                            ▼
                                             frontend (static SPA)      backend (/api/*) ──▶ PostgreSQL
                                                                                  ▲
Admin (you) ──WireGuard──▶ Tailscale ──▶ host:8443 ──▶ Caddy admin block ────────┘
                                                        (full API incl. /api/v1/admin/*)
```

Admin, auth, and internal routes (`/admin*`, `/api/v1/admin/*`,
`/api/v1/auth/*`, `/internal/*`) return 404 on the public block — they only
exist behind the Tailscale-only admin block. Full rationale in
[`docs/security.md`](docs/security.md).

## Repository structure

```
backend/            FastAPI app — routes, services, models, schemas, Alembic migrations, tests
frontend/            React/Vite SPA — pages, components, i18n, tests
noc/                 Network-health monitoring service (own Dockerfile)
infrastructure/caddy/ Production Caddyfile (public + Tailscale-admin site blocks)
scripts/             Seed data, backup/restore, retention purge, SMTP check, preflight checks
docs/                architecture.md, security.md, deployment.md, frontend-design.md
docker-compose.yml         Production stack
docker-compose.dev.yml     Local dev stack (hot reload, published DB/API ports)
```

## Getting started (development)

Prerequisites: Docker, Docker Compose, `make`.

```bash
cp .env.example .env   # fill in local values; see comments in the file
make dev-build          # first run — builds images and starts the dev stack
make db-migrate          # apply Alembic migrations
make db-seed              # load sample project/skills/certification data
```

Dev stack ports: frontend `5173`, backend `8000`, Postgres `5432` (all
published to `localhost` — see `docker-compose.dev.yml`). Subsequent runs:
`make dev`. Other useful targets: `make backend-shell`, `make frontend-shell`,
`make db-shell`, `make dev-logs`. Full list in the [`Makefile`](Makefile).

## Testing

```bash
make test   # backend pytest + frontend vitest, inside the dev containers
```

Or individually: `cd frontend && npm run typecheck && npm run test`,
`docker compose -f docker-compose.dev.yml exec backend pytest`.

CI (`.github/workflows/ci.yml`) runs frontend typecheck/test/audit, backend
tests/audit, and validates that both production Docker images and the
Caddyfile build/validate cleanly.

## Production deployment

Runs as a Docker Compose stack on the home server, reachable only through an
outbound Cloudflare Tunnel — nothing listens on the router or a public IP.
The admin surface is published solely on the host's Tailscale address.
Step-by-step host prep, secrets, first deploy, verification, rollback, and
failure playbook: [`docs/deployment.md`](docs/deployment.md).

```bash
make prod-up          # docker compose up -d, production stack
make tunnel-status    # confirm the Cloudflare Tunnel is actually connected
make prod-logs
```

## Documentation

| Doc | Covers |
|---|---|
| [`docs/architecture.md`](docs/architecture.md) | Requirements, system design, DB schema, REST API, testing/CI strategy |
| [`docs/security.md`](docs/security.md) | Network exposure model, admin isolation, firewall, secrets, visitor-data privacy, backups |
| [`docs/deployment.md`](docs/deployment.md) | Host prep through cutover, rollback, and failure playbook for the production stack |
| [`docs/frontend-design.md`](docs/frontend-design.md) | Design system and frontend workflow |

## Contact

- GitHub: [Rol0a](https://github.com/Rol0a)
- LinkedIn: [rodrigo-lópez](https://www.linkedin.com/in/rodrigo-l%C3%B3pez-a9a696222/)
- Email: mlopez2018ig@gmail.com
