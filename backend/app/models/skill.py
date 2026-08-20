import enum
import uuid

from sqlalchemy import Enum, Index, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SkillCategory(str, enum.Enum):
    programming = "programming"
    embedded_systems = "embedded_systems"
    electronics = "electronics"
    automation = "automation"
    web_dev = "web_dev"
    ml_data = "ml_data"
    cybersecurity = "cybersecurity"
    linux_devops = "linux_devops"
    engineering_tools = "engineering_tools"


class Skill(Base):
    __tablename__ = "skills"
    __table_args__ = (Index("idx_skills_category", "category"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    category: Mapped[SkillCategory] = mapped_column(Enum(SkillCategory, name="skill_category"), nullable=False)
    proficiency: Mapped[int | None] = mapped_column(Integer)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    icon_url: Mapped[str | None] = mapped_column(Text)
