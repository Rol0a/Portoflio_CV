"""add project status

Revision ID: c1f0a7d94b23
Revises: bf0d8d836407
Create Date: 2026-08-20 04:05:00.000000

Adds `projects.status` so an unfinished project can say so instead of just
missing a GitHub link. Existing rows are backfilled to `complete` — that is
what a project with a repo and a writeup already meant — and the two rows that
are genuinely still being built are flipped by hand below, keyed on slug so the
migration is idempotent against a database that doesn't have them.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'c1f0a7d94b23'
down_revision: Union[str, None] = 'bf0d8d836407'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

IN_DEVELOPMENT_SLUGS = ('electrodynamic-tether-deorbit', 'fedora-linux-environment')


def upgrade() -> None:
    project_status = sa.Enum('complete', 'in_development', name='project_status')
    project_status.create(op.get_bind(), checkfirst=True)

    op.add_column(
        'projects',
        sa.Column(
            'status',
            project_status,
            nullable=False,
            server_default='complete',
        ),
    )

    op.execute(
        sa.text(
            "UPDATE projects SET status = 'in_development' WHERE slug = ANY(:slugs)"
        ).bindparams(sa.bindparam('slugs', value=list(IN_DEVELOPMENT_SLUGS)))
    )


def downgrade() -> None:
    op.drop_column('projects', 'status')
    sa.Enum(name='project_status').drop(op.get_bind(), checkfirst=True)
