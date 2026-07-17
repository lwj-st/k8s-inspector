import pytest
from pydantic import ValidationError

from app.schemas.common import AbnormalCategory, EvidenceBundle, InspectionTarget, KeywordHit, TemplateCondition, TemplateTarget
from app.schemas.inspection import (
    NamespaceBatchInspectionRequest,
    NamespaceBatchInspectionResponse,
    NamespaceDiscoveryResponse,
    NamespaceSummary,
)
from app.schemas.template import FaultTemplateCreate


def test_template_contract_supports_typed_targets_and_conditions(client) -> None:
    payload = {
        "name": "Pod CrashLoop",
        "scenario": "targeted_diagnosis",
        "targets": [
            {
                "target_ref": "demo-api",
                "namespace": "demo",
                "label_selector": "app=demo",
                "resource_scope": ["pods"],
            }
        ],
        "match_conditions": [
            {
                "target_ref": "demo-api",
                "condition_type": "pod_status",
                "operator": "in",
                "expected_value": ["CrashLoopBackOff"],
                "join_operator": "AND",
                "enabled": True,
            }
        ],
        "reason": "Application startup failure",
        "suggestion": "Check startup configuration",
        "command": "kubectl logs -n demo deploy/demo",
        "risk_note": "Read-only command",
        "enabled": True,
    }

    response = client.post("/api/v1/templates", json=payload)

    assert response.status_code == 201
    body = response.json()
    assert body["targets"][0]["target_ref"] == "demo-api"
    assert body["match_conditions"][0]["condition_type"] == "pod_status"


def test_whitelist_contract_supports_pod_and_container_scope(client) -> None:
    payload = {
        "namespace": "demo",
        "label_selector": "app=demo",
        "pod_name_pattern": "demo-api-*",
        "container_name": "api",
        "keyword": "connection refused",
        "enabled": True,
        "note": "known harmless in warmup",
    }

    response = client.post("/api/v1/whitelists", json=payload)

    assert response.status_code == 201
    body = response.json()
    assert body["pod_name_pattern"] == "demo-api-*"
    assert body["container_name"] == "api"


