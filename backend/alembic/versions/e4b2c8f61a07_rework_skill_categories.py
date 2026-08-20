"""rework skill categories

Revision ID: e4b2c8f61a07
Revises: c1f0a7d94b23
Create Date: 2026-08-20 05:10:00.000000

Replaces the tool-shaped skill categories with discipline-shaped ones, drops the
self-assessed proficiency scale, and adds a `featured_rank` column.

**This deletes every row in `skills` and lets `scripts/seed.py` repopulate.**
That is not laziness: the old and new taxonomies do not map onto each other
row-for-row. `engineering_tools` split across `hardware_design` and `robotics`,
`automation` dissolved entirely into `programming` and `linux_devops`, and most
of the skill *names* changed too ("PWM & Motor Control" became two entries).
A per-row UPDATE would be a worse-documented version of the seed file.

Safe to do: `skills` is pure reference data. Nothing references it — no foreign
key in the schema points at `skills.id` (projects use the separate
`technologies` table), so there is nothing to cascade.

`proficiency` and `icon_url` are dropped rather than left in place. Proficiency
is gone by design — the badges show no numbers, and a column nothing writes or
reads is rot. `icon_url` was never populated; icons now live in the frontend's
`components/SkillBadge/skillIcons.ts` map, where changing one is an edit rather
than a migration.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'e4b2c8f61a07'
down_revision: Union[str, None] = 'c1f0a7d94b23'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_VALUES = (
    'programming', 'embedded_systems', 'electronics', 'automation', 'web_dev',
    'ml_data', 'cybersecurity', 'linux_devops', 'engineering_tools',
)
NEW_VALUES = (
    'programming', 'embedded_systems', 'hardware_design', 'robotics', 'networks',
    'web_backend', 'linux_devops', 'data_ml',
)


def _swap_enum(values: Sequence[str]) -> None:
    """Replace the `skill_category` type in place.

    Postgres can add enum values but cannot remove or reorder them, and the
    declared order is load-bearing here (it is the page's section order). So the
    type is rebuilt rather than altered. The table is emptied first, which makes
    the USING cast trivial and avoids any question of what an old value maps to.
    """
    op.execute('DELETE FROM skills')
    op.execute('ALTER TYPE skill_category RENAME TO skill_category_old')
    sa.Enum(*values, name='skill_category').create(op.get_bind(), checkfirst=False)
    op.execute(
        'ALTER TABLE skills ALTER COLUMN category TYPE skill_category '
        'USING category::text::skill_category'
    )
    op.execute('DROP TYPE skill_category_old')


def upgrade() -> None:
    _swap_enum(NEW_VALUES)
    op.add_column('skills', sa.Column('featured_rank', sa.Integer(), nullable=True))
    op.drop_column('skills', 'proficiency')
    op.drop_column('skills', 'icon_url')


def downgrade() -> None:
    op.add_column('skills', sa.Column('icon_url', sa.Text(), nullable=True))
    op.add_column('skills', sa.Column('proficiency', sa.Integer(), nullable=True))
    op.drop_column('skills', 'featured_rank')
    _swap_enum(OLD_VALUES)
