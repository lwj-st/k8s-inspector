from pydantic import BaseModel, ConfigDict, Field


class WhitelistBase(BaseModel):
    namespace: str = Field(min_length=1)
    label_selector: str | None = None
    keyword: str = Field(min_length=1)
    enabled: bool = True
    note: str | None = None


class WhitelistCreate(WhitelistBase):
    pass


class WhitelistUpdate(WhitelistBase):
    pass


class WhitelistRead(WhitelistBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
