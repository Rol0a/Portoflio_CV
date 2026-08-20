"""Standalone NOC (network-operations-center) poller for the portfolio's home
server. Runs as its own container, separate from the `backend` app — see
docs/security.md for why it's isolated this way. It has no server of its own
and no listening port: it only reaches *out* (to Postgres, to the backend, to
a handful of public internet hosts) and writes what it finds into
`network_health_samples`. The admin dashboard's Network Health page reads
that table through the backend's own `/api/v1/admin/network-health` route —
this service never serves a request itself, so there's nothing here to
authenticate or expose.

Deliberately dependency-light (asyncpg, httpx, psutil — nothing else) and
runs as a non-root user with no extra Linux capabilities (see Dockerfile).
Internet reachability is measured via a plain TCP connect rather than ICMP
ping, specifically so the container never needs CAP_NET_RAW — a real,
documented trade-off, not an oversight (see docs/security.md's
least-privilege section).
"""

import asyncio
import json
import os
import time
from datetime import datetime, timezone

import asyncpg
import httpx
import psutil

INTERVAL_SECONDS = float(os.environ.get("NOC_INTERVAL_SECONDS", "30"))
BACKEND_URL = os.environ.get("NOC_BACKEND_URL", "http://backend:8000")
CADDY_URL = os.environ.get("NOC_CADDY_URL")  # unset in dev — no Caddy container there
# cloudflared's /ready endpoint (TUNNEL_METRICS in docker-compose.yml). The
# tunnel is the single path from the internet to this stack, so if it drops
# the site is offline while every other service still reports healthy —
# exactly the outage that is invisible from inside the network.
CLOUDFLARED_URL = os.environ.get("NOC_CLOUDFLARED_URL")  # unset in dev — no tunnel there
INTERNET_TARGETS = [
    t.strip() for t in os.environ.get("NOC_INTERNET_TARGETS", "1.1.1.1:443,8.8.8.8:443,9.9.9.9:443").split(",") if t.strip()
]
CONNECT_TIMEOUT_SECONDS = 2.0
RETENTION_DAYS = 7
PURGE_EVERY_N_CYCLES = 120  # ~once/hour at the default 30s interval

# Prefer the least-privilege `noc_writer` credential (M16): it may only
# INSERT/DELETE on network_health_samples, so this container — which talks to
# the public internet on a timer — cannot read admin_users or analytics_events
# even if it were compromised. Provisioned by scripts/create_noc_role.sql and
# wired in docker-compose.yml.
#
# Falls back to the backend's shared DATABASE_URL so the dev stack keeps
# working without extra setup. That fallback is a privilege escalation, so it
# announces itself at startup rather than being silent — see docs/security.md §7.
_NOC_DSN = os.environ.get("NOC_DATABASE_URL")
DATABASE_CREDENTIAL_SOURCE = "NOC_DATABASE_URL (least-privilege noc_writer)"
if not _NOC_DSN:
    _NOC_DSN = os.environ["DATABASE_URL"]
    DATABASE_CREDENTIAL_SOURCE = "DATABASE_URL (shared with backend — full table access)"

# asyncpg wants a plain postgresql:// DSN, not SQLAlchemy's postgresql+asyncpg://
RAW_DATABASE_URL = _NOC_DSN.replace("postgresql+asyncpg://", "postgresql://")

_prev_requests_total: int | None = None
_prev_errors_total: int | None = None


async def check_postgres(pool: asyncpg.Pool) -> dict:
    start = time.perf_counter()
    try:
        async with pool.acquire() as conn:
            await conn.execute("SELECT 1")
        return {"status": "up", "latency_ms": round((time.perf_counter() - start) * 1000, 1)}
    except Exception:
        return {"status": "down", "latency_ms": None}


async def check_http_service(client: httpx.AsyncClient, url: str) -> dict:
    start = time.perf_counter()
    try:
        response = await client.get(url, timeout=CONNECT_TIMEOUT_SECONDS)
        latency_ms = round((time.perf_counter() - start) * 1000, 1)
        return {"status": "up" if response.status_code < 500 else "degraded", "latency_ms": latency_ms}
    except Exception:
        return {"status": "down", "latency_ms": None}


