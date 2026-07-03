from pydantic import BaseModel, Field


class ClusterInspectionResult(BaseModel):
    component: str
    namespace: str | None = None
    node: str | None = None
    status: str
    describe_summary: str | None = None
    log_summary: str | None = None


class ClusterInspectionResponse(BaseModel):
    health_status: str
    executed_at: str
    results: list[ClusterInspectionResult]


class NamespaceInspectionRequest(BaseModel):
    namespace: str = Field(min_length=1)
    label_selector: str | None = None


class InspectedPod(BaseModel):
    name: str
    status: str
    restarts: int
    events: list[str]
    describe_summary: str
    log_summary: str | None = None
    resource_usage: dict[str, str]


class InspectedObject(BaseModel):
    name: str
    status: str
    summary: str


class NamespaceInspectionResponse(BaseModel):
    namespace: str
    label_selector: str | None = None
    health_status: str
    executed_at: str
    pods: list[InspectedPod]
    services: list[InspectedObject]
    ingresses: list[InspectedObject]
    tls_secrets: list[InspectedObject]
    daemonsets: list[InspectedObject]
