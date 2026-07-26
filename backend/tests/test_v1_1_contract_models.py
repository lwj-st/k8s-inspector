from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.schemas.v1_1 import (
    AdminSession,
    ApiError,
    CheckStatus,
    CheckEvaluation,
    CollectionLayer,
    Coverage,
    DataRetentionSettings,
    Evidence,
    EvidenceSource,
    HealthStatus,
    InspectionCheckResult,
    InspectionPolicySettings,
    InspectionPlanCreate,
    InspectionPlanScope,
    InspectionPlanScopeType,
    InspectionRun,
    InspectionRunDetail,
    InspectionRunStatus,
    InspectionScope,
    InspectionThresholds,
    InspectionTrigger,
    Issue,
    IssueAcknowledgeRequest,
    IssueCandidate,
    IssueCode,
    IssueEvent,
    IssueEventType,
    IssueListFilter,
    IssueSeverity,
    IssueSortMode,
    IssueStatus,
    NotificationChannel,
    NotificationChannelCreate,
    NotificationChannelType,
    NotificationChannelUpdate,
    NotificationDelivery,
    NotificationDeliveryStatus,
    NotificationEventType,
    NotificationMessage,
    PlanInterval,
    PlanSchedule,
    Page,
    PageParams,
    ProviderCollectionRequest,
    ProviderObservation,
    RequiredComponentPolicy,
    ResourceMetricState,
    ResourceRef,
    SecurityAuditAction,
    SecurityAuditLog,
    SecurityAuditOutcome,
    SystemComponentStatus,
    V11InspectionExtension,
    V11SettingsExtension,
    V11SettingsUpdateExtension,
    WebhookTargetPolicy,
    build_inspection_scope_key,
    build_issue_fingerprint,
)


NOW = datetime(2026, 7, 26, 8, 0, tzinfo=timezone.utc)
RESOURCE = ResourceRef(kind="Pod", namespace="demo", name="api-0")


def make_issue(**changes: object) -> Issue:
    payload: dict[str, object] = {
        "id": 1,
        "cluster_id": "prod-shanghai",
        "issue_code": IssueCode.POD_NOT_READY,
        "fingerprint": build_issue_fingerprint(
            cluster_id="prod-shanghai",
            source_check="pod.runtime",
            issue_code=IssueCode.POD_NOT_READY,
            resource=RESOURCE,
        ),
        "severity": IssueSeverity.warning,
        "status": IssueStatus.open,
        "scope": "pod",
        "resource": RESOURCE,
        "summary": "Pod 未就绪",
        "reason": "Ready Condition 为 False",
        "suggestion": "检查探针和容器事件",
        "evidence": [
            Evidence(
                code="pod_ready_condition",
                source=EvidenceSource.kubernetes_api,
                summary="Ready=False",
                facts={"condition": "Ready", "status": "False"},
                observed_at=NOW,
            )
        ],
        "first_seen_at": NOW,
        "last_seen_at": NOW,
        "occurrence_count": 1,
        "source_check": "pod.runtime",
    }
    payload.update(changes)
    return Issue.model_validate(payload)


def test_fingerprint_is_stable_and_ignores_mutable_issue_text() -> None:
    first = make_issue(summary="第一次文案", severity=IssueSeverity.warning)
    second = make_issue(summary="调整后的文案", severity=IssueSeverity.critical)

    assert first.fingerprint == second.fingerprint
    assert len(first.fingerprint) == 64


@pytest.mark.parametrize(("cluster_id", "source_check"), [("", "pod.runtime"), ("prod", " ")])
def test_fingerprint_rejects_empty_identity_inputs(cluster_id: str, source_check: str) -> None:
    with pytest.raises(ValueError):
        build_issue_fingerprint(
            cluster_id=cluster_id,
            source_check=source_check,
            issue_code=IssueCode.POD_NOT_READY,
            resource=RESOURCE,
        )