async def check_backend_metrics(client: httpx.AsyncClient) -> tuple[dict, int | None, int | None]:
    global _prev_requests_total, _prev_errors_total
    try:
        response = await client.get(f"{BACKEND_URL}/api/v1/health", timeout=CONNECT_TIMEOUT_SECONDS)
        response.raise_for_status()
        start = time.perf_counter()
        metrics_response = await client.get(f"{BACKEND_URL}/internal/metrics", timeout=CONNECT_TIMEOUT_SECONDS)
        latency_ms = round((time.perf_counter() - start) * 1000, 1)
        metrics_response.raise_for_status()
        metrics = metrics_response.json()
    except Exception:
        return {"status": "down", "latency_ms": None}, None, None

    requests_total = metrics.get("requests_total")
    errors_total = metrics.get("errors_total")

    requests_delta = None
    errors_delta = None
    if requests_total is not None:
        if _prev_requests_total is not None and requests_total >= _prev_requests_total:
            requests_delta = requests_total - _prev_requests_total
        else:
            requests_delta = 0  # first sample, or the backend restarted and counters reset
        _prev_requests_total = requests_total
    if errors_total is not None:
        if _prev_errors_total is not None and errors_total >= _prev_errors_total:
            errors_delta = errors_total - _prev_errors_total
        else:
            errors_delta = 0
        _prev_errors_total = errors_total

    return {"status": "up", "latency_ms": latency_ms}, requests_delta, errors_delta


async def check_tcp_target(target: str) -> dict:
    host, _, port_str = target.partition(":")
    port = int(port_str) if port_str else 443
    start = time.perf_counter()
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=CONNECT_TIMEOUT_SECONDS
        )
        writer.close()
        await writer.wait_closed()
        return {"reachable": True, "latency_ms": round((time.perf_counter() - start) * 1000, 1)}
    except Exception:
        return {"reachable": False, "latency_ms": None}


def read_host_resources() -> tuple[float | None, float | None, float | None]:
    try:
        cpu = psutil.cpu_percent(interval=0.5)
        memory = psutil.virtual_memory().percent
        disk = psutil.disk_usage("/").percent
        return cpu, memory, disk
    except Exception:
        return None, None, None


async def run_cycle(pool: asyncpg.Pool, client: httpx.AsyncClient) -> None:
    services: dict[str, dict] = {}
    services["postgres"] = await check_postgres(pool)
    services["backend"], requests_count, errors_count = await check_backend_metrics(client)
    if CADDY_URL:
        services["caddy"] = await check_http_service(client, CADDY_URL)
    if CLOUDFLARED_URL:
        services["cloudflared"] = await check_http_service(client, CLOUDFLARED_URL)

    target_results = await asyncio.gather(*(check_tcp_target(target) for target in INTERNET_TARGETS))
    internet_targets = dict(zip(INTERNET_TARGETS, target_results))
    reachable_count = sum(1 for result in target_results if result["reachable"])
    packet_loss_pct = (
        round((1 - reachable_count / len(target_results)) * 100, 1) if target_results else None
    )

    cpu_percent, memory_percent, disk_percent = await asyncio.to_thread(read_host_resources)

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO network_health_samples
                (sampled_at, services, internet_targets, packet_loss_pct,
                 cpu_percent, memory_percent, disk_percent, requests_count, errors_count)
            VALUES ($1, $2::jsonb, $3::jsonb, $4, $5, $6, $7, $8, $9)
            """,
            datetime.now(timezone.utc),
            json.dumps(services),
            json.dumps(internet_targets),
            packet_loss_pct,
            cpu_percent,
            memory_percent,
            disk_percent,
            requests_count,
            errors_count,
        )

    print(
        f"[noc] sampled: services={ {k: v['status'] for k, v in services.items()} } "
        f"packet_loss={packet_loss_pct}% cpu={cpu_percent}% mem={memory_percent}% disk={disk_percent}%",
        flush=True,
    )


async def purge_old_samples(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        deleted = await conn.execute(
            "DELETE FROM network_health_samples WHERE sampled_at < now() - make_interval(days => $1)",
            RETENTION_DAYS,
        )
    print(f"[noc] retention purge: {deleted}", flush=True)


async def main() -> None:
    # Never log the DSN itself — it carries the password.
    print(f"[noc] database credential: {DATABASE_CREDENTIAL_SOURCE}", flush=True)
    pool = await asyncpg.create_pool(RAW_DATABASE_URL, min_size=1, max_size=2)
    cycle = 0
    async with httpx.AsyncClient() as client:
        try:
            while True:
                cycle += 1
                try:
                    await run_cycle(pool, client)
                except Exception as exc:
                    print(f"[noc] cycle failed: {exc!r}", flush=True)

                if cycle % PURGE_EVERY_N_CYCLES == 0:
                    try:
                        await purge_old_samples(pool)
                    except Exception as exc:
                        print(f"[noc] purge failed: {exc!r}", flush=True)

                await asyncio.sleep(INTERVAL_SECONDS)
        finally:
            await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
