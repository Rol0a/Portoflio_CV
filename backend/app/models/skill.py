import enum
import uuid

from sqlalchemy import Enum, Index, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SkillCategory(str, enum.Enum):
    """Engineering disciplines, not tool bins.

    The earlier set (`electronics`, `automation`, `engineering_tools`,
    `cybersecurity`, `ml_data`, `web_dev`) sorted skills by what *kind of thing*
    each one was, which scattered a single competency across three headings —
    Fusion 360 under engineering_tools, PCB design under electronics, DFM under
    engineering_tools again — and left a reader with no way to see that they add
    up to hardware design. These categories name the discipline instead, so each
    heading is something you could actually claim in an interview.

    Declaration order is the on-page order: Postgres sorts an enum column by the
    type's declared order, and `routes/skills.py` orders by `category` — so
    moving a value here moves the section on the page.

    "Featured" is deliberately *not* a value: it is `Skill.featured`, a flag. As
    a category it would need Python and Docker to exist twice, and `skills.name`
    is unique.
    """

    programming = "programming"
    embedded_systems = "embedded_systems"
    hardware_design = "hardware_design"
    robotics = "robotics"
    networks = "networks"
    web_backend = "web_backend"
    linux_devops = "linux_devops"
    data_ml = "data_ml"


class Skill(Base):
    __tablename__ = "skills"
    __table_args__ = (Index("idx_skills_category", "category"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    category: Mapped[SkillCategory] = mapped_column(Enum(SkillCategory, name="skill_category"), nullable=False)
    # Surfaces the skill in the page's opening "Featured" row as well as its own
    # section — a quick read of the profile, not a second copy of the list.
    #
    # A rank rather than a boolean, so one nullable column carries both facts:
    # NULL means "not featured", and any value is that badge's position in the
    # row. Featured is a curated sequence, and `sort_order` can't express it —
    # that one is scoped to the skill's own category section.
    featured_rank: Mapped[int | None] = mapped_column(Integer)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
