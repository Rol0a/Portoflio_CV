import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Table,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Locale(str, enum.Enum):
    en = "en"
    es = "es"


class ProjectCategory(str, enum.Enum):
    featured = "featured"
    software = "software"
    embedded = "embedded"
    electronics = "electronics"
    robotics = "robotics"
    ml_data = "ml_data"
    cybersecurity = "cybersecurity"
    devops_infra = "devops_infra"
    academic_research = "academic_research"


class ProjectStatus(str, enum.Enum):
    """Whether a project is finished work or still being built.

    Exists so "no GitHub link" stops being ambiguous. A null `github_url` was
    already carrying two very different meanings — the work is private/offline,
    or the work isn't done yet — and the UI could only render the absence, not
    the reason. `in_development` says the second one out loud.
    """

    complete = "complete"
    in_development = "in_development"


class TechCategory(str, enum.Enum):
    programming = "programming"
    embedded_systems = "embedded_systems"
    electronics = "electronics"
    automation = "automation"
    web_dev = "web_dev"
    ml_data = "ml_data"
    cybersecurity = "cybersecurity"
    linux_devops = "linux_devops"
    engineering_tools = "engineering_tools"


project_technologies = Table(
    "project_technologies",
    Base.metadata,
    Column("project_id", UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "technology_id", UUID(as_uuid=True), ForeignKey("technologies.id", ondelete="CASCADE"), primary_key=True
    ),
)


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        Index("idx_projects_category", "category"),
        Index("idx_projects_featured", "featured", postgresql_where=text("featured = true")),
        Index("idx_projects_sort_order", "sort_order"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    category: Mapped[ProjectCategory] = mapped_column(Enum(ProjectCategory, name="project_category"), nullable=False)
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus, name="project_status"),
        nullable=False,
        server_default=ProjectStatus.complete.value,
    )
    github_url: Mapped[str | None] = mapped_column(Text)
    demo_url: Mapped[str | None] = mapped_column(Text)
    featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    translations: Mapped[list["ProjectTranslation"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    images: Mapped[list["ProjectImage"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="ProjectImage.sort_order"
    )
    technologies: Mapped[list["Technology"]] = relationship(
        secondary=project_technologies, back_populates="projects"
    )


class ProjectTranslation(Base):
    __tablename__ = "project_translations"
    __table_args__ = (
        UniqueConstraint("project_id", "locale", name="uq_project_locale"),
        Index("idx_pt_locale", "locale"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    locale: Mapped[Locale] = mapped_column(Enum(Locale, name="locale_type"), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    short_desc: Mapped[str] = mapped_column(Text, nullable=False)
    overview: Mapped[str | None] = mapped_column(Text)
    problem: Mapped[str | None] = mapped_column(Text)
    requirements: Mapped[str | None] = mapped_column(Text)
    architecture: Mapped[str | None] = mapped_column(Text)
    implementation: Mapped[str | None] = mapped_column(Text)
    decisions: Mapped[str | None] = mapped_column(Text)
    challenges: Mapped[str | None] = mapped_column(Text)
    testing_desc: Mapped[str | None] = mapped_column(Text)
    results: Mapped[str | None] = mapped_column(Text)
    lessons: Mapped[str | None] = mapped_column(Text)

    project: Mapped["Project"] = relationship(back_populates="translations")


class ProjectImage(Base):
    __tablename__ = "project_images"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    alt_text: Mapped[str | None] = mapped_column(Text)
    is_hero: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    project: Mapped["Project"] = relationship(back_populates="images")


class Technology(Base):
    __tablename__ = "technologies"
    __table_args__ = (Index("idx_technologies_category", "category"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    category: Mapped[TechCategory] = mapped_column(Enum(TechCategory, name="tech_category"), nullable=False)
    icon_url: Mapped[str | None] = mapped_column(Text)

    projects: Mapped[list["Project"]] = relationship(secondary=project_technologies, back_populates="technologies")