def test_issue_recovery_and_acknowledgement_are_independent() -> None:
    acknowledged = make_issue(acknowledged_at=NOW, acknowledge_note="已安排处理")
    assert acknowledged.status == IssueStatus.open

    recovered = make_issue(status=IssueStatus.recovered, recovered_at=NOW)
    assert recovered.status == IssueStatus.recovered

    with pytest.raises(ValidationError):
        make_issue(status=IssueStatus.recovered, recovered_at=None)

    with pytest.raises(ValidationError):
        make_issue(
            status=IssueStatus.recovered,
            last_seen_at=NOW,
            recovered_at=NOW - timedelta(seconds=1),
        )

    with pytest.raises(ValidationError):
        IssueAcknowledgeRequest(note=" ")


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        (CheckStatus.passed, None),
        (CheckStatus.abnormal, "发现异常"),
        (CheckStatus.skipped, "Metrics API 未安装"),
        (CheckStatus.failed, "Kubernetes API 超时"),
    ],
)
def test_coverage_expresses_all_execution_states(status: CheckStatus, reason: str | None) -> None:
    coverage = Coverage(
        check_code="pod.runtime",
        name="Pod 运行状态",
        status=status,
        reason=reason,
        checked_objects=2,
        duration_ms=12,
    )
    assert coverage.status == status


def test_skipped_and_failed_coverage_require_a_reason() -> None:
    with pytest.raises(ValidationError):
        Coverage(
            check_code="metrics.resource",
            name="资源指标",
            status=CheckStatus.skipped,
            checked_objects=0,
            duration_ms=1,
        )


def test_evidence_forbids_raw_logs_sensitive_keys_and_oversized_payloads() -> None:
    with pytest.raises(ValidationError):
        Evidence(
            code="unsafe",
            source=EvidenceSource.log_match,
            summary="不安全证据",
            facts={"raw_log": "Authorization: bearer secret"},
            observed_at=NOW,
        )

    with pytest.raises(ValidationError):
        Evidence.model_validate(
            {
                "code": "unsafe",
                "source": "log_match",
                "summary": "不安全证据",
                "facts": {},
                "observed_at": NOW,
                "raw_logs": ["full log"],
            }
        )

    with pytest.raises(ValidationError):
        Evidence(
            code="too_large",
            source=EvidenceSource.kubernetes_api,
            summary="超限",
            facts={"context": "x" * (64 * 1024)},
            observed_at=NOW,
        )


def test_inspection_run_supports_partial_success_and_collection_counters() -> None:
    run = InspectionRun(
        id=10,
        trigger=InspectionTrigger.scheduled,
        status=InspectionRunStatus.partial,
        scope=InspectionScope(type="namespace", namespaces=["demo"]),
        plan_id=3,
        started_at=NOW,
        finished_at=NOW,
        coverage=[
            Coverage(
                check_code="pod.runtime",
                name="Pod 运行状态",
                status="passed",
                checked_objects=2,
                duration_ms=10,
            ),
            Coverage(
                check_code="metrics.resource",
                name="资源指标",
                status="skipped",
                reason="Metrics API 未安装",
                checked_objects=0,
                duration_ms=2,
            ),
        ],
        kubernetes_api_calls=5,
        log_pods_read=0,
        collected_log_bytes=0,
        duration_ms=12,
    )
    assert run.status == InspectionRunStatus.partial
    assert run.coverage[1].status == CheckStatus.skipped


def test_inspection_check_result_has_explicit_run_check_and_scope() -> None:
    scope = InspectionScope(type="namespace", namespace="demo")
    result = InspectionCheckResult(
        id=1,
        run_id=10,
        check_code="pod.runtime",
        name="Pod 运行状态",
        status="failed",
        reason="demo 名称空间 API 超时",
        checked_objects=0,
        duration_ms=1000,
        issue_count=0,
        scope=scope,
        scope_key=build_inspection_scope_key(scope),
        completed_at=NOW,
    )
    assert result.run_id == 10
    assert result.scope.namespace == "demo"

    mismatched_payload = result.model_dump()
    mismatched_payload["scope_key"] = "0" * 64
    with pytest.raises(ValidationError):
        InspectionCheckResult.model_validate(mismatched_payload)

    with pytest.raises(ValidationError):
        InspectionScope(type="namespace", namespace="demo", namespaces=["prod"])


