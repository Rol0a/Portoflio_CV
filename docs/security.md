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

### Chosen strategy: Tailscale Funnel

**Decided 2026-08-20, replacing Cloudflare Tunnel.** The deciding constraint
was not technical: this deployment must cost nothing, and a Cloudflare *named*
tunnel requires a DNS zone, which requires buying a domain. A Cloudflare
*quick* tunnel needs no domain but hands out a new random
`*.trycloudflare.com` hostname on every restart, with no uptime guarantee —
unusable for a CV that people are meant to be able to return to.

**Tailscale Funnel** (BSD-3 client, WireGuard-based) gives a stable public
HTTPS hostname for free, with no domain and no account beyond the Tailscale
one already in use for admin access (§3):

```
https://roloa.tailb961fd.ts.net
```

It keeps every property that made Cloudflare Tunnel the original choice:

- **No inbound port, ever.** `tailscaled` holds an outbound connection to
  Tailscale's ingress. Nothing listens on the home IP, so there is nothing for
  a port scanner to find, and CGNAT (§1) is irrelevant.
- **The home IP is never published.** The public hostname resolves to
  Tailscale's ingress addresses (`199.38.181.54`, `209.177.145.137` at time of
  writing), never to this network. Confirmed by resolving the name against a
  public resolver rather than MagicDNS — from inside the tailnet the same name
  resolves to `100.x.y.z`, which is why local `dig` output proves nothing here.
- **Valid public TLS**, provisioned automatically by Tailscale via Let's
  Encrypt. Verified: `curl` reports `ssl_verify_result: 0`.

The trade-off is the same shape as before and worth stating plainly: traffic
relays through Tailscale's infrastructure, so they are a trusted intermediary
exactly as Cloudflare would have been. The client is open source; the relay is
not self-hosted. Given the alternative is paying for a domain or an
always-on VPS, this is the deliberate choice — and `architecture.md` §11
already listed it as Strategy C.

### The one configuration that would undo all of this

Funnel can serve **443, 8443, or 10000**. The admin site (§3) is bound to
**8443**. Funnelling 8443 would publish the admin dashboard to the open
internet while every other control in this document remained perfectly intact
and completely irrelevant.

`scripts/preflight.sh` fails loudly if Funnel is ever serving anything but
443. Turn a mistake off with:

```bash
tailscale funnel --https=8443 off
```

### How the public path fits together

```
Visitor
    │  HTTPS (TLS terminated by Tailscale's ingress)
    ▼
Tailscale Funnel ingress  ── no inbound port opened at the home network ──
    │
    ▼  tailscaled on the host, outbound connection held open
127.0.0.1:8080            ← Caddy's public block, published to host LOOPBACK
    │                       ONLY (docker-compose.yml). "8080:80" would bind
    │                       0.0.0.0 and put the whole site on the home LAN.
    ▼
caddy :80  (public site block, matches on $DOMAIN)
    │
    ├── /api/*  → backend:8000
    └── else    → frontend:80
```

Admin traffic never touches this path at all: it goes tailnet → `:8443`,
published only on the host's Tailscale address (§3).

```bash
make funnel         # enable (443 → 127.0.0.1:8080)
make funnel-status  # what is published right now
make funnel-off     # take the site off the internet
```

Funnel config is stored in `tailscaled`'s state, not in memory: verified by
restarting `tailscaled` and confirming Funnel came back on its own. With
`tailscaled` enabled at boot and `portfolio-stack.service` bringing the stack
up (`docs/deployment.md` §1.5), the site restores itself after a reboot with
no manual step.

### What Funnel does and does not rewrite

Determined empirically against the live public ingress, not assumed — this
governs §9's client-IP handling and §3.1's exposure guard, so guessing was not
an option:

| Header | Behaviour | Consequence |
|---|---|---|
| `X-Forwarded-For` | **Overwritten** with the real client IP. A request forging `1.2.3.4` arrived carrying the true address. | Trustworthy. This is what analytics and login throttling key on. |
| `Tailscale-Funnel-Request` | **Overwritten** to `?1` on every public request. A client sending `?0` had it corrected. | Un-forgeable proof a request came from the public internet — used as the outermost rule in §3.1. |
| Anything else (e.g. `X-Portfolio-Entry`) | **Passed through untouched.** | Any header the backend trusts must be overwritten at the Caddy boundary. It is. |

The last row is the one that bites: Funnel is not a header sanitiser. The
public Caddy block's `header_up X-Portfolio-Entry public` is what makes that
safe, and it must never be softened into a conditional.

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

