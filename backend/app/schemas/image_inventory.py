from pydantic import BaseModel, Field, model_validator


class ImageInventoryReference(BaseModel):
    namespace: str
    pod_name: str
    pod_phase: str
    container_name: str
    container_type: str
    source: str
    image: str
    image_id: str | None = None
    pod_created_at: str | None = None


class ImageInventoryItem(BaseModel):
    image: str
    namespace_count: int = Field(ge=0)
    pod_count: int = Field(ge=0)
    container_count: int = Field(ge=0)
    latest_pod_created_at: str | None = None
    latest_pod_phase: str | None = None
    references: list[ImageInventoryReference] = Field(default_factory=list)


class ImageInventorySummary(BaseModel):
    image_count: int = Field(ge=0)
    namespace_count: int = Field(ge=0)
    pod_count: int = Field(ge=0)
    container_count: int = Field(ge=0)


class ImageInventoryResponse(BaseModel):
    executed_at: str
    namespaces: list[str] = Field(default_factory=list)
    search: str | None = None
    provider_mode: str = "unknown"
    simulated: bool = False
    summary: ImageInventorySummary
    items: list[ImageInventoryItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_summary(self) -> "ImageInventoryResponse":
        if self.summary.image_count != len(self.items):
            raise ValueError("image_count must equal the number of items")
        return self