def test_scope_key_distinguishes_namespaces_and_normalizes_namespace_list_order() -> None:
    demo_scope = InspectionScope(type="namespace", namespace="demo")
    prod_scope = InspectionScope(type="namespace", namespace="prod")
    demo_result = InspectionCheckResult(
        id=1,
        run_id=10,
        check_code="pod.runtime",
        name="Pod 运行状态",
        status="passed",
        checked_objects=2,
        duration_ms=10,
        scope=demo_scope,
        scope_key=build_inspection_scope_key(demo_scope),
        completed_at=NOW,
    )
    prod_result = InspectionCheckResult(
        id=2,
        run_id=10,
        check_code="pod.runtime",
        name="Pod 运行状态",
        status="failed",
        reason="prod API 超时",
        checked_objects=0,
        duration_ms=100,
        scope=prod_scope,
        scope_key=build_inspection_scope_key(prod_scope),
        completed_at=NOW,
    )
    first_order = build_inspection_scope_key(
        InspectionScope(type="namespace", namespaces=["demo", "prod"])
    )
    second_order = build_inspection_scope_key(
        InspectionScope(type="namespace", namespaces=["prod", "demo"])
    )

    assert demo_result.run_id == prod_result.run_id
    assert demo_result.check_code == prod_result.check_code
    assert demo_result.scope_key != prod_result.scope_key
    assert first_order == second_order


def test_inspection_run_detail_returns_scoped_check_results() -> None:
    scope = InspectionScope(type="namespace", namespace="demo")
    detail = InspectionRunDetail(
        id=10,
        trigger="manual",
        status="partial",
        scope=scope,
        check_results=[
            InspectionCheckResult(
                id=1,
                run_id=10,
                check_code="pod.runtime",
                name="Pod 运行状态",
                status="failed",
                reason="demo API 超时",
                checked_objects=0,
                duration_ms=100,
                scope=scope,
                scope_key=build_inspection_scope_key(scope),
                completed_at=NOW,
            )
        ],
    )
    assert detail.check_results[0].scope_key == build_inspection_scope_key(scope)

    invalid_payload = detail.model_dump()
    invalid_payload["check_results"][0]["run_id"] = 11
    with pytest.raises(ValidationError):
        InspectionRunDetail.model_validate(invalid_payload)


def test_inspection_policy_defaults_and_required_component_locator() -> None:
    settings = InspectionPolicySettings(
        required_components=[
            RequiredComponentPolicy(
                name="生产 Ingress Controller",
                namespace="ingress-nginx",
                kind="Deployment",
                label_selector="app.kubernetes.io/component=controller",
            )
        ]
    )
    thresholds = settings.thresholds
    assert thresholds == InspectionThresholds()
    assert thresholds.tls_warning_days == 30
    assert thresholds.tls_critical_days == 7
    assert thresholds.pvc_pending_warning_minutes == 5
    assert thresholds.pvc_pending_critical_minutes == 30
    assert thresholds.pv_released_stale_hours == 24
    assert thresholds.job_incomplete_info_minutes == 60
    assert thresholds.resource_usage_warning_percent == 90
    assert thresholds.resource_usage_consecutive_cycles == 3
    assert thresholds.pod_terminating_warning_minutes == 10
    assert thresholds.pod_restart_window_minutes == 10
    assert thresholds.pod_restart_delta == 3
    assert thresholds.warning_event_window_minutes == 30
    assert thresholds.node_not_ready_grace_seconds == 0
    assert settings.namespace_concurrency == 3
    assert settings.max_log_pods == 200
    assert settings.retention == DataRetentionSettings()
    assert settings.retention.inspection_run_days == 30
    assert settings.retention.recovered_issue_days == 90
    assert settings.retention.notification_delivery_days == 30
    assert settings.retention.security_audit_days == 90
    assert V11SettingsExtension().inspection_policy.required_components == []
    assert V11SettingsUpdateExtension().inspection_policy is None

    with pytest.raises(ValidationError):
        V11SettingsUpdateExtension(inspection_policy=None)

    with pytest.raises(ValidationError):
        InspectionThresholds(node_not_ready_grace_seconds=3601)

    with pytest.raises(ValidationError):
        InspectionPolicySettings(namespace_concurrency=0)
    with pytest.raises(ValidationError):
        InspectionPolicySettings(max_log_pods=0)
    with pytest.raises(ValidationError):
        InspectionPolicySettings(max_log_pods=1001)

    with pytest.raises(ValidationError):
        InspectionPolicySettings(
            required_components=[
                RequiredComponentPolicy(
                    name="first",
                    namespace="ingress-nginx",
                    kind="Deployment",
                    label_selector="app=controller",
                ),
                RequiredComponentPolicy(
                    name="duplicate",
                    namespace="ingress-nginx",
                    kind="deployment",
                    label_selector="app=controller",
                ),
            ]
        )


