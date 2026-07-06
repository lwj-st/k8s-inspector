from sqlalchemy.orm import Session

from app.models import InspectionRecord
from app.providers.base import InspectionProvider
from app.services.keyword_service import match_log_text
from app.schemas.inspection import (
    InspectionRunRequest,
    InspectionTargetType,
    NamespaceInspectionRequest,
    PodInspectionRequest,
)


def _save_record(session: Session, inspection_type: str, request_payload: dict, result: dict) -> None:
    session.add(
        InspectionRecord(
            inspection_type=inspection_type,
            request_payload=request_payload,
            result_payload=result,
            summary_status=result["health_status"],
        )
    )
    session.commit()


def run_cluster_inspection(session: Session, provider: InspectionProvider) -> dict:
    result = provider.run_cluster_inspection()
    _save_record(session, "cluster", {}, result)
    return result


def run_namespace_inspection(session: Session, provider: InspectionProvider, payload: NamespaceInspectionRequest) -> dict:
    result = provider.run_namespace_inspection(payload.namespace, payload.label_selector)
    _attach_namespace_evidence(session, result, payload.namespace, payload.label_selector)
    _save_record(session, "namespace", payload.model_dump(), result)
    return result


def run_pod_inspection(session: Session, provider: InspectionProvider, payload: PodInspectionRequest) -> dict:
    result = provider.run_pod_inspection(payload.namespace, payload.pod_name)
    pod = _attach_log_hits(session, payload.namespace, None, result["pod"])
    result["pod"] = pod
    result["inspection_target"] = {
        "type": "pod",
        "namespace": payload.namespace,
        "pod_name": payload.pod_name,
        "label_selector": None,
        "saved_target_id": None,
        "template_id": None,
        "resource_scope": ["pods"],
    }
    result["evidence_bundle"] = _build_evidence_bundle(payload.namespace, pod)
    _save_record(session, "pod", payload.model_dump(), result)
    return result


def run_inspection(session: Session, provider: InspectionProvider, payload: InspectionRunRequest) -> dict:
    if payload.target_type == InspectionTargetType.cluster:
        return {
            "target_type": payload.target_type,
            "cluster_result": run_cluster_inspection(session, provider),
            "namespace_result": None,
            "pod_result": None,
        }

    if payload.target_type == InspectionTargetType.namespace:
        namespace_result = run_namespace_inspection(
            session,
            provider,
            NamespaceInspectionRequest(namespace=payload.namespace or "", label_selector=payload.label_selector),
        )
        return {
            "target_type": payload.target_type,
            "cluster_result": None,
            "namespace_result": namespace_result,
            "pod_result": None,
        }

    pod_result = run_pod_inspection(
        session,
        provider,
        PodInspectionRequest(namespace=payload.namespace or "", pod_name=payload.pod_name or ""),
    )
    return {
        "target_type": payload.target_type,
        "cluster_result": None,
        "namespace_result": None,
        "pod_result": pod_result,
    }


def list_history(session: Session, inspection_type: str | None = None) -> list[InspectionRecord]:
    query = session.query(InspectionRecord)
    if inspection_type is not None:
        query = query.filter(InspectionRecord.inspection_type == inspection_type)
    return query.order_by(InspectionRecord.executed_at.desc()).all()


def _attach_namespace_evidence(
    session: Session,
    result: dict,
    namespace: str,
    label_selector: str | None,
) -> None:
    pods = [_attach_log_hits(session, namespace, label_selector, dict(pod)) for pod in result.get("pods", [])]
    result["pods"] = pods
    result["inspection_target"] = {
        "type": "namespace",
        "namespace": namespace,
        "pod_name": None,
        "label_selector": label_selector,
        "saved_target_id": None,
        "template_id": None,
        "resource_scope": ["pods", "services", "ingresses", "daemonsets", "secrets"],
    }
    result["evidence_bundles"] = [_build_evidence_bundle(namespace, pod) for pod in pods]


def _attach_log_hits(
    session: Session,
    namespace: str,
    label_selector: str | None,
    pod: dict,
) -> dict:
    containers = pod.get("containers") or []
    container_name = containers[0]["name"] if containers else None
    hits = match_log_text(
        session=session,
        namespace=namespace,
        label_selector=label_selector,
        pod_name=pod["name"],
        container_name=container_name,
        log_text=pod.get("log_summary"),
    )
    pod["log_hits"] = [hit.model_dump() for hit in hits]
    return pod


def _build_evidence_bundle(namespace: str, pod: dict) -> dict:
    return {
        "object_type": "pod",
        "namespace": namespace,
        "name": pod["name"],
        "status": pod["status"],
        "node_name": pod.get("node_name"),
        "restarts": pod.get("restarts"),
        "describe_summary": pod.get("describe_summary"),
        "events": pod.get("events", []),
        "resource_usage": pod.get("resource_usage", {}),
        "log_hits": pod.get("log_hits", []),
        "related_resources": pod.get("related_resources", []),
    }
