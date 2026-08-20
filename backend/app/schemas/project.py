from pydantic import BaseModel

from app.models.project import ProjectCategory, TechCategory


class TechnologyOut(BaseModel):
    name: str
    category: TechCategory

    model_config = {"from_attributes": True}


class ProjectImageOut(BaseModel):
    url: str
    alt_text: str | None
    is_hero: bool

    model_config = {"from_attributes": True}


class ProjectListItem(BaseModel):
    id: str
    slug: str
    category: ProjectCategory
    github_url: str | None
    demo_url: str | None
    featured: bool
    title: str
    short_desc: str
    technologies: list[str]
    hero_image_url: str | None


class ProjectListResponse(BaseModel):
    projects: list[ProjectListItem]


class ProjectDetail(BaseModel):
    id: str
    slug: str
    category: ProjectCategory
    github_url: str | None
    demo_url: str | None
    featured: bool
    title: str
    short_desc: str
    overview: str | None
    problem: str | None
    requirements: str | None
    architecture: str | None
    implementation: str | None
    decisions: str | None
    challenges: str | None
    testing_desc: str | None
    results: str | None
    lessons: str | None
    technologies: list[TechnologyOut]
    images: list[ProjectImageOut]
