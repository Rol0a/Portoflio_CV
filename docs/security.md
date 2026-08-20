# Security Architecture — Home-Server Launch

This document is the concrete, tool-by-tool answer to one question: **how
does this portfolio go live on a home server without exposing the home
network's public IP, or any other personal/critical data, to the internet?**

It extends `architecture.md` §8 (Security Model) and §11 (Home-Server
Deployment Architecture) rather than replacing them — those sections cover
the *application-level* threat model (SQL injection, session cookies, CORS)
and the general deployment options. This document picks one concrete path
through those options for this deployment and adds the network- and
host-level hardening architecture.md left open. If a decision here
contradicts something in `architecture.md`, this file wins for anything
network/host-related; `architecture.md` wins for anything inside the
application itself.

**Tooling rule for this whole document:** every tool recommended is either
open source (auditable, self-hostable, no vendor lock-in) or first-party —
provided directly by the OS, Docker, or the project itself, not a
commercial third-party security SaaS. The one deliberate exception
(Cloudflare Tunnel's relay) is called out explicitly in §2, with the
trade-off stated plainly rather than glossed over.

## Table of Contents

1. [Starting Point](#1-starting-point)
2. [Network Exposure Strategy](#2-network-exposure-strategy)
3. [Keeping the Admin Surface Private](#3-keeping-the-admin-surface-private)
4. [Firewall](#4-firewall)
5. [TLS](#5-tls)
6. [Brute-Force and Intrusion Protection](#6-brute-force-and-intrusion-protection)
7. [Container and Host Hardening](#7-container-and-host-hardening)
8. [Secrets Management](#8-secrets-management)
9. [Visitor Data Privacy](#9-visitor-data-privacy)
10. [Backups](#10-backups)
11. [Updates and Patching](#11-updates-and-patching)
12. [Monitoring Ties Into the NOC Service](#12-monitoring-ties-into-the-noc-service)
13. [Pre-Launch Checklist](#13-pre-launch-checklist)

---

## 1. Starting Point

This deployment is **behind CGNAT** (confirmed directly, not inferred) — the
ISP does not hand out a public IP the router can accept inbound connections
on, so `architecture.md` §11's "Strategy A: Direct Port Forwarding" is not
available. Everything below is written for that reality: **no port on the
home router is ever forwarded, and 80/443 are never opened to the internet
at the router.** If that ever changes (new ISP, business-tier line with a
real public IP), re-run the CGNAT check in `architecture.md` §11 and this
document's firewall rules in §4 still apply — only §2's tunnel becomes
optional rather than required.

## 2. Network Exposure Strategy

### The core problem

A home server's public IP is itself sensitive: it can be used to
approximate the server owner's physical location (via IP geolocation) and
is the starting point for any direct network attack. The goal isn't just
"don't get hacked" — it's **never let a visitor's browser, DNS record, or
HTTP response reveal the home network's real IP address at all.**

### Chosen strategy: Cloudflare Tunnel

`cloudflared` (Cloudflare's tunnel client) is **Apache-2.0 licensed and
open source** — its source is auditable, and it's what makes this the one
deliberate exception to "self-hosted only" in this document: the client is
open source, but traffic relays through Cloudflare's infrastructure, which
is closed and third-party. That trade-off was chosen deliberately over the
alternative (renting a VPS as a self-hosted relay) because:

- It requires no inbound ports at all — `cloudflared` makes an **outbound**
  connection from the home server to Cloudflare's edge and holds it open.
  There is nothing for a port scanner to find, because nothing is
  listening on the public internet at the home network's IP.
- DNS for the public hostname points at Cloudflare's proxy IPs (the
  "orange cloud" state in Cloudflare DNS), never at the home IP. A visitor
  resolving the domain, or running `dig`/`whois` against it, sees
  Cloudflare — never the home network.
- It's free for this traffic volume and doesn't require running or paying
  for a separate always-on VPS.

If cost/trust trade-offs change later, `architecture.md` §11's "Strategy C:
Tailscale Funnel" is a drop-in alternative with the same shape (open-source
client — Tailscale's client is BSD-3, built on the fully open-source
WireGuard protocol — relayed through Tailscale's infrastructure when direct
peer-to-peer isn't possible through CGNAT).

### Setup shape

```
Home server (Docker host)
    │
    │ outbound-only, encrypted, no inbound port ever opened
    ▼
Cloudflare edge  ──(DNS: proxied "orange-cloud" A/AAAA record)──  Visitor
    │
    ▼ (ingress rule inside the tunnel config)
http://caddy:80  (same docker network as the app containers)
```

`cloudflared` runs as its own container on the existing `portfolio-net`
Docker network (or on the host directly — the container form keeps it
alongside everything else this project already manages with Compose):

```yaml
# docker-compose.yml (production) — illustrative, fill in the tunnel token
# from the Cloudflare Zero Trust dashboard (Networks → Tunnels), stored in
# .env like every other secret, never committed.
cloudflared:
  image: cloudflare/cloudflared:latest
  command: tunnel run
  environment:
    - TUNNEL_TOKEN=${CLOUDFLARE_TUNNEL_TOKEN}
  networks:
    - portfolio-net
  restart: unless-stopped
```

The tunnel's ingress rule points at `http://caddy:80` — plain HTTP is fine
for that one hop because it never leaves the Docker network, and the
tunnel connection itself (host → Cloudflare edge) is already encrypted.
Cloudflare terminates public TLS at its edge; Caddy can also hold its own
certificate and the tunnel can be configured for "Full (strict)" mode for
defense-in-depth (TLS end-to-end even inside the host), but that's an
optional hardening step, not required for the IP-hiding property itself.

### The IPv6 leak to watch for

This is the detail that's easy to miss and defeats the whole point if
missed: many home routers pass a globally-routable IPv6 address straight
through to LAN devices, **bypassing NAT and CGNAT entirely.** If the Docker
host has such an address and nothing blocks inbound IPv6, a service
listening on `0.0.0.0`/`::` can be reachable directly over IPv6 — a
completely separate path from the IPv4 CGNAT problem this tunnel solves,
and one that leaks the real network just as badly.

**Mitigation:** block all inbound IPv6 at the host firewall (§4) regardless
of tunnel setup, and confirm no container publishes a port that binds the
IPv6 wildcard. Don't publish an AAAA record for the public hostname unless
it's also proxied through Cloudflare.

## 3. Keeping the Admin Surface Private

The admin dashboard and the new Network Health / NOC page (see
`architecture.md`'s M9/M10 and this session's addition) don't need to be
reachable from the public internet at all — **only the site owner ever
uses them.** The cheapest, most effective hardening available here is to
simply never put them on the public path in the first place, rather than
relying on the login screen as the only line of defense.

**Tailscale** (BSD-3 client, WireGuard-based, first-party mesh VPN) gives
the server a private IP (`100.x.y.z`) reachable only from devices logged
into the same Tailscale account/tailnet — effectively a personal VPN
between the admin's own devices and the server, with no public exposure at
all.

Caddy gets a **second site block**, reachable only over Tailscale, serving
the admin routes — while the public, tunnel-facing site block explicitly
refuses to proxy them.

> **This section's config below is the original sketch, superseded by the
> real `infrastructure/caddy/Caddyfile`.** Building it surfaced three
> defects in the sketch, all of which the shipped file fixes. Kept here
> because the *reasoning* around it still stands; read the Caddyfile for
> what actually runs.
>
> 1. **`bind tailscale0` cannot work from a container** — the host's
>    `tailscale0` interface does not exist in the container's network
>    namespace. The shipped version publishes the port as
>    `"${TAILSCALE_IP}:8443:8443"` in `docker-compose.yml` instead, which
>    restricts reachability identically without host networking.
> 2. **The CSP breaks the site's typography.** It omits `font-src` and the
>    `fonts.googleapis.com` entry in `style-src`, so the Fraunces + Karla
>    webfonts that `frontend-design.md` §1 specifies would be blocked — in
>    production only, silently.
> 3. **`/api/v1/auth/*` is left public.** Since the admin only ever signs in
>    over Tailscale, the shipped config denies login on the public hostname
>    too, removing an internet-facing brute-force target rather than relying
>    on rate limiting to absorb it.
>
> The shipped file also wraps the deny rules in `route` so their order is
> explicit rather than resting on Caddy's implicit specificity sort, and adds
> a catch-all `:80` block because Caddy answers an unmatched `Host` with an
> empty `200` by default.

```caddyfile
# Public hostname — reachable ONLY via the Cloudflare Tunnel ingress rule,
# never bound to a host port directly.
portfolio.example.com {
    handle /api/v1/admin/* {
        respond 404
    }
    handle /internal/* {
        respond 404
    }
    handle /api/* {
        reverse_proxy backend:8000
    }
    handle {
        reverse_proxy frontend:80
    }
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options nosniff
        X-Frame-Options DENY
        Referrer-Policy strict-origin-when-cross-origin
        Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'"
        Permissions-Policy "camera=(), microphone=(), geolocation=()"
    }
}

# Admin-only — bound to the Tailscale interface, so it's simply
# unreachable from anywhere but the private tailnet, tunnel or no tunnel.
:8443 {
    bind tailscale0
    reverse_proxy /api/* backend:8000
    reverse_proxy frontend:80
}
```

This means: even if the admin session cookie or password were somehow
compromised, an attacker on the open internet still can't reach
`/admin/dashboard`, `/admin/network-health`, or `/api/v1/admin/*` at all —
those paths simply 404 on the public hostname. `/internal/metrics` (the
NOC service's polling target, see `architecture.md` and the backend's
`app/routes/internal.py`) gets the same treatment: it was never proxied by
Caddy's public block to begin with, so this is belt-and-suspenders, not the
only protection.

SSH access to the host itself should go the same way — bind `sshd` to the
Tailscale interface (or firewall it to only accept connections from the
`100.64.0.0/10` Tailscale range) instead of leaving port 22 reachable from
the LAN/WAN at all.

## 4. Firewall

`ufw` (Ubuntu/Debian's first-party firewall front-end for `nftables`/
`iptables`) — with the tunnel handling all public web traffic outbound-only
and admin access routed over Tailscale, the host firewall's job simplifies
to **default-deny everything inbound, with narrow exceptions:**

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing

# Tailscale's own interface — required for the admin-only access in §3
sudo ufw allow in on tailscale0

# SSH — ONLY from the Tailscale range, never from the raw internet
sudo ufw allow in on tailscale0 to any port 22 proto tcp

# Explicitly deny all IPv6 inbound (see §2's IPv6 leak note)
sudo ufw deny in from ::/0

sudo ufw enable
```

Notice **80 and 443 are never opened** — because `cloudflared` makes an
outbound connection, the host never needs to accept inbound traffic on
those ports at all. This is a stronger position than the direct
port-forwarding path in `architecture.md` §11 would have been.

## 5. TLS

Unchanged from `architecture.md` §8/§11: Caddy provisions and renews
certificates automatically via ACME/Let's Encrypt for the Tailscale-bound
admin site block too (Caddy supports internal/self-signed certs for
non-public names, or a real cert if the admin hostname is a subdomain
that's DNS-validated but never proxied publicly — either works; the
non-public reachability from §3 is what actually matters here, TLS is
defense in depth on top of it).

## 6. Brute-Force and Intrusion Protection

**fail2ban** (GPL, the standard first choice) watching:

- SSH auth log (redundant with §3/§4 restricting SSH to Tailscale, but
  cheap insurance if that config ever regresses)
- The admin login endpoint's failed attempts — `architecture.md` §8
  already specifies application-level rate limiting (5 attempts/IP/15min)
  on `/api/v1/auth/login`; point fail2ban at the backend's structured log
  output for that endpoint so repeated failures escalate to an actual
  firewall ban, not just a slowed-down retry.

```ini
# /etc/fail2ban/jail.local
[sshd]
enabled = true

[portfolio-admin-login]
enabled = true
filter = portfolio-admin-login
logpath = /var/log/portfolio/backend.log
maxretry = 5
findtime = 900
bantime = 3600
```

**CrowdSec** (MIT-licensed) is a reasonable upgrade path later — same
job as fail2ban plus community-sourced blocklist enrichment and a
Cloudflare bouncer that can push bans to Cloudflare's edge directly
(useful specifically because this deployment sits behind a tunnel — a
local iptables ban only stops traffic that already reached the host).
Not required for launch; fail2ban covers the same core threat with less
setup.

## 7. Container and Host Hardening

Building on what's already in place (`backend/Dockerfile`'s non-root
`appuser`, `noc/Dockerfile`'s non-root `noc` user, Postgres never
publishing its port in production per `architecture.md` §8):

- **`security_opt: no-new-privileges:true`** on every service — already
  set on `noc` in `docker-compose.dev.yml`; carry it into the production
  compose file for `backend`, `frontend`, and `caddy` too.
- **`read_only: true`** on containers that don't need to write to their
  own filesystem at runtime (the `noc` service already runs this way — it
  only writes to Postgres, never to its own disk). `backend` needs
  targeted exceptions (e.g. an uploads volume) rather than a blanket
  read-only root.
- **Resource limits** (`deploy.resources.limits` in Compose, or
  `mem_limit`/`cpus` directly) on every service — bounds the blast radius
  of a runaway process and gives the NOC dashboard's host-resource charts
  (§12) something meaningful to actually watch for.
- **Least-privilege database roles — CLOSED.** The `noc` service used to
  reuse the backend's `DATABASE_URL`, which owns every table, while all it
  does is insert samples and prune them. It now connects as a dedicated
  `noc_writer` role, provisioned by `scripts/create_noc_role.sql`
  (`make noc-role` / `make noc-role-prod`) and wired through
  `NOC_DATABASE_URL` in both compose files.

  The grant sketched here originally was incomplete: `id` is `BIGSERIAL`, so
  `USAGE` on `network_health_samples_id_seq` is required too — without it
  every insert fails with "permission denied for sequence". The role gets
  `SELECT, INSERT, DELETE` on that one table, `USAGE` (not `CREATE`) on the
  schema, and nothing else.

  Deliberately **not** granted `UPDATE` or `TRUNCATE`: the service appends
  and prunes, so withholding both means a compromised NOC container cannot
  rewrite recorded history or erase it wholesale.

  Verified empirically rather than assumed — reads of `admin_users`,
  `admin_sessions`, `analytics_events`, `login_attempts`, `projects`, and
  `certifications` all fail with "permission denied", as do `CREATE TABLE`,
  `DROP`, `TRUNCATE`, `UPDATE`, `CREATE ROLE`, `ALTER ROLE ... SUPERUSER`,
  and reading `pg_shadow`. `backend/tests/test_noc_role.py` asserts this
  continuously, enumerating tables at runtime so a table added by a future
  migration is covered automatically; it skips cleanly where the role isn't
  provisioned (e.g. CI).

  If `NOC_DATABASE_URL` is unset the service still falls back to the shared
  credential, because that keeps a fresh checkout working — but it prints
  which credential it holds at startup, so the weaker path announces itself
  instead of passing silently.
- **Mounting host `/proc`/`/sys`** into the `noc` container (to get true
  host-level CPU/memory/disk instead of the container's own cgroup view)
  is a real, if well-established (node_exporter/cAdvisor use the same
  pattern), privilege expansion. It's deliberately **not** done in
  `docker-compose.dev.yml` — the shipped default stays fully isolated. If
  host-level accuracy matters enough to be worth it in production, mount
  both **read-only** (`/proc:/host/proc:ro`, `/sys:/host/sys:ro`) and
  nothing more; don't grant it by default.

## 8. Secrets Management

`architecture.md` §8 already covers the basics (`.env`, `.gitignore`,
never committed). Adding for the home-server launch specifically:

- `chmod 600 .env` on the host — the file is readable by the deploying
  user only.
- The Cloudflare Tunnel token and Tailscale auth key are secrets exactly
  like `SESSION_SECRET_KEY` — same `.env`, same file permissions, same
  "never in a Docker image layer" rule.
- If `.env` (or a backup of it) ever needs to leave the host — e.g. an
  encrypted off-site backup per §10 — use **`age`** (Apache-2.0/MIT,
  a small first-party-feeling successor to GPG for this exact use case)
  to encrypt it, rather than shipping it in plaintext inside a backup
  archive.

## 9. Visitor Data Privacy

`architecture.md` §9 already establishes the analytics privacy model
(no PII, hashed IPs, aggregate-first). Two things specific to the tunnel
setup in §2:

- **Get the real visitor IP, not Cloudflare's.** Once traffic passes
  through the tunnel, the IP the backend sees on each request is
  Cloudflare's edge IP, not the visitor's. This breaks *two* things, not
  one:
  - the analytics IP-hashing in `architecture.md` §9 hashes the same
    handful of Cloudflare IPs for every visitor, silently breaking the
    "approximate unique counting" the whole mechanism exists for;
  - **more seriously**, `auth_service.check_rate_limit` keys login
    throttling on the same hash, so "5 failed attempts per 15 minutes per
    IP" degrades into *5 per 15 minutes globally* — one attacker locks the
    real admin out of their own dashboard, and all attackers share a single
    allowance.

  There are two halves to the fix, and **both** are required:

  1. **Backend — done.** `ProxyHeadersMiddleware` is wired as the outermost
     middleware in `backend/app/main.py`, trusting only the peers named by
     `TRUSTED_PROXY_IPS` (`.env`), and both call sites now resolve the
     client through `app/middleware/proxy.py`'s `client_ip()`. Covered by
     `backend/tests/test_proxy_headers.py`, including the assertion that two
     distinct visitors produce two distinct `ip_hash` values. Trusting
     nothing by default is deliberate: an unset/misconfigured
     `TRUSTED_PROXY_IPS` fails closed (headers ignored, peer address used)
     rather than letting any client spoof its own IP. `TRUSTED_PROXY_IPS=*`
     is never correct on a public deployment and logs a startup warning.
  2. **Caddy — still open.** Caddy must be configured with
     `trusted_proxies` for Cloudflare's published ranges so it reads
     `CF-Connecting-IP` and passes it on as `X-Forwarded-For`. Until the
     Caddyfile exists (see §7's note that `infrastructure/` is still
     empty), the backend half above is correctly wired but has nothing
     upstream feeding it a real visitor address.
- **Access logs are sensitive too.** Caddy's default access log includes
  the (now-correct, per above) visitor IP in plaintext on disk. Keep log
  file permissions restrictive (`chmod 640`, owned by a dedicated
  non-login user) and rotate/expire them on the same cadence as the
  analytics retention policy (`architecture.md` §9: 90 days) rather than
  keeping raw IP-bearing logs indefinitely.

## 10. Backups

`architecture.md` §11 mentions a backup strategy without naming a tool.
**restic** (BSD-2, first-party-quality Go binary, single static build) is
the concrete choice:

- Encrypts backups client-side before they leave the host — the backup
  destination (even a cheap off-site disk or object storage bucket) never
  sees plaintext data.
- Built-in retention/pruning (`restic forget --keep-daily 7 --keep-weekly
  4 --keep-monthly 6`), matching the 30-day rotation `architecture.md` §16
  already calls for.
- Backs up the Postgres dump (`pg_dump` piped straight into `restic
  backup --stdin`) and the uploads volume; doesn't need the running
  containers stopped.

```bash
# cron, nightly
0 3 * * * pg_dump -U portfolio portfolio | restic backup --stdin --stdin-filename postgres.sql
0 3 * * * restic backup /var/lib/docker/volumes/portfolio_uploads
0 4 * * * restic forget --keep-daily 7 --keep-weekly 4 --keep-monthly 6 --prune
```

Test the restore procedure (`architecture.md` §12/§16 already calls for
this) *before* it's the only copy that matters.

## 11. Updates and Patching

- **`unattended-upgrades`** (Debian/Ubuntu's own first-party package,
  not third-party) for OS-level security patches — set to install
  security updates automatically, everything else manually reviewed.
- **Container images:** don't auto-apply updates blindly (a silent
  Postgres major-version bump breaking the app is worse than a delayed
  patch). Use **Diun** (MIT-licensed) to get *notified* when a newer image
  tag exists for anything in the compose file, then pull/rebuild and
  redeploy deliberately (`docker compose pull && docker compose up -d`)
  on your own schedule.
- `npm audit` / `pip-audit` in CI (`architecture.md` §8/§13 already plan
  for this) catch dependency-level vulnerabilities before they ship, which
  is a different, earlier layer than the two points above.

## 12. Monitoring Ties Into the NOC Service

The standalone `noc` service and the admin **Network Health** dashboard
page (built this session — see `noc/monitor.py`,
`backend/app/routes/admin.py`'s `/network-health` route, and
`frontend/src/pages/admin/NetworkHealth.tsx`) are the operational half of
this document: §2–§8 describe how the network is *supposed* to behave,
and the NOC dashboard is how the site owner would actually notice if it
stopped.

Everything in §3 applies to it directly: the NOC dashboard is served only
from the Tailscale-bound Caddy site block, never the public one, and the
`noc` service itself has no listening port at all — it only makes outbound
connections (to Postgres, to the backend's internal-only `/internal/metrics`,
and to a handful of public DNS resolvers for the internet-reachability
check), so there is nothing on it to attack from the outside in the first
place. See §7 for the one open hardening item on this service (the shared
database credential).

## 13. Pre-Launch Checklist

- [ ] Cloudflare Tunnel running, DNS record proxied (orange cloud), no
      AAAA record unless also proxied
- [ ] `ufw` enabled, default-deny inbound, 80/443 never opened, IPv6
      inbound denied
- [ ] Tailscale installed on the host and on the admin's own devices;
      SSH and the admin Caddy site block both bound to `tailscale0`
- [ ] Public Caddy site block explicitly 404s `/api/v1/admin/*` and
      `/internal/*`
- [ ] `trusted_proxies` configured in Caddy for Cloudflare's IP ranges so
      analytics hash the real visitor IP, not Cloudflare's
- [ ] fail2ban running for SSH and the admin login endpoint
- [ ] `.env` is `chmod 600`, not committed, tunnel token and Tailscale key
      stored the same way as every other secret
- [ ] `no-new-privileges` and `read_only` set on every production
      container where feasible; resource limits set on all of them
- [ ] `noc` service moved off the shared `DATABASE_URL` onto a
      least-privilege role (see §7 — the one item deliberately left open)
- [ ] restic backups running nightly, retention configured, **restore
      tested at least once**
- [ ] `unattended-upgrades` enabled for OS security patches; Diun (or
      equivalent) watching for container image updates
- [ ] Network Health / NOC dashboard (§12) checked once after launch to
      confirm all services show "up" and packet loss is ~0% from the
      live environment, not just dev