@pytest.mark.parametrize(
    "field_name",
    [
        "inspection_run_days",
        "recovered_issue_days",
        "notification_delivery_days",
        "security_audit_days",
    ],
)
@pytest.mark.parametrize("invalid_value", [6, 181])
def test_data_retention_fields_are_bounded(
    field_name: str,
    invalid_value: int,
) -> None:
    with pytest.raises(ValidationError):
        DataRetentionSettings(**{field_name: invalid_value})


def test_daily_plan_requires_time_and_namespace_scope_requires_namespaces() -> None:
    plan = InspectionPlanCreate(
        name="每日巡检",
        scope=InspectionPlanScope(type=InspectionPlanScopeType.namespaces, namespaces=["demo"]),
        schedule=PlanSchedule(interval=PlanInterval.daily, daily_at="02:30", timezone="Asia/Shanghai"),
        notification_channel_ids=[1],
    )
    assert plan.schedule.daily_at == "02:30"

    with pytest.raises(ValidationError):
        InspectionPlanScope(type=InspectionPlanScopeType.namespaces)

    with pytest.raises(ValidationError):
        PlanSchedule(interval=PlanInterval.daily)


def test_notification_channel_response_never_contains_credentials() -> None:
    create = NotificationChannelCreate(
        name="飞书生产告警",
        type=NotificationChannelType.feishu_custom_bot,
        webhook_url="https://open.feishu.cn/open-apis/bot/v2/hook/credential",
        signing_secret="signing-secret",
        mention_all_on_critical=True,
    )
    dumped_create = create.model_dump(mode="json")
    assert "credential" not in str(dumped_create)
    assert "signing-secret" not in str(dumped_create)

    channel = NotificationChannel(
        id=1,
        name=create.name,
        type=create.type,
        enabled=True,
        endpoint_masked="https://open.feishu.cn/***ential",
        signing_secret_configured=True,
        mention_all_on_critical=True,
        timeout_seconds=5,
        created_at=NOW,
        updated_at=NOW,
    )
    dumped_response = channel.model_dump(mode="json")
    assert "webhook_url" not in dumped_response
    assert "signing_secret" not in dumped_response

    with pytest.raises(ValidationError):
        NotificationChannelCreate.model_validate(
            {
                "name": "越界能力",
                "type": "feishu_custom_bot",
                "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/x",
                "app_id": "not-supported",
            }
        )


@pytest.mark.parametrize(
    "url",
    [
        "http://open.feishu.cn/open-apis/bot/v2/hook/token",
        "https://example.com/open-apis/bot/v2/hook/token",
        "https://open.feishu.cn/open-apis/bot/v1/hook/token",
        "https://open.feishu.cn/open-apis/bot/v2/hook/",
    ],
)
def test_feishu_channel_rejects_non_v2_official_webhook_urls(url: str) -> None:
    with pytest.raises(ValidationError):
        NotificationChannelCreate(
            name="非法飞书地址",
            type=NotificationChannelType.feishu_custom_bot,
            webhook_url=url,
        )


def test_generic_webhook_url_is_governed_by_target_policy_and_channel_type_is_immutable() -> None:
    channel = NotificationChannelCreate(
        name="开发环境 Webhook",
        type=NotificationChannelType.generic_webhook,
        webhook_url="http://hooks.example.com/alerts",
    )
    assert channel.type == NotificationChannelType.generic_webhook

    with pytest.raises(ValidationError):
        NotificationChannelUpdate.model_validate({"type": "feishu_custom_bot"})


def test_notification_message_and_delivery_expose_failure_without_raw_response() -> None:
    message = NotificationMessage(
        event_type=NotificationEventType.issue_opened,
        cluster_id="prod-shanghai",
        issue_id=1,
        fingerprint=make_issue().fingerprint,
        issue_status=IssueStatus.open,
        severity=IssueSeverity.warning,
        summary="Pod 未就绪",
        resource=RESOURCE,
        first_seen_at=NOW,
        last_seen_at=NOW,
        evidence_summaries=["Ready=False"],
        suggestion="检查探针",
        detail_url="https://inspector.example.com/issues/1",
    )
    delivery = NotificationDelivery(
        id=9,
        channel_id=1,
        deduplication_key="channel:1:event:2",
        issue_event_id=2,
        event_type=message.event_type,
        status=NotificationDeliveryStatus.failed,
        attempt_count=3,
        error_code="timeout",
        error_message="请求超时",
        created_at=NOW,
        updated_at=NOW,
    )
    assert delivery.status == NotificationDeliveryStatus.failed
    assert "response_body" not in delivery.model_dump(mode="json")


