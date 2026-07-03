from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TimestampedModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime | None = None
    updated_at: datetime | None = None
