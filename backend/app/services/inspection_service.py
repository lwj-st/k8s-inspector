from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import get_settings as get_app_settings
from app.models import InspectionRecord, Issue as IssueModel, SystemSetting
from app.providers.base import (
    InspectionProvider,
    LogPodLimitExceededError as ProviderLogPodLimitExceededError,
)
from app.schemas.v1_1 import (
    CollectionLimits,
    InspectionPolicySettings,
    InspectionScope,
    InspectionScopeType,
    InspectionTrigger,
)
from app.services import discovery_service
from app.services.inspection_run_service import execute_inspection
from app.services.issue_query import issue_from_model
from app.services.settings_service import policy_with_builtin_required_components
from app.services.payload_sanitizer import (
    sanitize_persistence_payload as _shared_sanitize_persistence_payload,
    sanitize_public_payload,
)
from app.security.component_status import ComponentStatusRegistry
from app.services.keyword_service import match_log_text
from app.services.pod_health import is_abnormal_container, is_abnormal_pod, is_normal_pod_status
from app.schemas.inspection import (
    InspectionRunRequest,
    InspectionTargetType,
    NamespaceBatchInspectionRequest,
    NamespaceInspectionRequest,
    PodInspectionRequest,
)


class LogInspectionScopeTooLargeError(ValueError):
    def __init__(self, estimated_pods: int, limit: int):
        self.estimated_pods = estimated_pods
        self.limit = limit
        super().__init__(
            f"本次预计读取 {estimated_pods} 个 Pod 日志，超过上限 "
            f"{self.limit}，请缩小范围"
        )


def sanitize_persistence_payload(payload):
    """Keep the v1.0 metadata contract while using the shared sanitizer."""

    sanitized = _shared_sanitize_persistence_payload(payload)
    metadata = (
        sanitized.get("_persistence_sanitization")
        if isinstance(sanitized, dict)
        else None
    )
    if isinstance(metadata, dict):
        sanitized["_persistence_sanitization"] = {
            "raw_logs_removed": bool(metadata.get("raw_logs_removed")),
            "truncated": bool(
                metadata.get("truncated")
                or metadata.get("sensitive_values_redacted")
            ),
        }
    return sanitized