def test_layered_collection_and_check_evaluation_keep_responsibilities_separate() -> None:
    status_request = ProviderCollectionRequest(
        scope=InspectionScope(type="cluster"),
        layer=CollectionLayer.status,
        trigger=InspectionTrigger.scheduled,
    )
    assert status_request.include_logs is False
    assert status_request.thresholds == InspectionThresholds()

    with pytest.raises(ValidationError):
        ProviderCollectionRequest(
            scope=InspectionScope(type="cluster"),
            layer=CollectionLayer.status,
            include_logs=True,
            trigger=InspectionTrigger.scheduled,
        )

    evaluation = CheckEvaluation(
        scope=InspectionScope(type="namespace", namespace="demo"),
        scope_key=build_inspection_scope_key(InspectionScope(type="namespace", namespace="demo")),
        coverage=Coverage(
            check_code="pod.runtime",
            name="Pod 运行状态",
            status="abnormal",
            reason="Pod 未就绪",
            checked_objects=1,
            duration_ms=3,
            issue_count=1,
        ),
        issue_candidates=[
            IssueCandidate(
                issue_code="POD_NOT_READY",
                severity="warning",
                scope="pod",
                resource=RESOURCE,
                summary="Pod 未就绪",
                reason="Ready=False",
                suggestion="检查探针",
                source_check="pod.runtime",
            )
        ],
    )
    assert evaluation.issue_candidates[0].issue_code == IssueCode.POD_NOT_READY
    assert evaluation.scope.namespace == "demo"

    with pytest.raises(ValidationError):
        CheckEvaluation(
            scope=InspectionScope(type="namespace", namespace="demo"),
            scope_key=build_inspection_scope_key(InspectionScope(type="namespace", namespace="demo")),
            coverage=Coverage(
                check_code="pod.runtime",
                name="Pod 运行状态",
                status="abnormal",
                reason="Pod 未就绪",
                checked_objects=1,
                duration_ms=3,
                issue_count=0,
            ),
            issue_candidates=evaluation.issue_candidates,
        )

    mismatched_candidate = evaluation.issue_candidates[0].model_copy(update={"source_check": "pod.other"})
    with pytest.raises(ValidationError):
        CheckEvaluation(
            scope=evaluation.scope,
            scope_key=evaluation.scope_key,
            coverage=evaluation.coverage,
            issue_candidates=[mismatched_candidate],
        )


def test_provider_request_carries_an_immutable_run_threshold_snapshot() -> None:
    run_a_thresholds = InspectionThresholds(
        warning_event_window_minutes=15,
        pod_restart_window_minutes=5,
    )
    run_a_status = ProviderCollectionRequest(
        scope=InspectionScope(type="cluster"),
        layer=CollectionLayer.status,
        trigger=InspectionTrigger.scheduled,
        thresholds=run_a_thresholds,
    )
    run_a_evidence = ProviderCollectionRequest(
        scope=InspectionScope(type="cluster"),
        layer=CollectionLayer.evidence,
        evidence_targets=[RESOURCE],
        include_events=True,
        trigger=InspectionTrigger.scheduled,
        thresholds=run_a_thresholds,
    )
    run_b = ProviderCollectionRequest(
        scope=InspectionScope(type="cluster"),
        layer=CollectionLayer.status,
        trigger=InspectionTrigger.scheduled,
        thresholds=InspectionThresholds(
            warning_event_window_minutes=60,
            pod_restart_window_minutes=20,
        ),
    )

    assert run_a_status.thresholds == run_a_evidence.thresholds
    assert run_a_status.thresholds.warning_event_window_minutes == 15
    assert run_a_status.thresholds.pod_restart_window_minutes == 5
    assert run_b.thresholds.warning_event_window_minutes == 60
    assert run_b.thresholds.pod_restart_window_minutes == 20
    assert run_a_status.thresholds is not run_b.thresholds

    with pytest.raises(ValidationError):
        run_a_status.thresholds.warning_event_window_minutes = 30


