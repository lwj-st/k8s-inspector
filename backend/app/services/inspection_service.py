from sqlalchemy.orm import Session

from app.models import InspectionRecord
from app.providers.base import InspectionProvider
from app.services import discovery_service
from app.services.keyword_service import match_log_text
from app.services.pod_health import is_abnormal_container, is_abnormal_pod, is_normal_pod_status
from app.schemas.inspection import (
    InspectionRunRequest,
    InspectionTargetType,
    NamespaceBatchInspectionRequest,
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


def run_namespace_batch_inspection(
    session: Session,
    provider: InspectionProvider,
    payload: NamespaceBatchInspectionRequest,
) -> dict:
    discovery = discovery_service.discover_namespaces(provider)
    summaries_by_name = {item["name"]: item for item in discovery.get("namespaces", [])}
    requested_namespaces = (
        [item["name"] for item in discovery.get("namespaces", [])]
        if payload.all_namespaces
        else payload.namespaces
    )
    sorted_namespaces = sorted(requested_namespaces)

    results: list[dict] = []
    for namespace in sorted_namespaces:
        try:
            inspection = provider.run_namespace_inspection(namespace, None)
            _attach_namespace_evidence(session, inspection, namespace, None)
            summary = _build_namespace_batch_summary(
                namespace=namespace,
                inspection=inspection,
                discovered_summary=summaries_by_name.get(namespace),
            )
            results.append(
                {
                    "summary": summary,
                    "health_status": inspection["health_status"],
                    "detail_target": inspection["inspection_target"],
                }
            )
        except Exception:
            summary = summaries_by_name.get(
                namespace,
                {
                    "name": namespace,
                    "status": "error",
                    "pod_count": 0,
                    "abnormal_pod_count": 0,
                    "last_inspected_at": discovery["executed_at"],
                    "labels": {},
                    "abnormal_categories": [],
                },
            ) | {"name": namespace, "status": "error"}
            results.append(
                {
                    "summary": summary,
                    "health_status": "error",
                    "detail_target": {
                        "type": "namespace",
                        "namespace": namespace,
                        "pod_name": None,
                        "label_selector": None,
                        "saved_target_id": None,
                        "template_id": None,
                        "resource_scope": ["pods", "services", "ingresses", "daemonsets", "secrets"],
                    },
                }
            )

    result = {
        "executed_at": discovery["executed_at"],
        "all_namespaces": payload.all_namespaces,
        "requested_namespaces": requested_namespaces,
        "results": results,
    }
    overall_health_status = (
        "error"
        if any(item["health_status"] == "error" for item in results)
        else "warning" if any(item["health_status"] != "healthy" for item in results) else "healthy"
    )
    _save_record(session, "namespaces", payload.model_dump(), result | {"health_status": overall_health_status})
    result.pop("health_status", None)
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
    hits = []
    pod_labels = pod.get("labels") or {}
    container_logs = pod.get("container_log_summaries") or {}
    if container_logs:
        for container_name, log_text in container_logs.items():
            hits.extend(
                match_log_text(
                    session=session,
                    namespace=namespace,
                    label_selector=label_selector,
                    pod_name=pod["name"],
                    container_name=container_name,
                    log_text=log_text,
                    pod_labels=pod_labels,
                )
            )
    else:
        containers = pod.get("containers") or []
        container_name = containers[0]["name"] if containers else None
        hits = match_log_text(
            session=session,
            namespace=namespace,
            label_selector=label_selector,
            pod_name=pod["name"],
            container_name=container_name,
            log_text=pod.get("log_summary"),
            pod_labels=pod_labels,
        )
    pod["log_hits"] = [hit.model_dump() for hit in hits if not hit.whitelisted]
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


def _build_namespace_batch_summary(
    namespace: str,
    inspection: dict,
    discovered_summary: dict | None,
) -> dict:
    pods = inspection.get("pods", [])
    abnormal_pod_count = len([pod for pod in pods if is_abnormal_pod(pod)])
    abnormal_categories = _derive_namespace_abnormal_categories(inspection)

    return {
        "name": namespace,
        "status": inspection["health_status"],
        "pod_count": len(pods),
        "abnormal_pod_count": abnormal_pod_count,
        "last_inspected_at": inspection.get("executed_at"),
        "labels": (discovered_summary or {}).get("labels", {}),
        "abnormal_categories": abnormal_categories,
    }


def _derive_namespace_abnormal_categories(inspection: dict) -> list[str]:
    pods = inspection.get("pods", [])
    categories: list[str] = []

    if any(_is_abnormal_pod_status(pod.get("status")) for pod in pods):
        categories.append("pod_status")
    if any(_has_abnormal_container(container) for pod in pods for container in pod.get("containers", [])):
        categories.append("container_status")
    if any(pod.get("events") for pod in pods):
        categories.append("event")
    if _has_effective_log_hit(pods):
        categories.append("log_keyword")
    if _has_abnormal_related_object(inspection):
        categories.append("related_object")

    return categories


def _is_abnormal_pod_status(status: str | None) -> bool:
    return not is_normal_pod_status(status)


def _has_abnormal_container(container: dict) -> bool:
    return is_abnormal_container(
        container.get("state"),
        container.get("reason"),
        container.get("exit_code"),
    )


def _has_abnormal_related_object(inspection: dict) -> bool:
    namespace_objects = (
        inspection.get("services", []),
        inspection.get("ingresses", []),
        inspection.get("daemonsets", []),
        inspection.get("tls_secrets", []),
    )
    if any(_is_unhealthy_object(item) for objects in namespace_objects for item in objects):
        return True

    return any(_is_unhealthy_object(item) for pod in inspection.get("pods", []) for item in pod.get("related_resources", []))


def _has_effective_log_hit(pods: list[dict]) -> bool:
    return any(
        not hit.get("whitelisted")
        for pod in pods
        for hit in pod.get("log_hits", [])
    )


def _is_unhealthy_object(resource: dict) -> bool:
    return str(resource.get("status") or "").lower() != "healthy"
