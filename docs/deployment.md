# Deployment Runbook

The concrete, ordered procedure for taking this stack from a clean home server
to a live site — and for operating it afterwards.

**Scope.** `architecture.md` describes *what* is deployed and `security.md`
*why* the network looks the way it does. This document is the *how*: the order
of operations, what to verify at each step, and what to do when something
breaks. Where the other two disagree with reality, they win on design and this
file wins on procedure.

**Prerequisite reading:** `security.md` §2 (why a tunnel, not port forwarding),
§3 (why admin is split onto Tailscale), §4 (firewall). This runbook assumes
those decisions rather than re-arguing them.

> **Status.** Everything in §2–§4 is built and committed. §1 and §5 are
> host-level steps that have not been performed yet — this is the plan for
> them, not a record of them. Values marked `<...>` are environment-specific
> and belong in `.env` or the gitignored `docs/CLAUDE.md`, never here.

## Table of Contents

1. [Host Preparation](#1-host-preparation)
2. [Secrets and Configuration](#2-secrets-and-configuration)
3. [First Deploy](#3-first-deploy)
4. [Verification Gates](#4-verification-gates)
5. [Cutover](#5-cutover)
6. [Routine Operations](#6-routine-operations)
7. [Rollback](#7-rollback)
8. [Failure Playbook](#8-failure-playbook)

---

## 1. Host Preparation

Order matters here: the firewall is configured **before** the tunnel, so there
is never a window where the stack is reachable in a way it was not designed to
be.

### 1.1 Base system

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y docker.io docker-compose-v2 git restic age
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"   # log out and back in
```

On Fedora (including Fedora WSL, which is what this stack was first deployed
on) the equivalent is `dnf`, and Docker comes from Docker's own repo rather
than the distro:

```bash
sudo dnf install -y git restic age
sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
```

`restic` and `age` are needed by §6's backup procedure; installing them now
avoids discovering their absence during the first backup.

### 1.2 Tailscale (admin access path)

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up --ssh
tailscale ip -4          # -> the TAILSCALE_IP value for .env
```

This must come before the firewall step, or enabling `ufw` can lock you out of
a host you are administering over SSH.

### 1.3 Firewall

Per `security.md` §4. **80 and 443 are never opened** — the tunnel is outbound
only, so the host never accepts inbound web traffic.

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow in on tailscale0
sudo ufw deny in from ::/0        # the IPv6 leak in security.md §2
sudo ufw enable
sudo ufw status verbose
```

**Verify before continuing:** from a device *outside* the tailnet, confirm
nothing answers.

```bash
nmap -Pn -p 22,80,443,5432,8000,8443 <public-ip>   # expect all filtered
```

### 1.4 Public ingress: Tailscale Funnel

**As of 2026-08-20, the public path is Tailscale Funnel, not Cloudflare
Tunnel.** The deciding constraint was cost: a Cloudflare *named* tunnel needs
a DNS zone, which needs a purchased domain; a *quick* tunnel needs no domain
but hands out a new random `*.trycloudflare.com` hostname on every restart,
with no uptime guarantee. Funnel gives a stable hostname for free, using the
Tailscale account already required for admin access (§1.2). See
`docs/SELF_HOSTING.md` §3–§4 for the full setup and verification, and
`security.md` §2 for the header-forwarding details this depends on.

Short version:

```bash
sudo tailscale set --operator=$USER   # once, so funnel needs no sudo
make funnel                            # tailscale funnel --bg --https=443 http://127.0.0.1:8080
make funnel-status
make funnel-off                        # take the site off the internet
```

**The one configuration that would undo the whole exposure model:** Funnel
also supports serving `:8443`, which is where the admin site block is bound.
Funnelling it would publish the admin dashboard to the internet with every
other control in this document still intact and irrelevant.
`scripts/preflight.sh` fails loudly if this is ever the case — never override
that check.

`docker-compose.yml`'s `caddy` service publishes the public site block on
`127.0.0.1:8080` (host loopback only) specifically so Funnel has something to
forward into; `"8080:80"` without the loopback-pin would put the whole site on
the LAN unauthenticated.

#### Optional: Cloudflare Tunnel path (kept, not the default)

The `cloudflared` service is still defined in `docker-compose.yml`, gated
behind the `cloudflare` Compose profile so a bare `docker compose up -d`
never starts it — an empty `CLOUDFLARE_TUNNEL_TOKEN` would otherwise
crashloop the container on every boot. If a domain is ever registered, this
is the ready-made path back: bring it up with
`docker compose --profile cloudflare up -d` after completing the setup
below.

**In the Zero Trust dashboard** (Networks → Tunnels):

1. Create a tunnel. Choose the **Docker** connector; the dashboard shows a
   `docker run` command containing a token. Copy only the token — the compose
   file already supplies everything else — into `.env` as
   `CLOUDFLARE_TUNNEL_TOKEN`.
2. Under **Public Hostnames**, add one entry:

   | Field | Value |
   |---|---|
   | Subdomain / Domain | your `DOMAIN` |
   | Type | `HTTP` |
   | URL | `caddy:80` |

   `HTTP`, not `HTTPS`, is correct: that hop never leaves the Docker network,
   and Caddy deliberately holds no certificate (see `architecture.md` M13).
   The hostname resolves over the compose network, which is why the tunnel
   container must stay on `portfolio-net`.
3. Leave **Additional application settings → TLS → No TLS Verify** off. It is
   only relevant if you later add an origin certificate.

**In Cloudflare DNS:** creating the public hostname adds a `CNAME` to
`<tunnel-id>.cfargotunnel.com` automatically. Confirm it is **proxied**
(orange cloud). An unproxied record publishes the home IP and defeats the
entire strategy. Publish no `AAAA` record unless it is also proxied.

**Token mode means ingress lives in the dashboard, not in this repo.** That is
a deliberate trade: no credentials file on disk, at the cost of the routing
rule not being version-controlled. If a request reaches Caddy with an
unexpected `Host`, the catch-all block answers 404 — check the dashboard's
hostname entry against `DOMAIN`.

```bash
make tunnel-status
```

### 1.5 WSL2 hosts

**See `docs/SELF_HOSTING.md` §2 for the full boot chain, network-layer
diagram, and the two-separate-Tailscale-identities gotcha** — this section
covers only the setup steps; that one covers why they're needed and what's
still a genuine limitation of this hosting model.

A WSL2 distro can host this stack, but it fails differently from a normal
server: nothing here is unreachable because a port is shut, it is unreachable
because *the VM is not running*. Three things have to be true.

**systemd must be PID 1**, or `systemctl enable` is meaningless and Docker
never starts on its own. In `/etc/wsl.conf`:

```ini
[boot]
systemd=true
```

**Docker must be the distro's own `dockerd`, not Docker Desktop.** Docker
Desktop puts the daemon in a separate, Windows-managed distro that this
stack's `restart: unless-stopped` policy cannot rely on. Confirm with:

```bash
ps -p 1 -o comm=                    # -> systemd
docker info --format '{{.OperatingSystem}}'   # -> this distro, not "Docker Desktop"
```

**The stack must converge at boot, not merely restart.** Docker's restart
policy only revives containers that were running when the daemon stopped, so
a host that was shut down after a `docker compose down` comes back empty.
`/etc/systemd/system/portfolio-stack.service` closes that gap:

```ini
[Unit]
Description=CV portfolio production stack (docker compose)
Requires=docker.service
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/srv/portfolio
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose stop
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload && sudo systemctl enable portfolio-stack.service
```

#### Starting the distro after a Windows reboot

None of the above runs if Windows never starts the distro, and **WSL does not
auto-start distros**. This is the one genuinely unavoidable Windows-side step.
Register a logon task (PowerShell, as the user who owns the distro):

```powershell
$vbs = "$env:USERPROFILE\wsl-portfolio-autostart.vbs"
schtasks /Create /TN "WSL Portfolio Autostart" `
  /TR "wscript.exe `"$vbs`"" /SC ONLOGON /RL HIGHEST /F
```

where the `.vbs` runs the distro headlessly (a bare `wsl.exe` action flashes a
console window at every logon):

```vbscript
Set s = CreateObject("WScript.Shell")
s.Run "wsl.exe -d <DISTRO> -u root -e /bin/true", 0, False
```

`ONLOGON`, not `ONSTART`: WSL distros are registered per user, so a task
running as `SYSTEM` at boot either fails or starts a second, empty instance.
The consequence is that **an unattended reboot leaves the site down until
someone logs in** — if that is unacceptable, enable Windows auto-logon, or
move off WSL.

Also keep the VM from being reclaimed, in `%UserProfile%\.wslconfig`
(effective after `wsl --shutdown`):

```ini
[wsl2]
vmIdleTimeout=-1
```

#### Tunnel transport (Cloudflare path only)

Only relevant if running the optional `cloudflare` profile from §1.4 —
Tailscale Funnel doesn't have this failure mode. cloudflared prefers QUIC
(UDP 7844). WSL2's NAT layer, and plenty of consumer routers, drop or
fragment it while leaving TCP untouched — so the tunnel flaps or never
registers even though egress looks healthy. Verify the paths from the
compose network itself, not the host:

```bash
docker run --rm --network cv_resume_portfolio-net alpine \
  sh -c 'nc -z -w5 region1.v2.argotunnel.com 7844 && echo tcp-ok'
```

If `docker compose logs cloudflared` shows QUIC handshake failures, pin the
TCP fallback in `.env` — the compose file reads it:

```bash
TUNNEL_TRANSPORT_PROTOCOL=http2
```

#### What WSL2 still cannot give you

Windows sleep, hibernate, and Fast Startup all suspend the VM, and an
update-driven reboot drops the tunnel until the next logon. WSL2 is fine for
deployment testing and acceptable for a personal site; it is not equivalent to
a machine that boots unattended.

## 2. Secrets and Configuration

```bash
cp .env.example .env
chmod 600 .env
```

Fill in every value. The ones with no safe default:

| Variable | Notes |
|---|---|
| `POSTGRES_PASSWORD` | fresh random value, not the dev one |
| `SESSION_SECRET_KEY` | 64 random chars; rotating it invalidates all sessions **and** all analytics IP hashes |
| `ADMIN_PASSWORD` | seeded once, then changed |
| `NOC_DB_PASSWORD` | for the least-privilege `noc_writer` role |
| `TAILSCALE_IP` | from §1.2 — the admin site binds here and nowhere else |
| `DOMAIN` | your Funnel hostname (§1.4) — must exactly match `tailscale status --json`'s `Self.DNSName`, or Caddy's public block never matches |
| `ADMIN_ENTRY_TOKEN` | shared secret proving admin entry to the backend (`security.md` §3.1); `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `CLOUDFLARE_TUNNEL_TOKEN` | only if using the optional `cloudflare` profile from §1.4 — leave empty otherwise |
| `CONTACT_TO_EMAIL` | private destination; never goes in the frontend |
| `SMTP_PASSWORD` | Gmail **App Password**, requires 2FA on the account |
| `TRUSTED_PROXY_IPS` | leave at the compose default (`172.20.0.10`, Caddy's static address) |

Generate secrets with `openssl rand -hex 32` rather than inventing them.

**`VITE_API_URL` is deliberately not in this table.** Production hardcodes it
empty in `docker-compose.yml` so the SPA calls its own origin; a value
inherited from `.env` would bake the dev URL into the bundle.

## 3. First Deploy

Run the automated checks first — they catch the configuration mistakes that
are hardest to notice once the site is public:

```bash
make preflight
```

It verifies `.env` completeness, that no default password survives, that no
`.env` value has leaked into a repo file, that the only published port is
`<TAILSCALE_IP>:8443`, that `VITE_API_URL` is empty in the production build
args, that the Caddyfile validates and still denies all four private path
groups, and that `TAILSCALE_IP` matches this host. It changes nothing and
exits non-zero on any failure.

Then:

```bash
docker compose build
docker compose up -d postgres
docker compose run --rm backend alembic upgrade head
make noc-role-prod                # least-privilege DB role (security.md §7)
docker compose run --rm backend python -m scripts.seed
docker compose up -d
docker compose ps                 # every service healthy before proceeding

make check-smtp                   # contact relay: App Password valid?
make tunnel-status                # tunnel actually connected?
```

`make check-smtp ARGS=--send` additionally delivers one test message to
`CONTACT_TO_EMAIL`, which is the end-to-end check worth running once.

`docker compose` with no `-f` targets `docker-compose.yml`, the production
file. The dev stack requires `-f docker-compose.dev.yml` explicitly.

## 4. Verification Gates

Do not announce the site until all of these pass. Each maps to something that
has actually gone wrong in this project's history.

### 4.1 Exposure

```bash
docker compose ps --format '{{.Service}} {{.Ports}}'
```

Exactly one published port, `<TAILSCALE_IP>:8443`. Anything bound to
`0.0.0.0` is a defect — Postgres above all.

### 4.2 The admin surface is not on the public internet

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://<domain>/admin              # 404
curl -s -o /dev/null -w '%{http_code}\n' https://<domain>/api/v1/admin/analytics  # 404
curl -s -o /dev/null -w '%{http_code}\n' https://<domain>/api/v1/auth/login  # 404
curl -s -o /dev/null -w '%{http_code}\n' https://<domain>/internal/metrics   # 404
```

All four must be 404. The last is what makes `routes/internal.py`'s
"unauthenticated because Caddy never proxies it" docstring true.

Then confirm the same paths **do** work over Tailscale:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://<TAILSCALE_IP>:8443/admin    # 200
```

### 4.3 The site renders, with its fonts

Load `https://<domain>` in a browser. Headings must render in Fraunces, body in
Karla. If they fall back to a system serif/sans, the CSP is blocking Google
Fonts — check `font-src` and `style-src` in the Caddyfile. This is invisible to
`curl` and only appears in production.

Check the console for CSP violations and failed API calls. An API call to
`localhost:8000` means the frontend image was built with the wrong
`VITE_API_URL`.

### 4.4 Real visitor IPs reach the backend

The single most consequential thing to get wrong, because it degrades silently:
if every request arrives as Caddy's address, unique-visitor counts collapse to
1 **and** login rate limiting becomes one global bucket that any attacker can
exhaust for everyone.

```bash
# From two different external networks (e.g. phone on cellular, then wifi):
# load the site, then compare distinct hashes for today.
docker compose exec postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -t -c \
  "SELECT count(DISTINCT ip_hash) FROM analytics_events WHERE created_at > now() - interval '1 hour';"
```

Two visits from different networks must produce **2**, not 1.

### 4.5 Contact form

Send yourself a message from the public site. Confirm it arrives, that
`Reply-To` is the address you typed, and that hitting reply targets the sender
rather than the server. Then submit twice in a row — the second must be
rejected with 429.

### 4.6 Backups

```bash
./scripts/backup.sh
./scripts/restore.sh              # restores into a throwaway copy
```

Compare row counts, then drop the throwaway database. **A backup that has
never been restored is a hypothesis.**

### 4.7 TLS and headers

```bash
curl -sI https://<domain> | grep -iE 'strict-transport|content-security|x-frame|x-content-type'
```

The certificate is Tailscale's, provisioned automatically for the Funnel
hostname (`security.md` §2 — Caddy cannot run ACME because 80/443 are never
open at the router). Confirm with `curl -s -o /dev/null -w '%{ssl_verify_result}\n' https://<domain>` — `0` means valid.
Under the optional Cloudflare profile, the certificate is Cloudflare's instead.

## 5. Cutover

1. Run every gate in §4.
2. Walk `security.md` §13's pre-launch checklist and tick each box.
3. Load the site from a phone on **cellular**, not home wifi — this is the only
   check that proves the path works from outside the home network.
4. Change `ADMIN_PASSWORD` from its seeded value and confirm login over
   Tailscale.
5. Install the cron entries in §6.

## 6. Routine Operations

### Cron

```cron
# Backups (security.md §10)
0 3 * * *  cd /srv/portfolio && ./scripts/backup.sh >> /var/log/portfolio-backup.log 2>&1

# Restore rehearsal — quarterly, so a broken backup is found before it matters
0 4 1 */3 * cd /srv/portfolio && ./scripts/restore.sh >> /var/log/portfolio-restore-test.log 2>&1
```

Data retention needs no cron entry: the API runs it on a timer and sweeps once
at startup. To move it to cron instead, set `RETENTION_PURGE_ENABLED=false` and
add `docker compose exec -T backend python -m scripts.purge_retention`.

### Deploying a change

```bash
git pull
docker compose build
docker compose run --rm backend alembic upgrade head    # if migrations changed
docker compose up -d
docker compose ps
```

Re-run §4.1 and §4.2 after any change to the Caddyfile or either compose file.

### Watching it

- **Network Health dashboard** over Tailscale — service status, latency, host
  CPU/memory/disk, request and error rates.
- `docker compose logs -f --tail=100`
- Retention: `docker compose exec backend python -m scripts.purge_retention --dry-run`
  reports the oldest row per governed table. A steadily rising oldest-row age
  means the sweep has stopped running.

### Updates

Per `security.md` §11: `unattended-upgrades` for OS security patches; Diun to be
*notified* of new container images, then pull and redeploy deliberately. CI
fails on any new high/critical advisory, which is the earliest of the three
layers.

## 7. Rollback

The stack is stateless apart from Postgres, so rollback is usually just the
previous image.

```bash
git log --oneline -5
git checkout <previous-commit>
docker compose build && docker compose up -d
```

**Migrations are the exception.** `alembic downgrade` can be destructive. If a
release included one, prefer restoring the pre-deploy backup over downgrading:

```bash
./scripts/restore.sh --snapshot <id> --target "$POSTGRES_DB" \
  --i-understand-this-overwrites-live
```

Take a fresh backup immediately before any deploy that carries a migration.

## 8. Failure Playbook

| Symptom | Likely cause | First check |
|---|---|---|
| Site unreachable, host fine | Funnel off, or `tailscaled` down | `make funnel-status`; `systemctl status tailscaled` |
| Site unreachable, `make funnel-status` looks fine | `DOMAIN` doesn't match the Funnel hostname | Caddy's public block never matches, falls through to the 404 catch-all — compare `.env`'s `DOMAIN` against `tailscale status --json`'s `Self.DNSName` |
| Admin dashboard reachable from the internet | Funnel is serving `:8443`, not just `:443` | `tailscale funnel status`; if 8443 appears, `tailscale funnel --https=8443 off` **immediately** |
| (Cloudflare profile only) 502 / site down | tunnel container down or token invalid | `docker compose logs cloudflared`; Cloudflare dashboard shows tunnel health |
| Site loads, fonts wrong | CSP blocking Google Fonts | `font-src` / `style-src` in the Caddyfile |
| API calls fail in browser only | wrong `VITE_API_URL` baked into the image | rebuild frontend with the build arg empty |
| Unique visitors stuck at 1 | proxy headers not reaching the backend | `TRUSTED_PROXY_IPS` vs Caddy's actual address; Caddy's `header_up` line |
| Admin locked out after failed logins | expected, if the above is broken | same as previous row — the global-bucket failure |
| Contact form 503 | relay not configured | `CONTACT_TO_EMAIL` / `SMTP_USERNAME` set? |
| Contact form 502 | SMTP rejecting | Gmail App Password valid? 2FA still on? |
| NOC dashboard empty | `noc` cannot write | `docker compose logs noc` — a permission error means `make noc-role-prod` was not run |
| Disk filling | logs or retention | `docker system df`; confirm log caps and the retention sweep are running |
| Admin dashboard unreachable | Tailscale down, or `TAILSCALE_IP` changed | `tailscale status`; compare against `.env` |

---

## Open Items Before Launch

Repo-level work that remains, in dependency order:

1. **M17 (SEO/performance)** — the prerender step, per-page titles and meta,
   sitemap, OG image, real 404 status. The nginx `try_files` change and the
   Caddyfile interact, so do this before cutover rather than after.
2. **`restic` verification** — the backup scripts' Postgres round-trip is
   tested, but the restic leg has not been executed on a real repository.
3. **Public `GET` rate limiting** at the Caddy layer — the one gap left from
   M16's rate-limiting review.
4. **Cloudflare Origin Certificate** for end-to-end TLS ("Full (strict)"),
   optional hardening per `security.md` §2 — only applicable if the optional
   Cloudflare profile (§1.4) is ever adopted in place of Funnel.
