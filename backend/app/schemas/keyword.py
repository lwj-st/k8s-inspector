from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import KeywordHitSeverity


class KeywordRuleBase(BaseModel):
    keyword: str = Field(min_length=1)
    category: str = Field(min_length=1, default="generic")
    severity: KeywordHitSeverity = KeywordHitSeverity.warning
    description: str | None = None
    enabled: bool = True


class KeywordRuleCreate(KeywordRuleBase):
    builtin: bool = False


class KeywordRuleUpdate(KeywordRuleBase):
    builtin: bool = False


class KeywordRuleRead(KeywordRuleBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    builtin: bool
