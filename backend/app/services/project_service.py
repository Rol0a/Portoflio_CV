from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.project import Locale, Project, ProjectCategory, ProjectTranslation
from app.schemas.project import ProjectDetail, ProjectListItem, ProjectImageOut, TechnologyOut


async def list_projects(
    db: AsyncSession,
    locale: Locale,
    category: ProjectCategory | None = None,
    featured: bool | None = None,
) -> list[ProjectListItem]:
    stmt = (
        select(Project)
        .join(Project.translations)
        .where(ProjectTranslation.locale == locale)
        .options(
            selectinload(Project.translations),
            selectinload(Project.technologies),
            selectinload(Project.images),
        )
        .order_by(Project.sort_order)
    )
    if category is not None:
        stmt = stmt.where(Project.category == category)
    if featured is not None:
        stmt = stmt.where(Project.featured == featured)

    result = await db.execute(stmt)
    projects = result.scalars().unique().all()

    items = []
    for project in projects:
        translation = next(t for t in project.translations if t.locale == locale)
        hero = next((image for image in project.images if image.is_hero), None) or (
            project.images[0] if project.images else None
        )
        items.append(
            ProjectListItem(
                id=str(project.id),
                slug=project.slug,
                category=project.category,
                github_url=project.github_url,
                demo_url=project.demo_url,
                featured=project.featured,
                title=translation.title,
                short_desc=translation.short_desc,
                technologies=[tech.name for tech in project.technologies],
                hero_image_url=hero.url if hero else None,
            )
        )
    return items


async def get_project_by_slug(db: AsyncSession, slug: str, locale: Locale) -> ProjectDetail | None:
    stmt = (
        select(Project)
        .where(Project.slug == slug)
        .options(
            selectinload(Project.translations),
            selectinload(Project.technologies),
            selectinload(Project.images),
        )
    )
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()
    if project is None:
        return None

    translation = next(
        (t for t in project.translations if t.locale == locale),
        next((t for t in project.translations if t.locale == Locale.en), None),
    )
    if translation is None:
        return None

    return ProjectDetail(
        id=str(project.id),
        slug=project.slug,
        category=project.category,
        github_url=project.github_url,
        demo_url=project.demo_url,
        featured=project.featured,
        title=translation.title,
        short_desc=translation.short_desc,
        overview=translation.overview,
        problem=translation.problem,
        requirements=translation.requirements,
        architecture=translation.architecture,
        implementation=translation.implementation,
        decisions=translation.decisions,
        challenges=translation.challenges,
        testing_desc=translation.testing_desc,
        results=translation.results,
        lessons=translation.lessons,
        technologies=[TechnologyOut.model_validate(tech) for tech in project.technologies],
        images=[ProjectImageOut.model_validate(image) for image in project.images],
    )