def test_all_public_details_and_facts_reject_sensitive_keys() -> None:
    with pytest.raises(ValidationError):
        ApiError(code="unsafe", message="请求失败", details={"authorization": "bearer secret"})

    with pytest.raises(ValidationError):
        SystemComponentStatus(
            state="failed",
            message="配置错误",
            checked_at=NOW,
            details={"api_key": "secret"},
        )

    with pytest.raises(ValidationError):
        ProviderObservation(
            resource=RESOURCE,
            observed_at=NOW,
            facts={"access_token": "secret"},
        )


def test_resource_metric_state_has_no_long_term_series() -> None:
    state = ResourceMetricState(
        id=1,
        cluster_id="prod-shanghai",
        resource=RESOURCE,
        container_name="api",
        sampled_at=NOW,
        cpu_millicores=125,
        memory_bytes=128 * 1024 * 1024,
        cpu_limit_millicores=500,
        memory_limit_bytes=512 * 1024 * 1024,
        consecutive_cpu_over_threshold=0,
        consecutive_memory_over_threshold=0,
        stale=False,
        updated_at=NOW,
    )
    assert state.cpu_millicores == 125
    assert "samples" not in state.model_dump(mode="json")


def test_admin_session_and_audit_response_do_not_expose_session_token() -> None:
    session = AdminSession(
        authenticated=True,
        username="admin",
        csrf_token="csrf-public-response-token",
        idle_expires_at=NOW,
        absolute_expires_at=NOW,
    )
    audit = SecurityAuditLog(
        id=1,
        action=SecurityAuditAction.login_succeeded,
        outcome=SecurityAuditOutcome.success,
        actor="admin",
        occurred_at=NOW,
        details={"auth_mode": "local"},
    )
    assert "token_hash" not in session.model_dump(mode="json")
    assert audit.action == SecurityAuditAction.login_succeeded

    with pytest.raises(ValidationError):
        SecurityAuditLog(
            id=2,
            action=SecurityAuditAction.login_failed,
            outcome=SecurityAuditOutcome.denied,
            occurred_at=NOW,
            details={"password": "do-not-store"},
        )


def test_v1_inspection_extension_is_additive_and_defaults_to_empty_lists() -> None:
    extension = V11InspectionExtension()
    assert extension.issues == []
    assert extension.coverage == []


def test_webhook_policy_requires_no_redirects_and_explicit_allowlist() -> None:
    policy = WebhookTargetPolicy(allowed_hosts=["hooks.example.com"])
    assert policy.follow_redirects is False
    assert policy.block_private_networks is True

    with pytest.raises(ValidationError):
        WebhookTargetPolicy(allowed_hosts=[], allowed_cidrs=[])


def test_issue_event_supports_recovery_and_manual_trigger() -> None:
    event = IssueEvent(
        id=3,
        issue_id=1,
        run_id=10,
        event_type=IssueEventType.recovered,
        trigger=InspectionTrigger.manual,
        previous_status=IssueStatus.open,
        new_status=IssueStatus.recovered,
        occurred_at=NOW,
        summary="本轮检查成功且问题未再命中",
    )
    assert event.event_type == IssueEventType.recovered
    assert event.trigger == InspectionTrigger.manual


def test_issue_event_timeline_uses_bounded_page_contract() -> None:
    event = IssueEvent(
        id=3,
        issue_id=1,
        run_id=10,
        event_type=IssueEventType.recovered,
        trigger=InspectionTrigger.manual,
        previous_status=IssueStatus.open,
        new_status=IssueStatus.recovered,
        occurred_at=NOW,
        summary="问题已恢复",
    )
    page = Page[IssueEvent](items=[event], total=1, page=1, page_size=20)
    assert page.items[0].issue_id == 1

    with pytest.raises(ValidationError):
        PageParams(page=0)
    with pytest.raises(ValidationError):
        PageParams(page_size=101)


@pytest.mark.parametrize(
    "mode",
    [IssueSortMode.priority, IssueSortMode.duration, IssueSortMode.last_changed],
)
def test_issue_list_sort_is_restricted_and_defaults_to_priority(mode: IssueSortMode) -> None:
    assert IssueListFilter(sort=mode).sort == mode
    assert IssueListFilter().sort == IssueSortMode.priority

    with pytest.raises(ValidationError):
        IssueListFilter(sort="summary")
