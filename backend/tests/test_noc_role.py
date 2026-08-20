"""Privilege tests for the least-privilege `noc_writer` database role (M16).

The `noc` container reaches out to the public internet on a timer, so it is
the most exposed process in the stack; docs/security.md §7 calls its sharing
of the backend's full-access credential "the single highest-value hardening
item left over." scripts/create_noc_role.sql narrows it to INSERT/DELETE on
one table, and these tests assert that it stayed narrow.

Privileges are read from PostgreSQL's own catalog via `has_table_privilege`,
so the suite needs no password and no second connection — it asks the
database what `noc_writer` is allowed to do rather than trying it.

The important test is `test_noc_writer_cannot_touch_any_other_table`, which
enumerates tables at runtime: a table added in a future migration is covered
automatically, instead of only the ones someone remembered to list here.
"""

import pytest
from sqlalchemy import text

from app.database import engine

NOC_ROLE = "noc_writer"
NOC_TABLE = "network_health_samples"


async def _fetch(sql: str, **params):
    async with engine.connect() as conn:
        return (await conn.execute(text(sql), params)).all()


async def _role_exists() -> bool:
    rows = await _fetch("SELECT 1 FROM pg_roles WHERE rolname = :role", role=NOC_ROLE)
    return bool(rows)


async def _privilege(table: str, privilege: str) -> bool:
    rows = await _fetch(
        "SELECT has_table_privilege(:role, :table, :privilege)",
        role=NOC_ROLE,
        table=table,
        privilege=privilege,
    )
    return rows[0][0]


async def _skip_unless_provisioned():
    if not await _role_exists():
        pytest.skip(
            f"{NOC_ROLE} not provisioned in this database — run `make noc-role` "
            "(scripts/create_noc_role.sql) to enable these tests"
        )


async def test_noc_writer_can_write_and_prune_its_own_table():
    """The three privileges the service actually needs: INSERT to record a
    sample, DELETE to prune past the retention window, and the SELECT that
    PostgreSQL requires for the DELETE's WHERE clause.
    """
    await _skip_unless_provisioned()

    for privilege in ("INSERT", "DELETE", "SELECT"):
        assert await _privilege(NOC_TABLE, privilege), (
            f"{NOC_ROLE} needs {privilege} on {NOC_TABLE}; noc/monitor.py cannot run without it"
        )


async def test_noc_writer_cannot_rewrite_or_wipe_its_own_table():
    """Append-and-prune only. Without UPDATE and TRUNCATE, a compromised NOC
    container cannot rewrite recorded history or erase it wholesale — it can
    only add samples and age them out.
    """
    await _skip_unless_provisioned()

    for privilege in ("UPDATE", "TRUNCATE"):
        assert not await _privilege(NOC_TABLE, privilege), (
            f"{NOC_ROLE} has {privilege} on {NOC_TABLE}; it only ever inserts and prunes"
        )


async def test_noc_writer_cannot_touch_any_other_table():
    """The core invariant, and the reason this file exists: nothing else in
    the database is reachable with this credential — not admin_users, not
    admin_sessions, not analytics_events.

    Enumerated at runtime rather than hardcoded, so a table introduced by a
    later migration is covered by this assertion the day it lands.
    """
    await _skip_unless_provisioned()

    tables = await _fetch(
        """
        SELECT tablename FROM pg_tables
        WHERE schemaname = 'public' AND tablename <> :noc_table
        ORDER BY tablename
        """,
        noc_table=NOC_TABLE,
    )
    assert tables, "expected other tables to exist — has the schema been migrated?"

    leaked = [
        (table, privilege)
        for (table,) in tables
        for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE")
        if await _privilege(table, privilege)
    ]
    assert not leaked, f"{NOC_ROLE} has privileges it should not: {leaked}"


async def test_noc_writer_cannot_create_objects_or_escalate():
    """No CREATE on the schema (so it cannot add its own tables), and none of
    the role attributes that would let it grant itself more.
    """
    await _skip_unless_provisioned()

    can_create = (
        await _fetch(
            "SELECT has_schema_privilege(:role, 'public', 'CREATE')", role=NOC_ROLE
        )
    )[0][0]
    assert not can_create, f"{NOC_ROLE} can create objects in the public schema"

    superuser, createdb, createrole, bypassrls = (
        await _fetch(
            """
            SELECT rolsuper, rolcreatedb, rolcreaterole, rolbypassrls
            FROM pg_roles WHERE rolname = :role
            """,
            role=NOC_ROLE,
        )
    )[0]
    assert not superuser, f"{NOC_ROLE} is a superuser"
    assert not createdb, f"{NOC_ROLE} can create databases"
    assert not createrole, f"{NOC_ROLE} can create roles"
    assert not bypassrls, f"{NOC_ROLE} can bypass row-level security"
