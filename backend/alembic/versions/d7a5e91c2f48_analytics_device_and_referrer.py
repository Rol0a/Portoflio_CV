"""analytics device class + referrer host, and drop the seeded demo traffic

Revision ID: d7a5e91c2f48
Revises: e4b2c8f61a07
Create Date: 2026-08-20 15:40:00.000000

Two changes that only make sense together: widening what an analytics event
records, and deleting the synthetic rows that were standing in for real ones.

**Columns.** `device_class` and `referrer_host` are the two dimensions the
dashboard could never show because they were never written. Both are nullable
TEXT and both are populated at write time by `analytics_service.record_event`;
neither can be backfilled, because the only trace of an old visitor's browser
is a one-way hash. That is deliberate — see the model docstrings.

**The purge.** `scripts/seed.py` used to plant ~500 synthetic events across a
30-day window so the M10 dashboard had a shape to render before the M8
recording pipeline existed. That pipeline does exist now and has been writing
real events since 2026-08-19 23:04 UTC, so the demo rows are no longer scaffolding
— they are wrong numbers on an admin dashboard, mixed indistinguishably into
the real ones on every chart.

`ip_hash IS NULL` identifies them exactly. `record_event` hashes the client IP
unconditionally (it always has one), so every genuinely-recorded event has a
non-null `ip_hash`; the seed set neither `ip_hash` nor `user_agent_hash`.
Verified against the live table before writing this: 496 rows null, 226 rows
non-null, and zero rows in either mixed state.

The delete is inside the migration rather than a one-off script so that any
database this schema is applied to — production, a fresh clone, a test
throwaway — ends up with real-events-only, once. `downgrade()` cannot restore
them and does not pretend to.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'd7a5e91c2f48'
down_revision: Union[str, None] = 'e4b2c8f61a07'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('analytics_events', sa.Column('device_class', sa.Text(), nullable=True))
    op.add_column('analytics_events', sa.Column('referrer_host', sa.Text(), nullable=True))

    # Aggregations group by these two and always filter on created_at, so the
    # composite matches the access pattern; a bare index on the low-cardinality
    # device_class alone would rarely be chosen.
    op.create_index(
        'idx_analytics_device_class',
        'analytics_events',
        ['device_class', 'created_at'],
    )
    op.create_index(
        'idx_analytics_referrer_host',
        'analytics_events',
        ['referrer_host', 'created_at'],
    )

    op.execute("DELETE FROM analytics_events WHERE ip_hash IS NULL")


def downgrade() -> None:
    op.drop_index('idx_analytics_referrer_host', table_name='analytics_events')
    op.drop_index('idx_analytics_device_class', table_name='analytics_events')
    op.drop_column('analytics_events', 'referrer_host')
    op.drop_column('analytics_events', 'device_class')
