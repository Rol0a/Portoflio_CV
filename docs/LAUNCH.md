# Launch — the short version

The one-page answer to "how do I start my website." For the reasoning behind
any of it, see [`SELF_HOSTING.md`](SELF_HOSTING.md) (operator's manual),
[`deployment.md`](deployment.md) (full runbook), and
[`security.md`](security.md) (why the exposure model looks like this).

---

## 1. The thing that trips everyone up

There are **two stacks**, and they are not interchangeable:

| | Dev stack | Production stack |
|---|---|---|
| File | `docker-compose.dev.yml` | `docker-compose.yml` (the default) |
| Start with | `make dev` | `docker compose up -d` |
| Includes Caddy? | **No** | **Yes** |
| Reachable at | `localhost:5173` only | your Tailscale URL |
| Public? | Never | Yes, via Tailscale Funnel |

**Only the production stack is reachable over Tailscale.** The dev stack has
no Caddy, so nothing listens on `127.0.0.1:8080`, which is exactly where
Tailscale Funnel forwards traffic. Run the dev stack and the tailnet URL goes
dead — not because Funnel broke, but because there is nothing behind it.

**They also cannot run at the same time.** Both compose files live in the same
directory, so Docker gives them the same project name (`cv_resume`) and the
same container names (`cv_resume-backend-1`, …). Starting one while the other
runs produces "orphan container" warnings and network-removal errors. Always
bring one down before bringing the other up.

---

## 2. Launch the real site (what you want most of the time)

```bash
cd ~/CV_resume
docker compose -f docker-compose.dev.yml down   # only if the dev stack is up
docker compose up -d                            # add --build after code changes
docker compose ps                               # every service Up / healthy
```

Then confirm the public entrance is still published:

```bash
make funnel-status      # should print: https://roloa.tailb961fd.ts.net
make funnel             # only if it printed nothing — re-publishes it
```

That's it. `make funnel` is persistent — `tailscaled` stores it in its own
state and re-establishes it after a reboot, so it is normally a one-time
command, not part of every launch.

### Where the site lives

| What | URL |
|---|---|
| Public site | `https://roloa.tailb961fd.ts.net` |
| Admin dashboard | `https://roloa.tailb961fd.ts.net:8443/admin` |

The admin URL only resolves from a device logged into the **same Tailscale
account**. Three details are load-bearing: the **hostname** (not the raw IP —
the TLS cert is hostname-bound), **`https://`** (not `http://`), and the
trailing **`/admin`** (the bare hostname loads the public homepage, which is
correct behaviour, not a bug). See `SELF_HOSTING.md` §6.1.

---

## 3. Local development instead

```bash
cd ~/CV_resume
docker compose down     # only if the production stack is up
make dev                # or `make dev-build` after dependency changes
```

Frontend `http://localhost:5173`, backend `http://localhost:8000`,
Postgres `localhost:5432`. Nothing here is public, and the tailnet URL will be
down for as long as this is the stack that's running.

---

## 4. After a database reset (only when the DB is empty)

The `make db-*` targets in the [`Makefile`](../Makefile) all point at the
**dev** compose file. For production, run the same commands against the
default stack directly:

```bash
docker compose exec backend alembic upgrade head       # create the schema
docker compose exec backend python -m scripts.seed     # projects, skills, admin user
NOC_DB_PASSWORD=$(grep '^NOC_DB_PASSWORD=' .env | cut -d= -f2-) make noc-role-prod
```

That last line is needed because `make noc-role-prod` reads `NOC_DB_PASSWORD`
from the **shell**, not from `.env`. Skip it and the `noc` container crashloops
on `password authentication failed for user "noc_writer"` while everything
else looks fine.

**Postgres only reads `POSTGRES_PASSWORD` when it initialises an empty data
volume.** If `.env` is changed after the volume exists, the old password stays
in force and every connection fails with `password authentication failed for
user "portfolio"`. The fix is to recreate the volume — which **destroys that
database**:

```bash
docker compose down
docker volume rm cv_resume_pgdata        # PRODUCTION data. Back up first.
# cv_resume_pgdata_dev is the dev one — throwaway seed data, safe to drop.
docker compose up -d
# …then the three commands above.
```

---

## 5. Verify it actually works

```bash
make preflight                                   # config + exposure audit; aim for 0 failures
curl -I https://roloa.tailb961fd.ts.net          # expect 200 from outside
curl -s http://localhost:8000/api/v1/health      # dev stack only
docker compose logs -f --tail=50 backend
```

`make preflight` is the real "is this ready" gate — it checks exposure,
the Funnel binding, firewall state, secret containment, and the admin cert's
expiry in one pass.

The strongest check is the one this project's own rules ask for: load the
public URL **from a phone on cellular data**, off the home network entirely.

---

## 6. Turning it off

| Goal | Command |
|---|---|
| Off the internet, admin still works | `make funnel-off` |
| Stop everything, keep data | `docker compose down` |
| Stop it coming back after a reboot | `sudo systemctl disable portfolio-stack.service` |

`SELF_HOSTING.md` §5 has the full graduated list, including the destructive
`down -v` and what it costs.

---

## 7. When the site is dark

Work down this list — it is ordered by how often each one is the answer.

1. **Is the production stack up?** `docker compose ps`. If it shows nothing,
   or shows the dev containers, that's the problem — see §2.
2. **Is Funnel published?** `make funnel-status`. Empty output means the
   public entrance is gone; `make funnel` restores it.
3. **Is anything listening on 8080?** `ss -ltn | grep 8080`. Funnel forwards
   there; if it's empty, Caddy isn't running. Expect exactly two lines when
   healthy — `127.0.0.1:8080` and `100.124.209.87:8443`, never `0.0.0.0`.

   **`curl http://127.0.0.1:8080/` returning 404 is normal — don't chase it.**
   The public Caddy block matches on the `$DOMAIN` hostname, so a request
   arriving with `Host: 127.0.0.1` matches no site block and gets a 404. Real
   traffic through Funnel carries the correct `Host` and gets a 200. To test
   locally the way Funnel does:
   ```bash
   curl -s -o /dev/null -w '%{http_code}\n' -H 'Host: roloa.tailb961fd.ts.net' http://127.0.0.1:8080/
   ```
4. **Is the distro even awake?** WSL2 does not auto-start on boot — it starts
   when you log into Windows (`SELF_HOSTING.md` §2.3). A machine sitting at
   the lock screen serves nothing.
5. **Page loads but shows no projects/skills?** That's the database, not the
   network. Check `docker compose logs backend` for
   `password authentication failed` (→ §4) or `relation ... does not exist`
   (→ migrations never ran, also §4).

---

## 8. Boot persistence, already configured

`portfolio-stack.service` runs `docker compose up -d` at every distro boot, so
a cold start converges the production stack with no manual step:

```bash
systemctl status portfolio-stack.service
```

Because it targets the default compose file, **a reboot always comes back on
the production stack** — even if you were last working in dev.
