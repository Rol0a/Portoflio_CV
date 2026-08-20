-- Least-privilege database role for the standalone `noc` service (M16).
--
-- docs/security.md §7 calls the shared credential "the single highest-value
-- hardening item left over" from the NOC build: `noc` connects with the
-- backend's own DATABASE_URL, which owns every table in the database, while
-- all it actually does is INSERT samples and prune old ones. A container that
-- reaches out to the public internet on a timer should not hold a credential
-- that can read admin_users or analytics_events.
--
-- Run once per deployment, and again to rotate the password:
--     make noc-role                       (dev)
--     psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
--          -v noc_password="$NOC_DB_PASSWORD" -v db_name="$POSTGRES_DB" \
--          -f scripts/create_noc_role.sql
--
-- Idempotent by design: safe to re-run, and re-running is how the password
-- gets rotated. Deliberately NOT an Alembic migration — a role is cluster
-- state rather than schema, and the password is a secret that has no business
-- living in a version-controlled migration file.

\set ON_ERROR_STOP on

-- CREATE ROLE has no IF NOT EXISTS, hence the DO block.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'noc_writer') THEN
        CREATE ROLE noc_writer LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;
        RAISE NOTICE 'created role noc_writer';
    ELSE
        RAISE NOTICE 'role noc_writer already exists — updating password and grants';
    END IF;
END
$$;

ALTER ROLE noc_writer WITH LOGIN PASSWORD :'noc_password';

-- Reset to zero first, so re-running after someone has widened the grants by
-- hand narrows them back rather than leaving the extra privileges in place.
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM noc_writer;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM noc_writer;
REVOKE ALL ON SCHEMA public FROM noc_writer;

GRANT CONNECT ON DATABASE :"db_name" TO noc_writer;

-- USAGE only: the role can resolve names inside the schema but cannot CREATE
-- objects in it.
GRANT USAGE ON SCHEMA public TO noc_writer;

-- The one table `noc` touches (noc/monitor.py):
--   INSERT — run_cycle() writes one row per poll
--   DELETE — purge_old_samples() prunes past the retention window
--   SELECT — required by PostgreSQL for the DELETE's WHERE clause, which
--            reads sampled_at. Not granted for reading's own sake.
GRANT SELECT, INSERT, DELETE ON network_health_samples TO noc_writer;

-- id is BIGSERIAL, so INSERT needs the sequence as well. (docs/security.md
-- §7's sketch of this grant omitted the sequence; without it every INSERT
-- fails with "permission denied for sequence".)
GRANT USAGE, SELECT ON SEQUENCE network_health_samples_id_seq TO noc_writer;

-- Everything else — analytics_events, admin_users, admin_sessions,
-- login_attempts, projects, certifications, skills — is left with no grant at
-- all, which in PostgreSQL means no access. Verified in
-- backend/tests/test_noc_role.py rather than assumed.
