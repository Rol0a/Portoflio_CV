from pydantic import BaseModel

from app.models.skill import SkillCategory


class SkillOut(BaseModel):
    name: str
    proficiency: int | None


class SkillGroupOut(BaseModel):
    category: SkillCategory
    skills: list[SkillOut]


class SkillsResponse(BaseModel):
    categories: list[SkillGroupOut]