def _save_record(session: Session, inspection_type: str, request_payload: dict, result: dict) -> InspectionRecord:
    record = InspectionRecord(
        inspection_type=inspection_type,
        request_payload=sanitize_persistence_payload(request_payload),
        result_payload=sanitize_persistence_payload(result),
        summary_status=result["health_status"],
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def sanitize_inspection_response(payload: dict) -> dict:
    """Redact public DTO text while preserving its complete field structure."""

    return sanitize_public_payload(payload)


def run_cluster_inspection(
    session: Session,
    provider: InspectionProvider,
    registry: ComponentStatusRegistry | None = None,
    *,
    include_logs: bool = True,
) -> dict:
    policy = _load_inspection_policy(session)
    if include_logs:
        discovery = discovery_service.discover_namespaces(provider)
        _enforce_log_inspection_limit(
            sum(
                int(item.get("abnormal_pod_count") or 0)
                for item in discovery.get("namespaces", [])
            ),
            policy.max_log_pods,
        )
    result = provider.run_cluster_inspection(include_logs=include_logs)
    record = _save_record(session, "cluster", {}, result)
    _attach_v11_extension(
        session,
        provider,
        result,
        scope=InspectionScope(type=InspectionScopeType.cluster),
        inspection_record=record,
        registry=registry,
    )
    return sanitize_inspection_response(result)


def run_namespace_inspection(
    session: Session,
    provider: InspectionProvider,
    payload: NamespaceInspectionRequest,
    registry: ComponentStatusRegistry | None = None,
) -> dict:
    policy = _load_inspection_policy(session)
    limits = CollectionLimits(
        max_log_pods=policy.max_log_pods,
        namespace_concurrency=policy.namespace_concurrency,
    )
    if payload.include_logs:
        _enforce_log_inspection_limit(
            _estimate_namespace_log_pods(
                provider,
                payload.namespace,
                payload.label_selector,
            ),
            policy.max_log_pods,
        )
    try:
        result = provider.run_namespace_inspection(
            payload.namespace,
            payload.label_selector,
            include_logs=payload.include_logs,
            limits=limits,
        )
    except ProviderLogPodLimitExceededError as exc:
        raise LogInspectionScopeTooLargeError(
            exc.requested_pods,
            exc.limit,
        ) from exc
    _attach_namespace_evidence(session, result, payload.namespace, payload.label_selector)
    record = _save_record(session, "namespace", payload.model_dump(), result)
    _attach_v11_extension(
        session,
        provider,
        result,
        scope=InspectionScope(
            type=InspectionScopeType.namespace,
            namespace=payload.namespace,
            label_selector=payload.label_selector,
        ),
        inspection_record=record,
        registry=registry,
    )
    return sanitize_inspection_response(result)


def run_namespace_log_inspection(
    session: Session,
    provider: InspectionProvider,
    payload: NamespaceInspectionRequest,
) -> dict:
    policy = _load_inspection_policy(session)
    limits = CollectionLimits(
        max_log_pods=policy.max_log_pods,
        namespace_concurrency=policy.namespace_concurrency,
    )
    discovery = discovery_service.discover_namespace_pods(
        provider,
        payload.namespace,
        payload.label_selector,
    )
    pod_summaries = discovery.get("pods", [])
    _enforce_log_inspection_limit(len(pod_summaries), policy.max_log_pods)
    try:
        log_collection = provider.collect_pod_log_samples(
            payload.namespace,
            [str(item.get("name") or "") for item in pod_summaries],
            limits,
        )
    except ProviderLogPodLimitExceededError as exc:
        raise LogInspectionScopeTooLargeError(
            exc.requested_pods,
            exc.limit,
        ) from exc

    pods = []
    for item in pod_summaries:
        name = str(item.get("name") or "")
        container_logs = log_collection.container_samples.get(name, {})
        log_summary = "\n".join(
            f"[{container_name}] {sample}"
            for container_name, sample in container_logs.items()
            if sample
        ) or None
        previous_log_summary = log_collection.previous_samples.get(name)
        pod = {
            "name": name,
            "labels": item.get("labels") or {},
            "status": "unknown",
            "node_name": None,
            "restarts": 0,
            "containers": [
                {
                    "name": container_name,
                    "restart_count": 0,
                    "state": "unknown",
                    "reason": None,
                }
                for container_name in container_logs
            ],
            "events": [],
            "describe_summary": "日志巡检未采集 Pod 运行状态、事件、Service 或 Ingress。",
            "log_summary": log_summary,
            "container_log_summaries": container_logs,
            "previous_log_summary": previous_log_summary,
            "resource_usage": {},
            "related_resources": [],
        }
        pods.append(_attach_log_hits(session, payload.namespace, payload.label_selector, pod))

    result = {
        "inspection_target": {
            "type": "namespace",
            "namespace": payload.namespace,
            "pod_name": None,
            "label_selector": payload.label_selector,
            "saved_target_id": None,
            "template_id": None,
            "resource_scope": ["pod_logs"],
        },
        "namespace": payload.namespace,
        "label_selector": payload.label_selector,
        "health_status": "warning" if any(pod.get("log_hits") for pod in pods) else "healthy",
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "evidence_bundles": [_build_evidence_bundle(payload.namespace, pod) for pod in pods],
        "pods": pods,
        "services": [],
        "ingresses": [],
        "tls_secrets": [],
        "daemonsets": [],
        "issues": [],
        "coverage": [],
        "log_collection": {
            "pod_count": len(pod_summaries),
            "pods_read": log_collection.log_pods_read,
            "collected_log_bytes": log_collection.collected_log_bytes,
            "truncated": log_collection.truncated,
        },
    }
    _save_record(
        session,
        "namespace_log",
        payload.model_dump(),
        result,
    )
    return sanitize_inspection_response(result)


def run_namespace_batch_inspection(
    session: Session,
    provider: InspectionProvider,
    payload: NamespaceBatchInspectionRequest,
    registry: ComponentStatusRegistry | None = None,
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
            inspection = provider.run_namespace_inspection(
                namespace,
                None,
                include_logs=False,
            )
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
    persisted = result | {"health_status": overall_health_status}
    record = _save_record(session, "namespaces", payload.model_dump(), persisted)
    namespace_run, namespace_issues, namespace_coverage = _execute_v11_extension(
        session,
        provider,
        scope=InspectionScope(
            type=InspectionScopeType.namespace,
            namespaces=requested_namespaces,
        ),
        inspection_record=record,
        registry=registry,
    )
    cluster_run, cluster_issues, cluster_coverage = _execute_v11_extension(
        session,
        provider,
        scope=InspectionScope(type=InspectionScopeType.cluster),
        inspection_record=None,
        registry=registry,
    )
    result["issues"] = _merge_issue_payloads([*namespace_issues, *cluster_issues])
    result["coverage"] = _merge_coverage_payloads([*namespace_coverage, *cluster_coverage])
    record.result_payload = sanitize_persistence_payload(result)
    session.commit()
    result.pop("health_status", None)
    return sanitize_inspection_response(result)


def run_pod_inspection(
    session: Session,
    provider: InspectionProvider,
    payload: PodInspectionRequest,
    registry: ComponentStatusRegistry | None = None,
) -> dict:
    _enforce_log_inspection_limit(
        1,
        _load_inspection_policy(session).max_log_pods,
    )
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
    record = _save_record(session, "pod", payload.model_dump(), result)
    _attach_v11_extension(
        session,
        provider,
        result,
        scope=InspectionScope(
            type=InspectionScopeType.pod,
            namespace=payload.namespace,
            pod_name=payload.pod_name,
        ),
        inspection_record=record,
        registry=registry,
    )
    return sanitize_inspection_response(result)


def run_inspection(
    session: Session,
    provider: InspectionProvider,
    payload: InspectionRunRequest,
    registry: ComponentStatusRegistry | None = None,
) -> dict:
    if payload.target_type == InspectionTargetType.cluster:
        return {
            "target_type": payload.target_type,
            "cluster_result": run_cluster_inspection(session, provider, registry),
            "namespace_result": None,
            "pod_result": None,
        }

    if payload.target_type == InspectionTargetType.namespace:
        namespace_result = run_namespace_inspection(
            session,
            provider,
            NamespaceInspectionRequest(namespace=payload.namespace or "", label_selector=payload.label_selector),
            registry,
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
        registry,
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


def _estimate_namespace_log_pods(
    provider: InspectionProvider,
    namespace: str,
    label_selector: str | None,
) -> int:
    discovery = discovery_service.discover_namespace_pods(
        provider,
        namespace,
        label_selector,
    )
    return int(discovery.get("pod_count") or 0)


def _load_inspection_policy(session: Session) -> InspectionPolicySettings:
    settings = session.get(SystemSetting, 1)
    return InspectionPolicySettings.model_validate(
        policy_with_builtin_required_components(
            settings.inspection_policy if settings else None,
        )
    )


def _enforce_log_inspection_limit(
    estimated_pods: int,
    limit: int,
) -> None:
    if estimated_pods > limit:
        raise LogInspectionScopeTooLargeError(estimated_pods, limit)


def _attach_v11_extension(
    session: Session,
    provider: InspectionProvider,
    result: dict,
    *,
    scope: InspectionScope,
    inspection_record: InspectionRecord | None,
    registry: ComponentStatusRegistry | None = None,
) -> None:
    _, issues, coverage = _execute_v11_extension(
        session,
        provider,
        scope=scope,
        inspection_record=inspection_record,
        registry=registry,
    )
    result["issues"] = issues
    result["coverage"] = coverage
    inspection_record.result_payload = sanitize_persistence_payload(result)
    session.commit()


def _execute_v11_extension(
    session: Session,
    provider: InspectionProvider,
    *,
    scope: InspectionScope,
    inspection_record: InspectionRecord,
    registry: ComponentStatusRegistry | None = None,
):
    run, _ = execute_inspection(
        session,
        provider=provider,
        cluster_id=get_app_settings().cluster_id,
        scope=scope,
        trigger=InspectionTrigger.manual,
        inspection_record_id=inspection_record.id if inspection_record else None,
        registry=registry,
    )
    issues = [
        issue_from_model(row).model_dump(mode="json")
        for issue_id in run.issue_ids
        if (row := session.get(IssueModel, issue_id)) is not None
    ]
    coverage = [item.model_dump(mode="json") for item in run.coverage]
    return run, issues, coverage


def _merge_issue_payloads(issues: list[dict]) -> list[dict]:
    merged: dict[int | str, dict] = {}
    for issue in issues:
        key = issue.get("id") or issue.get("fingerprint") or str(issue)
        merged[key] = issue
    return list(merged.values())


def _merge_coverage_payloads(coverage: list[dict]) -> list[dict]:
    status_rank = {
        "failed": 0,
        "abnormal": 1,
        "skipped": 2,
        "passed": 3,
    }
    merged: dict[str, dict] = {}
    for item in coverage:
        check_code = str(item.get("check_code") or "")
        if not check_code:
            continue
        existing = merged.get(check_code)
        if existing is None:
            merged[check_code] = dict(item)
            continue
        existing_status = str(existing.get("status") or "passed")
        item_status = str(item.get("status") or "passed")
        if status_rank.get(item_status, 99) < status_rank.get(existing_status, 99):
            existing["status"] = item_status
        existing["checked_objects"] = int(existing.get("checked_objects") or 0) + int(item.get("checked_objects") or 0)
        existing["duration_ms"] = int(existing.get("duration_ms") or 0) + int(item.get("duration_ms") or 0)
        existing["issue_count"] = int(existing.get("issue_count") or 0) + int(item.get("issue_count") or 0)
        reasons = [
            str(reason)
            for reason in [existing.get("reason"), item.get("reason")]
            if reason
        ]
        unique_reasons = list(dict.fromkeys(reasons))
        existing["reason"] = "；".join(unique_reasons[:3]) if unique_reasons else None
    return list(merged.values())


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
        "resource_usage": _summarize_namespace_resource_usage(pods),
    }


def _summarize_namespace_resource_usage(pods: list[dict]) -> dict[str, str]:
    total_cpu_millicores = 0
    total_memory_bytes = 0
    sampled_pods = 0
    latest_sample_time = ""
    for pod in pods:
        usage = pod.get("resource_usage") or {}
        cpu = _parse_millicores(usage.get("cpu"))
        memory = _parse_memory_bytes(usage.get("memory"))
        if cpu is None and memory is None:
            continue
        sampled_pods += 1
        total_cpu_millicores += cpu or 0
        total_memory_bytes += memory or 0
        sample_time = str(usage.get("sample_time") or "")
        if sample_time > latest_sample_time:
            latest_sample_time = sample_time
    if sampled_pods == 0:
        return {}
    result = {
        "cpu": f"{total_cpu_millicores}m",
        "memory": _format_memory_bytes(total_memory_bytes),
        "sampled_pods": str(sampled_pods),
    }
    if latest_sample_time:
        result["sample_time"] = latest_sample_time
    return result


def _parse_millicores(value: object) -> int | None:
    if value is None:
        return None
    text = str(value)
    if not text.endswith("m"):
        return None
    try:
        return int(text[:-1])
    except ValueError:
        return None


def _parse_memory_bytes(value: object) -> int | None:
    if value is None:
        return None
    text = str(value)
    try:
        if text.endswith("Mi"):
            return int(float(text[:-2]) * 1024 * 1024)
        if text.endswith("Gi"):
            return int(float(text[:-2]) * 1024 * 1024 * 1024)
    except ValueError:
        return None
    return None


def _format_memory_bytes(value: int) -> str:
    mib = value / 1024 / 1024
    if mib >= 1024:
        return f"{mib / 1024:.1f}Gi"
    return f"{mib:.0f}Mi"


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