def test_namespace_inspection_response_exposes_unified_target_and_evidence(client) -> None:
    response = client.post(
        "/api/v1/inspections/namespace/run",
        json={"namespace": "demo", "label_selector": "app=demo"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["inspection_target"]["type"] == "namespace"
    assert body["inspection_target"]["namespace"] == "demo"
    assert body["evidence_bundles"][0]["object_type"] == "pod"
    assert body["evidence_bundles"][0]["log_hits"][0]["keyword"] == "connection refused"


def test_diagnosis_response_exposes_unified_target_and_match_results(client) -> None:
    client.post(
        "/api/v1/templates",
        json={
            "name": "CrashLoop template",
            "scenario": "targeted_diagnosis",
            "targets": [
                {
                    "target_ref": "demo-api",
                    "namespace": "demo",
                    "label_selector": "app=demo",
                    "resource_scope": ["pods"],
                }
            ],
            "match_conditions": [
                {
                    "target_ref": "demo-api",
                    "condition_type": "pod_status",
                    "operator": "in",
                    "expected_value": ["CrashLoopBackOff"],
                    "join_operator": "AND",
                    "enabled": True,
                }
            ],
            "reason": "Dependency startup failure",
            "suggestion": "Check downstream service",
            "enabled": True,
        },
    )

    response = client.post("/api/v1/diagnoses/run", json={"namespace": "demo", "scope": "deployment/demo-api"})

    assert response.status_code == 200
    body = response.json()
    assert body["inspection_target"]["type"] == "namespace"
    assert isinstance(body["template_match_results"], list)


def test_common_contract_models_validate_expected_fields() -> None:
    target = InspectionTarget(type="template", namespace="demo", template_id=7, resource_scope=["pods"])
    hit = KeywordHit(
        keyword="connection refused",
        category="dependency",
        severity="warning",
        source="current_log",
        matched_text="database connection refused",
        container_name="api",
        whitelisted=False,
        whitelist_rule_id=None,
    )
    evidence = EvidenceBundle(
        object_type="pod",
        namespace="demo",
        name="demo-api-123",
        status="CrashLoopBackOff",
        node_name="node-a",
        restarts=4,
        describe_summary="container exited during startup",
        events=["Back-off restarting failed container"],
        resource_usage={"cpu": "220m", "memory": "180Mi"},
        log_hits=[hit],
        related_resources=[],
    )
    condition = TemplateCondition(
        target_ref="demo-api",
        condition_type="log_keyword",
        operator="contains",
        expected_value="connection refused",
        join_operator="AND",
        enabled=True,
    )
    template_target = TemplateTarget(
        target_ref="demo-api",
        namespace="demo",
        label_selector="app=demo",
        resource_scope=["pods"],
    )

    assert target.template_id == 7
    assert evidence.log_hits[0].keyword == "connection refused"
    assert condition.expected_value == "connection refused"
    assert template_target.label_selector == "app=demo"


def test_common_contract_models_accept_legacy_aliases() -> None:
    template_target = TemplateTarget(
        ref="demo-api",
        namespace="demo",
        label_selector="app=demo",
        name="demo-api-*",
        scopes=["pods"],
    )
    condition = TemplateCondition(
        target_ref="demo-api",
        type="log_keyword",
        operator="contains",
        value="connection refused",
        join_operator="AND",
    )

    assert template_target.target_ref == "demo-api"
    assert template_target.pod_name_pattern == "demo-api-*"
    assert template_target.resource_scope == ["pods"]
    assert condition.condition_type == "log_keyword"
    assert condition.expected_value == "connection refused"


def test_fault_template_prefers_targets_and_keeps_target_groups_compatibility() -> None:
    template = FaultTemplateCreate(
        name="legacy template",
        scenario="legacy",
        target_groups=[
            {
                "ref": "api",
                "namespace": "demo",
                "label_selector": "app=demo-api",
                "object_scope": "pods",
            }
        ],
        match_conditions=[
            {
                "type": "pod_status",
                "operator": "in",
                "value": ["CrashLoopBackOff"],
            }
        ],
        joint_rule={"operator": "AND"},
        reason="legacy reason",
        suggestion="legacy suggestion",
    )

    assert template.targets[0].target_ref == "api"
    assert template.targets[0].resource_scope == ["pods"]
    assert template.match_conditions[0].target_ref == "api"
    assert template.match_conditions[0].join_operator == "AND"


def test_namespace_discovery_contract_exposes_summary_fields() -> None:
    response = NamespaceDiscoveryResponse(
        executed_at="2026-07-12T10:00:00Z",
        namespaces=[
            NamespaceSummary(
                name="demo",
                status="warning",
                pod_count=6,
                abnormal_pod_count=2,
                last_inspected_at="2026-07-12T09:58:00Z",
                labels={"team": "platform"},
                abnormal_categories=[AbnormalCategory.pod_status, AbnormalCategory.log_keyword],
            )
        ],
    )

    assert response.namespaces[0].name == "demo"
    assert response.namespaces[0].abnormal_categories == [
        AbnormalCategory.pod_status,
        AbnormalCategory.log_keyword,
    ]


def test_namespace_batch_request_requires_namespaces_or_all_namespaces() -> None:
    with pytest.raises(ValidationError):
        NamespaceBatchInspectionRequest()

    payload = NamespaceBatchInspectionRequest(namespaces=["demo", "prod"])
    assert payload.namespaces == ["demo", "prod"]
    assert payload.all_namespaces is False

    all_payload = NamespaceBatchInspectionRequest(all_namespaces=True)
    assert all_payload.all_namespaces is True


def test_namespace_batch_response_uses_summary_and_detail_target() -> None:
    response = NamespaceBatchInspectionResponse(
        executed_at="2026-07-12T10:00:00Z",
        all_namespaces=False,
        requested_namespaces=["demo"],
        results=[
            {
                "summary": {
                    "name": "demo",
                    "status": "warning",
                    "pod_count": 4,
                    "abnormal_pod_count": 1,
                    "last_inspected_at": "2026-07-12T10:00:00Z",
                    "labels": {"team": "platform"},
                    "abnormal_categories": ["event"],
                },
                "health_status": "warning",
                "detail_target": {
                    "type": "namespace",
                    "namespace": "demo",
                    "resource_scope": ["pods", "events"],
                },
            }
        ],
    )

    assert response.results[0].summary.abnormal_categories == [AbnormalCategory.event]
    assert response.results[0].detail_target.namespace == "demo"


def test_common_contract_models_reject_unknown_enum_values() -> None:
    with pytest.raises(ValidationError):
        KeywordHit(
            keyword="connection refused",
            category="dependency",
            severity="fatal",
            source="current_log",
            matched_text="database connection refused",
        )

    with pytest.raises(ValidationError):
        TemplateCondition(
            target_ref="demo-api",
            condition_type="unknown_condition",
            operator="contains",
            expected_value="value",
        )

    with pytest.raises(ValidationError):
        TemplateCondition(
            target_ref="demo-api",
            condition_type="log_keyword",
            operator="regex",
            expected_value="value",
        )

    with pytest.raises(ValidationError):
        NamespaceSummary(
            name="demo",
            status="warning",
            pod_count=1,
            abnormal_pod_count=1,
            labels={},
            abnormal_categories=["unknown_category"],
        )
