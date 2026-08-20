from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.project import Locale, ProjectCategory
from app.schemas.project import ProjectDetail, ProjectListResponse
from app.services import project_service

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


@router.get("", response_model=ProjectListResponse)
async def get_projects(
    locale: Locale = Query(default=Locale.en),
    category: ProjectCategory | None = Query(default=None),
    featured: bool | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> ProjectListResponse:
    projects = await project_service.list_projects(db, locale=locale, category=category, featured=featured)
    return ProjectListResponse(projects=projects)


@router.get("/{slug}", response_model=ProjectDetail)
async def get_project(
    slug: str,
    locale: Locale = Query(default=Locale.en),
    db: AsyncSession = Depends(get_db),
) -> ProjectDetail:
    project = await project_service.get_project_by_slug(db, slug=slug, locale=locale)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project
