from pydantic import BaseModel, Field

from app.schemas.common import TimestampedModel


class WhitelistBase(BaseModel):
    namespace: str = Field(min_length=1)
    label_selector: str | None = None
    pod_name_pattern: str | None = None
    container_name: str | None = None
    keyword: str = Field(min_length=1)
    enabled: bool = True
    note: str | None = None


class WhitelistCreate(WhitelistBase):
    pass


class WhitelistUpdate(WhitelistBase):
    pass


class WhitelistRead(TimestampedModel, WhitelistBase):
    pass


class WhitelistIgnoreCreate(BaseModel):
    namespace: str = Field(min_length=1)
    label_selector: str | None = None
    pod_name_pattern: str | None = None
    container_name: str | None = None
    keyword: str = Field(min_length=1)
    note: str | None = None
