from pydantic import BaseModel, ConfigDict, Field


class KeywordRuleBase(BaseModel):
    keyword: str = Field(min_length=1)
    category: str = Field(min_length=1, default="generic")
    severity: str = Field(min_length=1, default="warning")
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
