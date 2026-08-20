from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.skill import Skill, SkillCategory
from app.schemas.skill import SkillGroupOut, SkillOut, SkillsResponse

router = APIRouter(prefix="/api/v1/skills", tags=["skills"])


@router.get("", response_model=SkillsResponse)
async def get_skills(db: AsyncSession = Depends(get_db)) -> SkillsResponse:
    result = await db.execute(select(Skill).order_by(Skill.category, Skill.sort_order))
    skills = result.scalars().all()

    grouped: dict[SkillCategory, list[SkillOut]] = {}
    for skill in skills:
        grouped.setdefault(skill.category, []).append(
            SkillOut(name=skill.name, proficiency=skill.proficiency)
        )

    return SkillsResponse(
        categories=[SkillGroupOut(category=category, skills=items) for category, items in grouped.items()]
    )
