from pydantic import BaseModel

from app.models.skill import SkillCategory


class SkillOut(BaseModel):
    name: str


class SkillGroupOut(BaseModel):
    category: SkillCategory
    skills: list[SkillOut]


class SkillsResponse(BaseModel):
    """Featured is a flat list, not a group.

    It is a cross-section of the categories below rather than a category of its
    own, so giving it a `SkillGroupOut` would mean inventing a `SkillCategory`
    value that no row actually holds.
    """

    featured: list[SkillOut]
    categories: list[SkillGroupOut]
