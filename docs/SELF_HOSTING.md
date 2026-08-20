# Self-Hosting Guide

This is the operator's manual: how this deployment actually works end to end,
how to bring it up and take it down, what's left to make administration fully
usable, how to reason about what this stack can and can't reach on your
machine, and precisely how a request travels from the public internet down
through Windows and into a container.

It complements, and deliberately doesn't repeat, three existing documents:

- **`architecture.md`** — application design, database schema, API surface.
- **`security.md`** — *why* the exposure model looks like this, tool by tool,
  with the full defence-in-depth reasoning.
- **`deployment.md`** — the step-by-step runbook, verification gates, and
  failure playbook.

Read those for the reasoning. This one is for orientation, operation, and the
two things they don't fully cover: the WSL2→Windows boot chain, and what this
stack can reach on your filesystem.

---

## Table of Contents

1. [The whole chain, in one picture](#1-the-whole-chain-in-one-picture)
2. [True hosting: Windows → WSL2 → Linux → Docker](#2-true-hosting-windows--wsl2--linux--docker)
3. [How the self-hosting is actually implemented](#3-how-the-self-hosting-is-actually-implemented)
4. [Setting it up from a fresh clone](#4-setting-it-up-from-a-fresh-clone)
5. [Turning it off](#5-turning-it-off)
6. [Next steps: admin access and services](#6-next-steps-admin-access-and-services)
7. [Reducing what this stack can reach on your computer](#7-reducing-what-this-stack-can-reach-on-your-computer)
8. [Command reference](#8-command-reference)

---

## 1. The whole chain, in one picture

Two independent paths reach this stack — deliberately never the same one:

```
PUBLIC PATH (anyone on the internet)
──────────────────────────────────────────────────────────────────────
Visitor
    │  HTTPS, TLS terminated by Tailscale
    ▼
Tailscale Funnel ingress        ← no inbound port ever opened at home
    │  outbound connection held open by tailscaled, running on the host
    ▼
127.0.0.1:8080                  ← Caddy's public block, host LOOPBACK only
    │  (Docker port publish, inside the WSL2 VM)
    ▼
caddy:80  (container, public site block)
    │
    ├─ /api/*  → backend:8000   (admin/auth/internal paths 404 here)
    └─ else    → frontend:80

ADMIN PATH (only devices on your tailnet)
──────────────────────────────────────────────────────────────────────
Your phone/laptop, logged into the same Tailscale account
    │  WireGuard, encrypted at the transport layer
    ▼
100.124.209.87:8443             ← Caddy's admin block, tailnet-address only
    │
    ▼
caddy:8443  (container, admin site block — serves everything)
    │
    ├─ /api/*  → backend:8000
    └─ else    → frontend:80
```

Both paths converge on the same `backend` and `frontend` containers — there
is one application, reached two different ways with two different trust
levels. `postgres` and `noc` are reachable from neither path directly; they
only ever talk to other containers on `portfolio-net`.

---

## 2. True hosting: Windows → WSL2 → Linux → Docker

This is not a VPS, a cloud instance, or a Raspberry Pi. It is a laptop/
desktop running Windows, and every layer below matters for understanding
why the site stays up — and when it doesn't.

### 2.1 The layers, outside in

```
┌─────────────────────────────────────────────────────────────────┐
│ Windows 11 (the physical machine)                                │
│                                                                    │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ Hyper-V-backed WSL2 virtual machine                         │  │
│  │  Its own kernel, its own virtual NIC (172.17.x.x/20 —       │  │
│  │  reassigned on every VM restart, never hardcode it)          │  │
│  │                                                               │  │
│  │  ┌─────────────────────────────────────────────────────┐   │  │
│  │  │ Fedora Linux 43 (WSL) distro                          │   │  │
│  │  │  systemd is PID 1 (requires /etc/wsl.conf's           │   │  │
│  │  │  [boot] systemd=true — WSL does NOT do this by         │   │  │
│  │  │  default)                                              │   │  │
│  │  │                                                         │   │  │
│  │  │  systemd starts:                                       │   │  │
│  │  │   • docker.service   → the distro's OWN dockerd,       │   │  │
│  │  │                        not Docker Desktop               │   │  │
│  │  │   • tailscaled.service → this distro's own Tailscale   │   │  │
│  │  │                          node (100.124.209.87)          │   │  │
│  │  │   • portfolio-stack.service → runs `docker compose      │   │  │
│  │  │     up -d`, converging the whole stack even after a     │   │  │
│  │  │     hard shutdown                                       │   │  │
│  │  │                                                         │   │  │
│  │  │   ┌───────────────────────────────────────────────┐   │   │  │
│  │  │   │ Docker bridge networks                          │   │   │  │
│  │  │   │  docker0        172.18.0.0/16  (Docker default)│   │   │  │
│  │  │   │  portfolio-net  172.20.0.0/16  (this project,   │   │   │  │
│  │  │   │                 PINNED so Caddy is always        │   │   │  │
│  │  │   │                 172.20.0.10)                     │   │   │  │
│  │  │   │   → postgres, backend, frontend, caddy, noc      │   │   │  │
│  │  │   └───────────────────────────────────────────────┘   │   │  │
│  │  └─────────────────────────────────────────────────────┘   │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

Every arrow above is a real, separate network boundary. A packet from a
visitor crosses **five** of them (Tailscale ingress → Hyper-V virtual
switch → WSL2 VM's NAT → `docker0`/`portfolio-net` bridge → the container's
own network namespace) before it reaches application code. None of them are
port-forwarded from the Windows host — the only thing making any of this
reachable from outside is Tailscale Funnel's *outbound* connection, made
from inside the distro.

### 2.2 Two separate Tailscale identities — don't confuse them

`tailscale status` on this machine shows two nodes, because Tailscale is
installed **twice**, once on each side of the WSL2 boundary:

| Node | Hostname | Address | Runs where | Used for |
|---|---|---|---|---|
| Linux node | `roloa` | `100.124.209.87` | **Inside the WSL2 distro** | Everything in this doc — Funnel, the admin Caddy block, `make funnel*` |
| Windows node | `roloa-1` | `100.80.250.5` | The Windows host itself | Unrelated to this deployment |

If you're troubleshooting Funnel or the admin dashboard and things don't
line up, confirm you're looking at the Linux node's status — run `tailscale
status` **from inside the WSL2 shell**, not from a Windows terminal.

### 2.3 The boot chain, start to finish

1. **Windows boots.** WSL2 distros do **not** auto-start — this is a
   platform limitation, not a configuration gap.
2. **You log into Windows.** A scheduled task (`WSL Portfolio Autostart`,
   trigger `AtLogOn`) fires and runs a hidden VBScript:
   ```vbscript
   Set s = CreateObject("WScript.Shell")
   s.Run "wsl.exe -d FedoraLinux-43 -u root -e /bin/true", 0, False
   ```
   This just needs to *touch* the distro — `wsl.exe` starting it at all is
   enough to bring the VM and systemd up; the `/bin/true` payload is
   deliberately a no-op.
3. **The WSL2 VM starts**, Hyper-V allocates it, and `systemd` becomes PID 1
   inside Fedora (confirmed: `ps -p 1 -o comm=` → `systemd`).
4. **systemd starts `docker.service`, `tailscaled.service`, and
   `portfolio-stack.service`** in dependency order. The last one runs
   `docker compose up -d`, which converges every container to the state
   defined in `docker-compose.yml` — this is what makes a *cold* boot
   recover the site, not just a container restart.
5. **`tailscaled` reads Funnel's config from its own persisted state** (not
   from this repo, not from `.env`) and re-establishes the outbound
   connection to Tailscale's ingress. Verified this session: restarting
   `tailscaled` brought Funnel back with zero manual steps.
6. **The site is live**, with no further action, at whatever URL `make
   funnel-status` reports.

### 2.4 What keeps it up — and what still doesn't

**Keeping it up, already configured:**

| Setting | Where | Effect |
|---|---|---|
| `vmIdleTimeout=-1` | `%UserProfile%\.wslconfig` (Windows side) | Stops WSL2 from tearing the VM down after a period of inactivity — the default behaviour would silently kill the tunnel |
| `WSL Portfolio Autostart` scheduled task | Windows Task Scheduler, trigger `AtLogOn` | The one unavoidable manual step WSL2 imposes — see below |
| AC sleep disabled | Windows Power Options | Windows itself won't suspend, which would suspend the VM with it |
| `portfolio-stack.service` enabled | systemd inside the distro | Converges the stack at every distro boot |
| `tailscaled` enabled | systemd inside the distro | Funnel config survives a daemon or VM restart |

**Honest limitations — this is not equivalent to a machine that boots
unattended:**

- **The scheduled task fires on *logon*, not on boot.** If Windows restarts
  and nobody logs in, the distro never starts and the site stays down until
  someone does. Fixing this fully means either enabling Windows auto-logon
  (a real trade-off: anyone with physical access reaches your desktop
  without a password) or moving to always-on hardware.
- **Sleep, hibernate, and laptop lid-close all suspend the VM** regardless
  of `vmIdleTimeout`, because they suspend the whole Windows host. AC sleep
  is disabled; a laptop's lid-close behaviour is a separate Windows setting,
  worth checking if this runs on a laptop.
- **A Windows Update-driven forced reboot** behaves like any other reboot —
  covered if you're logged back in promptly, not covered if the machine sits
  at the lock screen for a day.

None of this is a defect in the setup; it's the genuine ceiling of running a
public service from a WSL2 distro on a personal machine rather than a
server. `docs/deployment.md` §1.5 calls this the same way: "acceptable for a
personal site; it is not equivalent to a machine that boots unattended."

---

## 3. How the self-hosting is actually implemented

The full reasoning lives in `security.md`; this is the shape of it.

### 3.1 Two Caddy site blocks, two trust levels

`infrastructure/caddy/Caddyfile` defines a **public** block (matches
`$DOMAIN`, published to host loopback only, reached by Funnel) and an
**admin** block (`:8443`, published only on the host's Tailscale address).
The public block explicitly 404s `/internal/*`, `/api/v1/admin/*`,
`/api/v1/auth/*`, and `/admin*` — the admin surface is never proxied to the
public path at all, not merely gated behind a login screen.

### 3.2 The backend enforces the same boundary a second time

`backend/app/middleware/exposure.py` doesn't trust Caddy alone — if a
`handle` block were ever dropped, or something got repointed straight at
`backend:8000`, the backend still refuses the request. Three independent
signals, checked in this order:

1. **Tailscale's own `Tailscale-Funnel-Request` header.** Set by Tailscale
   on every public-ingress request and overwritten if a client tries to
   forge it — verified empirically against the live ingress. Any such
   request to an admin or internal path is refused outright, and this rule
   wins even over a *correct* admin token, because it's the one signal this
   project doesn't generate itself.
2. **`/internal/*` requires an unproxied, in-network caller.** The `noc`
   service is the only legitimate caller, and it never goes through a
   proxy, so any request carrying `X-Forwarded-For` at all is refused.
3. **Admin/auth surfaces require a matching `X-Portfolio-Entry` marker**
   on any request that arrived through a proxy. Caddy's public block stamps
   `public`; its admin block stamps `$ADMIN_ENTRY_TOKEN`. Both `header_up`
   directives *overwrite* rather than append, so a visitor cannot forge
   this value through the public path.

### 3.3 The analytics endpoint accepts performance data only

`POST /api/v1/analytics/events` is public and unauthenticated by design —
that's what a tracking beacon is. `backend/app/schemas/analytics.py`
allowlists exactly four metadata keys (`path`, `from`, `to`, `link`), strips
query strings and fragments from paths before storing them, and bounds
`session_id`/`project_slug` to charsets that cannot carry an email address
or free text. Anything else is silently dropped, not rejected — a beacon
can't react to a 4xx, so the countable part of the event is kept and the
rest never reaches the database. Verified live: a payload carrying an email
address and free text stored only `{"path": "/contact"}`.

### 3.4 The real visitor IP survives five network hops

Both analytics (unique-visitor counting) and login rate-limiting depend on
seeing the visitor's actual IP, not a proxy's. Tailscale Funnel overwrites
`X-Forwarded-For` with the true client address before the request reaches
this host; Caddy pins that value forward (rather than letting
`reverse_proxy` append its own hop, which would resolve to the Docker
gateway instead); the backend's `ProxyHeadersMiddleware` trusts only
Caddy's own pinned address (`172.20.0.10`). Verified end to end: an event
posted through the public Funnel URL stored an `ip_hash` matching
`sha256(<real client IP>:<date>:<secret>)`.

---

## 4. Setting it up from a fresh clone

```bash
# 1. Prerequisites, once per host
#    - systemd=true in /etc/wsl.conf, then `wsl --shutdown` from Windows
#    - Fedora's own dockerd running (not Docker Desktop):
docker info --format '{{.OperatingSystem}}'   # must NOT say "Docker Desktop"
#    - Tailscale installed and logged in, Funnel enabled once for the
#      tailnet at https://login.tailscale.com/f/funnel (a one-time,
#      account-level toggle — the CLI will print this URL if it's off)
sudo tailscale set --operator=$USER           # lets `tailscale funnel`
                                               # run without sudo

# 2. Clone and configure
git clone <this repo> && cd CV_resume
cp .env.example .env
chmod 600 .env
# Fill in every value .env.example describes — POSTGRES_PASSWORD,
# SESSION_SECRET_KEY, ADMIN_USERNAME/PASSWORD, DOMAIN (your tailnet
# hostname, e.g. roloa.tailb961fd.ts.net — find it with
# `tailscale status --json | python3 -c "import json,sys;
#  print(json.load(sys.stdin)['Self']['DNSName'])"`),
# TAILSCALE_IP (`tailscale ip -4`), ADMIN_ENTRY_TOKEN
# (`python3 -c "import secrets; print(secrets.token_hex(32))"` — this
# host has no `openssl`), NOC_DB_PASSWORD.

# 3. Bring the stack up
docker compose up -d --build
make noc-role-prod          # provisions the least-privilege NOC database role

# 4. Verify configuration before going public
make preflight               # must reach 0 failures

# 5. Publish it
make funnel                  # tailscale funnel --bg --https=443 http://127.0.0.1:8080

# 6. Make it survive a reboot
sudo systemctl daemon-reload
sudo systemctl enable --now portfolio-stack.service
#    …and register the Windows scheduled task from §2.3 if this is WSL2.
```

`make preflight` is the actual source of truth for "is this ready" — it
checks configuration, exposure, the Funnel binding, firewall state, and
secret containment in one pass. Don't skip it.

---

## 5. Turning it off

"Turn it off" means different things depending on how far you want to go.
Pick the level you actually need — most of the time it's Level 1.

| Level | What it does | Command | Reversible how |
|---|---|---|---|
| **1. Off the internet, still running locally** | Removes the public entrance. Admin access over Tailscale is unaffected. Containers keep running. | `make funnel-off` | `make funnel` |
| **2. Stop the containers** | Nothing runs, nothing is reachable at all, data is untouched. | `docker compose down` (or `make prod-down`) | `docker compose up -d` |
| **3. Stop it auto-starting on boot** | Level 2, plus a reboot won't bring it back. | `sudo systemctl disable portfolio-stack.service` | `sudo systemctl enable portfolio-stack.service` |
| **4. Full teardown — destroys data** | Removes containers, images, **and named volumes** (`pgdata`, `caddy_data`, `caddy_config`). The database is gone. | `docker compose down -v` | **Not reversible without a backup.** Never run this without confirming `scripts/backup.sh` has run recently. |

For a WSL2 host specifically, there's a fifth option outside Docker
entirely: removing the `WSL Portfolio Autostart` scheduled task in Windows
stops the distro itself from starting at logon, which stops everything
transitively — but also stops any other work you do in this distro, so it's
rarely what you actually want. Level 3 is the equivalent scoped to just
this project.

---

## 6. Next steps: admin access and services

### 6.1 Admin access already works today

From any device logged into the same Tailscale account:

```
http://roloa.tailb961fd.ts.net:8443
```

(or the raw tailnet IP — `http://100.124.209.87:8443`; MagicDNS just gives
the name a friendlier form). Plain `http://`, not `https://` — this is
correct: WireGuard already encrypts the tailnet transport, so Caddy's admin
block deliberately doesn't hold its own TLS certificate for it.

Log in with `ADMIN_USERNAME` / `ADMIN_PASSWORD` from `.env`. A row already
exists in `admin_users`, seeded via `make db-seed` → `scripts/seed.py`.

**Rotate the seeded password before treating this as done.** There is
currently **no in-app password-change flow** — `scripts/seed.py` only
creates the row once (`if existing is not None: return`), so editing
`ADMIN_PASSWORD` in `.env` and re-seeding does **nothing** to an
already-seeded user. To actually rotate it:

```bash
# Generate a bcrypt hash the same way the app does:
NEW_HASH=$(docker compose exec -T backend python -c \
  "from app.services.auth_service import hash_password; print(hash_password('<new password here>'))")

# Write it directly:
docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -c "UPDATE admin_users SET password_hash = '$NEW_HASH' WHERE username = '<username>';"
```

This gap — no self-service rotation, no forgot-password path — is worth
treating as a real backlog item, not just an operational footnote, if this
ever needs to be handed to anyone besides you.

### 6.2 What's still needed for "services fully available"

In rough priority order, from the last two working sessions' audits:

1. **Backup schedule + a tested restore. This is the largest open gap.**
   `restic` is installed and `scripts/backup.sh`/`scripts/restore.sh` exist,
   but the nightly cron isn't confirmed running and the restore path has
   never actually been exercised. A corrupted volume today would be
   unrecoverable. Verify with:
   ```bash
   crontab -l | grep restic          # is it actually scheduled?
   ./scripts/backup.sh                # run it once by hand
   ./scripts/restore.sh <snapshot-id> # into a throwaway database, per
                                       # deployment.md §4.6
   ```
2. **OS security patching.** This host is Fedora, so the Debian-oriented
   `unattended-upgrades` in `security.md` §11 doesn't apply — the
   equivalent is `dnf-automatic`:
   ```bash
   sudo dnf install -y dnf-automatic
   sudo systemctl enable --now dnf-automatic-install.timer
   ```
3. **Container image update notifications.** `security.md` §11 recommends
   Diun; not yet installed.
4. **Two known application bugs, unrelated to hosting:** broken project
   hero images (missing `/uploads/*` route + unseeded images) and two
   moderate `react-router` CVEs needing a deliberate major-version bump.
   Both are tracked in `docs/SESSION_STATE.md`.

---

## 7. Reducing what this stack can reach on your computer

This question has two genuinely different answers depending on what
"this stack" means — the containers, or the WSL2 environment they run in.
Conflating them either overstates the risk or misses a real one, so they're
addressed separately.

### 7.1 What the containers can reach: audited, and deliberately narrow

Checked directly against the running configuration, not assumed:

- **No container mounts the Docker socket.** This is the single most common
  way a container "escapes" to full host control — a container with
  `/var/run/docker.sock` mounted can launch new containers with arbitrary
  privileges, including a bind mount of `/`. Nothing here does this. Keep
  it that way; it's the one rule in this whole document worth never
  making an exception to.
- **No bind mount reaches outside the repository.** The only host paths
  mounted into any production container are `./infrastructure/caddy/Caddyfile`
  (read-only) and `./scripts` (read-only). Everything else — Postgres data,
  Caddy's TLS state — lives in named Docker volumes, which are Docker's own
  managed storage, not a path on your filesystem you'd stumble into.
- **Two of five services run as a non-root user inside the container**
  (`backend` as `appuser`, `noc` as `noc`). The other three (`frontend`,
  `caddy`, `postgres`) run as their base images' own root — but container
  root is namespaced by the Linux kernel away from host root regardless,
  and none of the three has a bind mount to abuse even if that boundary
  were somehow crossed.
- **Found and fixed this session:** none of the three services had a
  `.dockerignore`. An earlier round of ad-hoc test containers (bind-mounted
  to this repo, run as root, to work around a missing `pytest` in the
  production image) had left root-owned `__pycache__`/`.pytest_cache`
  directories on the host — and without a `.dockerignore`, the next
  `docker build` picked them up via `COPY . .` and baked them into the
  production image, owned by root, sitting inside a tree meant to be
  entirely `appuser`'s. Added `.dockerignore` to all three services,
  cleaned the stray host artifacts, and rebuilt — confirmed clean.
  **The lesson generalizes:** without a `.dockerignore`, a build context
  includes literally everything under that directory at build time,
  including anything else that happens to be lying around. Keep one
  current as the project grows.

**A further hardening step, not yet applied — worth knowing the cost of
before doing it:** only `noc` runs `read_only: true` today. Extending that
to `backend`, `frontend`, and `caddy` would mean a compromised process in
any of them literally cannot write to its own container filesystem, which
closes off a class of attack (dropping a webshell, modifying served files)
even if application code were exploited. It isn't free — each service needs
an explicit `tmpfs:` mount for whatever it writes at runtime (`frontend`'s
nginx needs `/var/cache/nginx` and `/var/run`; `caddy` may need scratch
space beyond its already-volumed `/data`/`/config`), so it needs to be
tested against a real request, not just switched on.

### 7.2 What WSL2 itself can reach — a different, wider question

This is **not** a Docker configuration issue, and no change to this
project's code affects it. It's how WSL2 works by default:

```
C:\ on /mnt/c type 9p (rw,...,uid=1000,gid=1000,...)
```

The WSL2 distro **automounts the entire Windows C: drive, read-write**, for
any process running directly in the distro's shell as your user — that
includes an ordinary terminal, a coding assistant operating in this
environment, or anything else you run here that isn't inside a container.
**None of the containers in this stack have this mount** — verified, no
container config references `/mnt` anywhere — so the deployed application
itself cannot reach your Windows files through any path this project
controls. The exposure that exists is a property of the distro you're
working in, independent of anything documented in §7.1.

Three honest options, in order of how disruptive they are:

1. **Leave it as-is (the reasonable default).** Nothing in this deployment
   uses `/mnt/c`, and WSL2's file-sharing is genuinely useful for normal
   development — editing this repo from a Windows editor, moving files
   between the two, etc. Restricting it trades that away for a risk that,
   for this project specifically, isn't live.
2. **Make Windows files read-only from inside the distro.** In
   `/etc/wsl.conf`:
   ```ini
   [automount]
   options = "ro"
   ```
   Everything under `/mnt/*` becomes readable but not writable from any WSL2
   process. This is the middle ground — it doesn't break reading files for
   normal workflows, but nothing running in the distro (a compromised
   process, an over-eager script) could modify anything on the Windows side.
   **Not yet applied or tested here** — deliberately, since testing it
   requires `wsl --shutdown`, which would take the site offline until the
   next boot trigger fires. Try it on a maintenance window, not casually.
3. **Disable automount entirely.** `[automount] enabled = false` — the most
   restrictive option, and the one most likely to break something you
   actually use (VS Code's Remote-WSL Windows-file access, anything that
   expects `/mnt/c` to exist). Only worth it if option 2 doesn't feel like
   enough.

Both config changes take effect only after `wsl --shutdown` from a Windows
terminal (not from inside the distro) followed by restarting the distro —
which, per §2.3, restarting means either logging back in (fires the
scheduled task) or running `wsl.exe -d FedoraLinux-43` by hand.

---

## 8. Command reference

```bash
# Setup / verification
docker compose up -d --build   # build and start everything
make preflight                  # the actual "is this ready" check
make noc-role-prod              # provision the least-privilege NOC role

# Public ingress
make funnel                     # publish the site (443 → 127.0.0.1:8080)
make funnel-status              # what's currently published
make funnel-off                 # take the site off the internet

# Turning things off (see §5 for the full graduated list)
docker compose down             # stop everything, keep data
docker compose down -v          # stop everything, DELETE VOLUMES — destructive

# Boot persistence
sudo systemctl enable --now portfolio-stack.service
sudo systemctl status portfolio-stack.service

# Host hardening (dry-run by default)
make harden                     # preview firewall/fail2ban changes
make harden-apply               # apply them

# Day to day
docker compose ps               # what's running
docker compose logs -f --tail=100 <service>
make prod-logs                  # same, for everything
make tunnel-status              # only meaningful under --profile cloudflare
```
