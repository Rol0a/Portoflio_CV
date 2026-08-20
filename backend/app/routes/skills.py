from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.skill import Skill, SkillCategory
from app.schemas.skill import SkillGroupOut, SkillOut, SkillsResponse

router = APIRouter(prefix="/api/v1/skills", tags=["skills"])


@router.get("", response_model=SkillsResponse)
async def get_skills(db: AsyncSession = Depends(get_db)) -> SkillsResponse:
    # Postgres orders an enum column by the type's declared order, so this is
    # also the on-page section order — see SkillCategory's docstring.
    result = await db.execute(select(Skill).order_by(Skill.category, Skill.sort_order))
    skills = result.scalars().all()

    grouped: dict[SkillCategory, list[SkillOut]] = {}
    for skill in skills:
        grouped.setdefault(skill.category, []).append(SkillOut(name=skill.name))

    featured = [
        SkillOut(name=skill.name)
        for skill in sorted(
            (s for s in skills if s.featured_rank is not None),
            key=lambda s: s.featured_rank,  # type: ignore[arg-type,return-value]
        )
    ]

    return SkillsResponse(
        featured=featured,
        categories=[SkillGroupOut(category=category, skills=items) for category, items in grouped.items()],
    )