### 3.1 The backend enforces this too, independently of Caddy

Everything above is one control in one file. If a `handle` block is dropped
from the Caddyfile, or the tunnel's ingress rule is repointed straight at
`backend:8000` to rule out the proxy while debugging, or the stack comes up
without the `caddy` service, then nothing above is enforcing anything — and
the failure is silent, because the site keeps working.

`backend/app/middleware/exposure.py` is the second lock, so the layers have
to fail together. Its rules are deliberately of different kinds:

0. **Anything Tailscale marks as a public Funnel request is refused outright
   on every non-public surface.** Tailscale sets
   `Tailscale-Funnel-Request: ?1` on ingress and overwrites any
   client-supplied value (§2's table), so a visitor can neither forge it nor
   strip it. This is the strongest signal available here because it is the
   only one this project does not generate itself — it holds even when the
   Caddyfile is wrong, absent, or bypassed, which is exactly when the other
   two stop being trustworthy. A correct admin entry marker does **not**
   override it.
1. **`/internal/*` is for unproxied, in-network callers only.** The `noc`
   service reaches it as `http://backend:8000/internal/metrics` over the
   Docker network, so a legitimate request carries no `X-Forwarded-For`;
   anything that passed through any proxy has one. No shared secret, no
   knowledge of Caddy's address — it keys on a structural property of the
   only supported call path.
2. **Admin and auth surfaces require proof of admin entry, on any request
   that was proxied at all.** Caddy's admin block stamps `X-Portfolio-Entry`
   with the expected value; the public block stamps `public`. Both *set* the
   header, so a value a visitor supplies is overwritten and cannot survive
   the public path.

   The rule is "proxied and not marked admin → refuse", not "marked public →
   refuse", specifically so it also covers the bypass case: a request from a
   repointed tunnel has an `X-Forwarded-For` (cloudflared adds one) and no
   marker at all. An *unproxied* request has neither header and is allowed —
   that is dev, the test suite, and direct in-network calls, none of which can
   originate from the internet given `docker-compose.yml` publishes no port
   for the backend.

`ADMIN_ENTRY_TOKEN` upgrades the marker from a known constant to a shared
secret; without it both sides fall back to the literal `admin`, which still
catches a Caddy misconfiguration but is guessable by an attacker already past
Caddy. The backend logs a warning when running on that fallback rather than
degrading silently — the same pattern §7's NOC credential uses.

Both rules answer `404`, matching Caddy, so neither confirms the path exists.

One limit worth stating plainly: the guard only sees requests that reach the
*backend*. `/admin*` in the public block falls through to the frontend
container's nginx, not the backend, so if that deny rule were removed the SPA
shell itself would be served publicly. That is inert — every API call it makes
goes to `/api/v1/auth/*` or `/api/v1/admin/*`, which the guard does refuse — but
"the admin page cannot be loaded from the internet" is a property of the
Caddyfile alone, while "the admin page cannot *do* anything from the internet"
is enforced twice.

`backend/tests/test_exposure_guard.py` covers this by speaking ASGI directly
to the middleware — deliberately not through Caddy, since bypassing Caddy is
the situation the guard exists for. `scripts/preflight.sh` checks that both
halves (the Caddy stamps and the backend wiring) are present, because a check
that only looked at one would report a single point of failure as healthy.

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

### 4.1 What this host actually looks like right now

The rules above are the target state, not a description. Audited on
2026-08-20, `ufw` on this host is active with `default deny (incoming)` and
does **not** open 80/443 — but SSH is allowed from *anywhere*, on both IPv4
and IPv6:

```
22/tcp (SSH)               ALLOW IN    Anywhere
22/tcp (SSH (v6))          ALLOW IN    Anywhere (v6)
```

That is every device on the home LAN, including anything that joins it
later, rather than the tailnet-only access this section specifies.
`fail2ban` is not installed either. `scripts/preflight.sh` now fails on both
rather than only checking 80/443, so neither can drift back unnoticed.

`scripts/harden_host.sh` applies this section (and §6) for real. It is a
dry run by default — `make harden` prints the plan and changes nothing;
`make harden-apply` acts. It adds the `tailscale0` rules *before* deleting
the permissive ones, so there is never a window with no SSH rule, refuses to
run at all if Tailscale is down (removing the open rule with no tailnet would
leave no way back in), prompts before each deletion, and re-reads `ufw
status` afterwards to verify rather than assume.

**WSL2 caveat.** `systemd-detect-virt` reports `wsl`, so `ufw` here filters
the Linux distro only. Inbound LAN traffic reaches WSL2 through the Windows
host's NAT and the *Windows* firewall, which none of this configures. These
rules harden the server VM; they are not the outer perimeter. The outer
perimeter is that nothing is port-forwarded (CGNAT makes inbound IPv4
impossible upstream regardless — see `docs/CLAUDE.md` §2) and that the tunnel
is outbound-only.

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

`scripts/harden_host.sh` installs and enables this, with `ignoreip` covering
the tailnet (`100.64.0.0/10`) so a mistyped password from the admin's own
laptop cannot lock them out of their own server.

Note the layering: with §3, §3.1 and §4 in place, fail2ban is the *third*
control on the admin login path, not the first. That is deliberate — it is
the only one of the three that reacts to a sustained campaign rather than
refusing each request in isolation.

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
  2. **Caddy — done, and rewired for Funnel (2026-08-20).** The public
     block pins `X-Forwarded-For` to the value Tailscale Funnel already set:

     ```caddyfile
     header_up X-Forwarded-For {http.request.header.X-Forwarded-For}
     ```

     Two things make this correct rather than circular:

     - Funnel **overwrites** `X-Forwarded-For` with the real client address
       before the request reaches this host (§2's table — verified against the
       live ingress, not assumed), so the incoming value cannot be spoofed by
       the visitor.
     - Pinning it, rather than letting `reverse_proxy` append this hop, is
       what keeps it usable. Caddy would otherwise forward
       `<visitor>, <docker-gateway>`, and the backend's
       `ProxyHeadersMiddleware` trusts only Caddy's own `172.20.0.10` — so it
       would resolve the *gateway* as the client and collapse every visitor to
       a single address. That is precisely the bug this section exists to
       prevent, reintroduced by an apparently harmless default.

     The previous value was `{http.request.header.CF-Connecting-IP}`, correct
     for Cloudflare and **empty under Funnel**. Leaving it would have silently
     broken unique-visitor analytics and turned per-IP login throttling into
     one global allowance — with no error anywhere.

     **Verified end to end**, not inferred: an event posted through the public
     Funnel ingress stored an `ip_hash` equal to
     `sha256("<real client IP>:<date>:<secret>")`, and *not* the hash of the
     Docker gateway or of the Caddy container.
- **Access logs are sensitive too.** Caddy's default access log includes
  the (now-correct, per above) visitor IP in plaintext on disk. Keep log
  file permissions restrictive (`chmod 640`, owned by a dedicated
  non-login user) and rotate/expire them on the same cadence as the
  analytics retention policy (`architecture.md` §9: 90 days) rather than
  keeping raw IP-bearing logs indefinitely.

### 9.1 The endpoint only accepts performance data — enforced, not assumed

`POST /api/v1/analytics/events` is unauthenticated and public; that is what a
beacon is. Its `metadata` field was a bare `dict`, so whatever anyone sent was
written verbatim into a JSONB column — on a site whose documentation promises
it stores no personal data. Anyone with `curl` could have posted
`{"email": "...", "message": "..."}` and had it persisted indefinitely.

`test_analytics_privacy.py` asserted the stored shape was `{"path"}`, but only
for rows the test itself constructed, so it could never have caught this. The
promise was real; the enforcement was not.

`backend/app/schemas/analytics.py` now enforces it at the wire boundary, as an
**allowlist rather than a blocklist**:

| Field | Accepted | Everything else |
|---|---|---|
| `metadata.path` | a route path, query string and fragment stripped first | dropped |
| `metadata.from` / `.to` | a short locale code | dropped |
| `metadata.link` | a short lowercase token our own code chose | dropped |
| `session_id` | 8–128 chars of `[A-Za-z0-9_-]` — no spaces, no `@`, no `.` | blanked, so the event is ignored |
| `project_slug` | a slug | dropped |

Adding a new tracked dimension therefore requires editing that file, which is
exactly the review checkpoint this commitment needs.

Two details that matter more than they look:

- **Query strings are stripped, not rejected.** `/contact?email=someone@…`
  is an ordinary URL, and storing the path verbatim would store the address
  without anyone intending it. The navigation still counts as a view of
  `/contact`; the parameters never reach the database.
- **Nothing surviving is stored as `NULL`, not `{}`.** A scrubbed event is
  indistinguishable from one that never carried metadata — no empty object
  left behind as a marker that something was removed.

Sanitising rather than rejecting is deliberate: a beacon cannot react to a
4xx, so a hard `422` would turn a stray field into lost measurement. Dropping
the offending key keeps the countable part, which is the only part that was
ever wanted.

`backend/tests/test_analytics_input_policy.py` comes at this from the
attacker's side — it hands the schema the payloads a hostile or careless
client would actually send and requires the policy to strip them.

**What is deliberately still collected**, because it is performance/behaviour
data and not identity: event type and timestamp, which route was viewed, which
project, which locale, a client-generated random `session_id`, a daily-salted
IP hash, and a truncated user-agent hash. Nothing in that set is asked of the
visitor, and the two hashes rotate or truncate specifically so they cannot be
joined back to a person (see §9's parent section and `architecture.md` §9).

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

`make preflight` checks most of this automatically and fails rather than warns
on anything that silently breaks the design. As of **2026-08-20 it reports 48
passed, 0 failed, 2 warnings** — the site is live and every hard requirement
below is met.

**Live at https://roloa.tailb961fd.ts.net** — free, no domain, stable hostname.

- [x] ✓ Public ingress is Tailscale Funnel on **443 only**; the admin site on
      8443 is not published (§2 — the one misconfiguration that would undo
      everything, and the one preflight fails loudest on)
- [x] ✓ `DOMAIN` matches the Funnel hostname, so Caddy's public block actually
      matches instead of falling through to the catch-all
- [x] ✓ Home IP never published — the hostname resolves to Tailscale's ingress
      addresses on the public internet. No inbound port opened; CGNAT irrelevant
- [x] ✓ Valid public TLS, auto-provisioned by Tailscale (`ssl_verify_result: 0`)
- [x] ✓ Funnel config persists in `tailscaled` state — verified by restarting
      the daemon and watching it come back on its own. `tailscaled` and
      `portfolio-stack.service` are both enabled at boot
- [x] ✓ No quick tunnel running; `cloudflared` is profile-gated so a bare
      `docker compose up -d` cannot start it tokenless and crashloop
- [x] ✓ `ufw` enabled, default-deny inbound, 80/443 never opened, IPv6 managed
- [x] ✓ SSH not open beyond the tailnet (and in fact no `sshd` is installed on
      this host at all — see §4.1)
- [x] ✓ Every published Docker port is tailnet-only or loopback-only; nothing
      binds `0.0.0.0`
- [x] ✓ Public Caddy block 404s `/internal/*`, `/api/v1/admin/*`,
      `/api/v1/auth/*`, `/admin*` — verified live through the public ingress
- [x] ✓ The backend enforces the same boundary independently, with three
      signals of different kinds (§3.1), the outermost being Tailscale's own
      un-forgeable Funnel marker
- [x] ✓ `ADMIN_ENTRY_TOKEN` set, so the entry marker is a shared secret
- [x] ✓ Real visitor IP survives Funnel → loopback → Docker NAT → Caddy →
      backend, confirmed by hash comparison rather than assumption (§9)
- [x] ✓ Analytics accepts performance fields only, enforced server-side (§9.1)
- [x] ✓ `.env` is `chmod 600`, untracked, no secret appears elsewhere in the repo
- [x] ✓ `no-new-privileges` on every container, `read_only` where feasible,
      resource limits on all of them
- [x] ✓ `noc` on the least-privilege `noc_writer` role (§7)
- [ ] restic backups running nightly, retention configured, **restore tested at
      least once** — restic is installed; the schedule is not verified here.
      **This is now the largest remaining gap.**
- [ ] `unattended-upgrades`/`dnf-automatic` for OS security patches; Diun (or
      equivalent) watching for container image updates
- [ ] Network Health / NOC dashboard (§12) checked once against the live
      environment

### Two accepted warnings, not defects

**fail2ban is not running, and installing it now would be theatre.** There is
no `sshd` on this host, so the SSH jail would watch nothing, and §6's
admin-login jail needs the backend writing a parseable log file — it currently
logs to Docker's json-file driver instead. `scripts/harden_host.sh` installs
and configures it correctly (`banaction = ufw`, tailnet in `ignoreip`, SSH jail
auto-disabled when no sshd exists) if either of those changes.

**`CONTACT_TO_EMAIL` is hardcoded in the frontend bundle.** The owner's address
is published on their own CV on purpose, so preflight warns rather than fails.
What protects the mailbox is the Gmail App Password, which is a real secret and
is checked. If the contact form should be the only route, remove the address
from `frontend/src/config/profile.ts`, both i18n bundles and the README.
