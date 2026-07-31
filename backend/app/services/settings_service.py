from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import SystemSetting
from app.providers.base import InspectionProvider
from app.schemas.settings import (
    RequiredComponentCandidate,
    RequiredComponentCandidateResponse,
    SettingsResponse,
    SettingsUpdate,
)
from app.schemas.v1_1 import (
    CollectionLayer,
    InspectionPolicySettings,
    InspectionScope,
    InspectionScopeType,
    InspectionTrigger,
    ProviderCollectionRequest,
    RequiredComponentPolicy,
    default_required_components,
)
from app.security.crypto import SensitiveValueCipher


MASKED_SECRET = "********"
COMPONENT_CANDIDATE_KINDS = {"Deployment", "DaemonSet", "StatefulSet", "Pod", "Service"}
SELECTOR_LABEL_PRIORITY = (
    "app.kubernetes.io/instance",
    "app.kubernetes.io/name",
    "app.kubernetes.io/component",
    "k8s-app",
    "app",
    "component",
    "name",
)


def get_settings(session: Session) -> SystemSetting:
    settings = session.get(SystemSetting, 1)
    if settings is None:
        raise ValueError("settings not found")
    return settings


def get_effective_cluster_id(session: Session, app_settings: Settings) -> str:
    settings = session.get(SystemSetting, 1)
    if settings is not None and settings.cluster_id.strip():
        return settings.cluster_id.strip()
    return app_settings.cluster_id.strip() or "local"


def serialize_settings(settings: SystemSetting) -> SettingsResponse:
    policy = policy_with_builtin_required_components(settings.inspection_policy)
    return SettingsResponse(
        cluster_id=settings.cluster_id,
        base_path=settings.base_path,
        provider_mode=settings.provider_mode,
        kubeconfig_path=settings.kubeconfig_path,
        kube_context=settings.kube_context,
        llm_enabled=settings.llm_enabled,
        llm_provider=settings.llm_provider,
        model_endpoint=settings.model_endpoint,
        api_key=MASKED_SECRET if settings.api_key_encrypted else None,
        default_inspection_strategy=settings.default_inspection_strategy,
        inspection_policy=InspectionPolicySettings.model_validate(policy),
    )


def policy_with_builtin_required_components(policy: dict | None) -> dict:
    normalized = dict(policy or {})
    if not normalized.get("required_components"):
        normalized["required_components"] = [
            item.model_dump(mode="json")
            for item in default_required_components()
        ]
    return normalized


def update_settings(
    session: Session,
    payload: SettingsUpdate,
    app_settings: Settings,
) -> SystemSetting:
    settings = get_settings(session)
    values = payload.model_dump(exclude={"api_key", "inspection_policy", "cluster_id"})
    for key, value in values.items():
        setattr(settings, key, value)
    if payload.cluster_id is not None:
        settings.cluster_id = payload.cluster_id
    if payload.api_key != MASKED_SECRET:
        settings.api_key = None
        settings.api_key_encrypted = (
            SensitiveValueCipher.from_key(app_settings.encryption_key).encrypt(
                payload.api_key,
                purpose="llm_api_key",
            )
            if payload.api_key
            else None
        )
    if "inspection_policy" in payload.model_fields_set:
        settings.inspection_policy = payload.inspection_policy.model_dump(mode="json")
    session.commit()
    session.refresh(settings)
    return settings


def _labels_to_dict(raw_labels: object) -> dict[str, str]:
    labels: dict[str, str] = {}
    if not isinstance(raw_labels, list):
        return labels
    for item in raw_labels:
        if not isinstance(item, str) or "=" not in item:
            continue
        key, value = item.split("=", 1)
        if key and value:
            labels[key] = value
    return labels


def _candidate_selector(labels: dict[str, str]) -> str | None:
    selector_parts: list[str] = []
    if "app.kubernetes.io/name" in labels and "app.kubernetes.io/component" in labels:
        selector_parts = [
            f"app.kubernetes.io/name={labels['app.kubernetes.io/name']}",
            f"app.kubernetes.io/component={labels['app.kubernetes.io/component']}",
        ]
    else:
        for key in SELECTOR_LABEL_PRIORITY:
            if key in labels:
                selector_parts = [f"{key}={labels[key]}"]
                break
    return ",".join(selector_parts) if selector_parts else None


def _candidate_key(component: RequiredComponentPolicy) -> tuple[str, str, str]:
    return (
        component.namespace,
        component.kind.casefold(),
        component.label_selector,
    )


def list_required_component_candidates(
    provider: InspectionProvider,
) -> RequiredComponentCandidateResponse:
    candidates: list[RequiredComponentCandidate] = [
        RequiredComponentCandidate(
            **component.model_dump(mode="json"),
            source="builtin",
        )
        for component in default_required_components()
    ]
    seen = {_candidate_key(component) for component in candidates}
    result = provider.collect_resources(
        ProviderCollectionRequest(
            scope=InspectionScope(type=InspectionScopeType.cluster),
            layer=CollectionLayer.status,
            trigger=InspectionTrigger.manual,
        )
    )
    for observation in result.observations:
        resource = observation.resource
        if resource.kind not in COMPONENT_CANDIDATE_KINDS or not resource.namespace:
            continue
        selector = _candidate_selector(_labels_to_dict(observation.facts.get("labels")))
        if not selector:
            continue
        candidate = RequiredComponentCandidate(
            name=resource.name,
            namespace=resource.namespace,
            kind=resource.kind,
            label_selector=selector,
            enabled=True,
            source="discovered",
        )
        key = _candidate_key(candidate)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(candidate)
    candidates.sort(key=lambda item: (item.source != "builtin", item.namespace, item.kind, item.name))
    return RequiredComponentCandidateResponse(items=candidates)
