from enum import Enum

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import EvidenceBundle, InspectionTarget, KeywordHit


class InspectionTargetType(str, Enum):
    cluster = "cluster"
    namespace = "namespace"
    pod = "pod"


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


class PodInspectionRequest(BaseModel):
    namespace: str = Field(min_length=1)
    pod_name: str = Field(min_length=1)


class InspectionRunRequest(BaseModel):
    target_type: InspectionTargetType
    namespace: str | None = None
    label_selector: str | None = None
    pod_name: str | None = None

    @model_validator(mode="after")
    def validate_target_fields(self) -> "InspectionRunRequest":
        if self.target_type == InspectionTargetType.cluster:
            return self
        if not self.namespace:
            raise ValueError("namespace is required for namespace and pod targets")
        if self.target_type == InspectionTargetType.pod and not self.pod_name:
            raise ValueError("pod_name is required for pod targets")
        return self


class InspectedContainer(BaseModel):
    name: str
    restart_count: int
    state: str
    reason: str | None = None


class RelatedResource(BaseModel):
    kind: str
    name: str
    status: str


class InspectedPod(BaseModel):
    name: str
    status: str
    node_name: str | None = None
    restarts: int
    containers: list[InspectedContainer] = Field(default_factory=list)
    events: list[str]
    describe_summary: str
    log_summary: str | None = None
    previous_log_summary: str | None = None
    log_hits: list[KeywordHit] = Field(default_factory=list)
    resource_usage: dict[str, str]
    related_resources: list[RelatedResource] = Field(default_factory=list)


class InspectedObject(BaseModel):
    name: str
    status: str
    summary: str


class NamespaceInspectionResponse(BaseModel):
    inspection_target: InspectionTarget
    namespace: str
    label_selector: str | None = None
    health_status: str
    executed_at: str
    evidence_bundles: list[EvidenceBundle] = Field(default_factory=list)
    pods: list[InspectedPod]
    services: list[InspectedObject]
    ingresses: list[InspectedObject]
    tls_secrets: list[InspectedObject]
    daemonsets: list[InspectedObject]


class PodInspectionResponse(BaseModel):
    inspection_target: InspectionTarget
    namespace: str
    health_status: str
    executed_at: str
    pod: InspectedPod
    evidence_bundle: EvidenceBundle | None = None


class InspectionRunResponse(BaseModel):
    target_type: InspectionTargetType
    cluster_result: ClusterInspectionResponse | None = None
    namespace_result: NamespaceInspectionResponse | None = None
    pod_result: PodInspectionResponse | None = None
