from datetime import datetime, timedelta, timezone

import httpx
from app.models import Issue as IssueModel
from app.models import IssueEvent as IssueEventModel
from app.models import InspectionPlan as InspectionPlanModel
from app.models import NotificationChannel as NotificationChannelModel
from app.models import NotificationDelivery as NotificationDeliveryModel
from app.models import MaintenanceSilenceWindow as MaintenanceSilenceWindowModel
from app.schemas.v1_1 import (
    IssueSeverity,
    IssueStatus,
    NotificationEventType,
    NotificationMessage,
    ResourceRef,
)
from app.models.v1_1 import inspection_plan_channels
from app.security.crypto import SensitiveValueCipher
from app.security.outbound import ValidatedOutboundTarget
from app.services import notification_delivery, notification_service
from app.services.notification_adapter import (
    FEISHU_MAX_BODY_BYTES,
    build_feishu_payload,
    serialized_body,
)
from app.services import notification_transport
from app.services.notification_transport import SendResult
from app.services.issue_lifecycle import LifecycleChange


def _message(
    *,
    severity=IssueSeverity.critical,
    mention_all=False,
    evidence=None,
    now: datetime | None = None,
    suggestion="检查容器状态",
):
    now = now or datetime.now(timezone.utc)
    return NotificationMessage(
        event_type=NotificationEventType.issue_opened,
        cluster_id="cluster-a",
        issue_id=1,
        fingerprint="a" * 64,
        issue_status=IssueStatus.open,
        severity=severity,
        summary="Pod 未就绪",
        resource=ResourceRef(kind="Pod", namespace="demo", name="api-0"),
        first_seen_at=now,
        last_seen_at=now,
        evidence_summaries=evidence or ["Ready=False"],
        suggestion=suggestion,
        detail_url="https://inspector.example.com/issues/1",
        mention_all=mention_all,
    )


def _target():
    return ValidatedOutboundTarget(
        original_url="https://hooks.example.com/v1/notify",
        hostname="hooks.example.com",
        port=443,
        resolved_addresses=("203.0.113.10",),
    )


def test_feishu_card_is_non_interactive_and_safely_cropped():
    payload, truncated = build_feishu_payload(
        _message(evidence=["证" * 800 for _ in range(20)], suggestion="建" * 2000),
        signing_secret="signing-secret",
        timestamp=123456,
    )
    assert payload["msg_type"] in {"interactive", "text"}
    assert "actions" not in str(payload)
    assert len(serialized_body(payload)) <= FEISHU_MAX_BODY_BYTES
    assert truncated is True
    assert payload["timestamp"] == "123456"
    assert payload["sign"]


def test_mention_all_only_appears_for_explicit_critical_message():
    critical, _ = build_feishu_payload(_message(mention_all=True))
    warning, _ = build_feishu_payload(_message(severity=IssueSeverity.warning))
    assert "<at id=all>" in str(critical)
    assert "<at id=all>" not in str(warning)


def test_feishu_notification_times_display_as_beijing_time():
    message = _message(now=datetime(2026, 8, 17, 7, 30, 45, tzinfo=timezone.utc))

    card_payload, _ = build_feishu_payload(message)
    text_payload, _ = build_feishu_payload(message, text_fallback=True)

    assert "2026-08-17 15:30:45 CST" in card_payload["card"]["elements"][0]["content"]
    assert "2026-08-17T07:30:45+00:00" not in card_payload["card"]["elements"][0]["content"]
    assert "时间：2026-08-17 15:30:45 CST" in text_payload["content"]["text"]


def test_delivery_revalidates_target_for_every_retry(client, monkeypatch):
    calls = {"validate": 0, "send": 0}

    def validate(*args, **kwargs):
        calls["validate"] += 1
        return _target()

    def sender(target, body, headers, timeout):
        calls["send"] += 1
        return SendResult(200 if calls["send"] == 3 else 503)

    monkeypatch.setattr(notification_delivery, "validate_outbound_target", validate)
    with client.app.state.session_factory() as session:
        cipher = SensitiveValueCipher.from_key(client.app.state.settings.encryption_key)
        channel = NotificationChannelModel(
            name="重试渠道",
            normalized_name="重试渠道",
            type="generic_webhook",
            enabled=True,
            encrypted_webhook_url=cipher.encrypt(
                "https://hooks.example.com/v1/notify",
                purpose="notification_webhook_url",
            ),
            endpoint_masked="https://hooks.example.com/***",
            mention_all_on_critical=False,
            timeout_seconds=1,
        )
        session.add(channel)
        session.commit()
        session.refresh(channel)
        delivery = notification_delivery.create_delivery(
            session,
            channel_id=channel.id,
            deduplication_key="retry-test",
            event_type=NotificationEventType.notification_test,
        )
        notification_delivery.deliver(
            session,
            row=channel,
            delivery=delivery,
            message=NotificationMessage(
                event_type=NotificationEventType.notification_test,
                cluster_id="cluster-a",
                summary="测试通知",
                last_seen_at=datetime.now(timezone.utc),
                detail_url="https://inspector.example.com/",
                is_test=True,
            ),
            settings=client.app.state.settings,
            target_policy=notification_service._target_policy(client.app.state.settings),
            sender=sender,
        )
        assert delivery.status == "succeeded"
        assert delivery.attempt_count == 3
    assert calls == {"validate": 3, "send": 3}


def test_transport_falls_back_to_next_validated_ip_without_hostname_resolution(monkeypatch):
    calls = []

    class Stream:
        def get_extra_info(self, key):
            return ("203.0.113.11", 443) if key == "server_addr" else None

    class Response:
        status_code = 200
        extensions = {"network_stream": Stream()}

    class Client:
        def __init__(self, **kwargs):
            assert kwargs["follow_redirects"] is False
            assert kwargs["trust_env"] is False

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, **kwargs):
            calls.append((url, kwargs))
            if "203.0.113.10" in url:
                raise httpx.ConnectError("unreachable", request=httpx.Request("POST", url))
            return Response()

    monkeypatch.setattr(notification_transport.httpx, "Client", Client)
    target = ValidatedOutboundTarget(
        original_url="https://hooks.example.com/v1/notify",
        hostname="hooks.example.com",
        port=443,
        resolved_addresses=("203.0.113.10", "203.0.113.11"),
    )
    result = notification_transport.http_send(
        target,
        b"{}",
        {"content-type": "application/json"},
        2,
    )
    assert result.succeeded
    assert len(calls) == 2
    assert all("hooks.example.com" not in url for url, _ in calls)
    assert calls[1][1]["headers"]["host"] == "hooks.example.com"
    assert calls[1][1]["extensions"]["sni_hostname"] == "hooks.example.com"


def test_channel_api_masks_secrets_and_test_does_not_create_issue(client, monkeypatch):
    monkeypatch.setattr(notification_service, "validate_outbound_target", lambda *args, **kwargs: _target())
    monkeypatch.setattr(notification_delivery, "validate_outbound_target", lambda *args, **kwargs: _target())
    monkeypatch.setattr(notification_delivery, "http_send", lambda *args, **kwargs: SendResult(200))
    created = client.post(
        "/api/v1/notification-channels",
        json={
            "name": "Webhook A",
            "type": "generic_webhook",
            "enabled": True,
            "webhook_url": "https://hooks.example.com/v1/very-secret-token",
            "signing_secret": "signing-secret",
            "mention_all_on_critical": False,
            "timeout_seconds": 2,
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert "very-secret-token" not in str(body)
    assert "signing-secret" not in str(body)
    assert "webhook_url" not in body
    assert body["signing_secret_configured"] is True

    tested = client.post(f"/api/v1/notification-channels/{body['id']}/test")
    assert tested.status_code == 200
    assert tested.json()["delivery"]["event_type"] == "notification_test"
    assert tested.json()["delivery"]["attempt_count"] == 1
    with client.app.state.session_factory() as session:
        assert session.query(IssueModel).count() == 0
        delivery = session.query(NotificationDeliveryModel).one()
        assert delivery.status == "succeeded"

    deleted = client.delete(f"/api/v1/notification-channels/{body['id']}")
    assert deleted.status_code == 204
    with client.app.state.session_factory() as session:
        channel = session.get(NotificationChannelModel, body["id"])
        assert channel.deleted_at is not None
        assert session.get(NotificationDeliveryModel, delivery.id) is not None


def test_notification_detail_url_uses_normalized_base_path() -> None:
    settings = notification_service.Settings(
        base_path="/inspector/",
        trusted_detail_base_url="https://inspector.example.com:31443",
    )

    assert (
        str(notification_service._detail_url(settings, "/issues/12"))
        == "https://inspector.example.com:31443/inspector/issues/12"
    )
    assert (
        str(notification_service._detail_url(settings, "issues/12"))
        == "https://inspector.example.com:31443/inspector/issues/12"
    )


def test_no_feishu_receive_or_callback_route_exists(client):
    paths = set(client.app.openapi()["paths"])
    assert not any("callback" in path or "events" in path and "issues" not in path for path in paths)
    assert not any("feishu" in path for path in paths)


def test_flapping_replaces_transition_and_cooldown_suppresses_followups(client, monkeypatch):
    monkeypatch.setattr(notification_delivery, "validate_outbound_target", lambda *args, **kwargs: _target())
    sender = lambda *args, **kwargs: SendResult(200)
    now = datetime.now(timezone.utc)
    with client.app.state.session_factory() as session:
        cipher = SensitiveValueCipher.from_key(client.app.state.settings.encryption_key)
        channel = NotificationChannelModel(
            name="抖动渠道",
            normalized_name="抖动渠道",
            type="generic_webhook",
            enabled=True,
            encrypted_webhook_url=cipher.encrypt(
                "https://hooks.example.com/v1/notify",
                purpose="notification_webhook_url",
            ),
            endpoint_masked="https://hooks.example.com/***",
            mention_all_on_critical=False,
            timeout_seconds=1,
        )
        plan = InspectionPlanModel(
            name="抖动计划",
            normalized_name="抖动计划",
            enabled=True,
            scope={"type": "namespaces", "namespaces": ["demo"]},
            schedule={"interval": "10m", "daily_at": None, "timezone": "UTC"},
            include_template_matching=True,
        )
        issue = IssueModel(
            cluster_id="cluster-a",
            issue_code="POD_NOT_READY",
            fingerprint="b" * 64,
            severity="warning",
            status="recovered",
            scope="pod",
            resource_kind="Pod",
            resource_namespace="demo",
            resource_name="api-0",
            summary="Pod 未就绪",
            reason="Ready=False",
            suggestion="检查容器状态",
            evidence=[],
            first_seen_at=now,
            last_seen_at=now,
            recovered_at=now,
            occurrence_count=3,
            source_check="pod.runtime",
        )
        session.add_all([channel, plan, issue])
        session.commit()
        session.execute(
            inspection_plan_channels.insert().values(plan_id=plan.id, channel_id=channel.id)
        )
        events = []
        for index, event_type in enumerate(
            ["opened", "recovered", "reopened", "recovered", "reopened", "recovered"]
        ):
            event = IssueEventModel(
                issue_id=issue.id,
                event_type=event_type,
                trigger="scheduled",
                occurred_at=now.replace(microsecond=index),
                summary=event_type,
                evidence_codes=[],
            )
            session.add(event)
            events.append(event)
        session.commit()
        current = events[-1]
        notification_service.dispatch_lifecycle_changes(
            session,
            plan_id=plan.id,
            changes=[LifecycleChange(issue, current)],
            settings=client.app.state.settings,
            sender=sender,
        )
        first = session.query(NotificationDeliveryModel).all()
        assert [item.event_type for item in first] == ["flapping"]
        assert first[0].status == "succeeded"

        reopened = IssueEventModel(
            issue_id=issue.id,
            event_type="reopened",
            trigger="scheduled",
            occurred_at=datetime.now(timezone.utc),
            summary="reopened",
            evidence_codes=[],
        )
        issue.status = "open"
        issue.recovered_at = None
        session.add(reopened)
        session.commit()
        notification_service.dispatch_lifecycle_changes(
            session,
            plan_id=plan.id,
            changes=[LifecycleChange(issue, reopened)],
            settings=client.app.state.settings,
            sender=sender,
        )
        suppressed = session.query(NotificationDeliveryModel).order_by(NotificationDeliveryModel.id).all()
        assert suppressed[-1].event_type == "issue_opened"
        assert suppressed[-1].status == "suppressed"

        escalated = IssueEventModel(
            issue_id=issue.id,
            event_type="severity_escalated",
            trigger="scheduled",
            occurred_at=datetime.now(timezone.utc),
            summary="severity escalated",
            evidence_codes=[],
        )
        issue.severity = "critical"
        session.add(escalated)
        session.commit()
        notification_service.dispatch_lifecycle_changes(
            session,
            plan_id=plan.id,
            changes=[LifecycleChange(issue, escalated)],
            settings=client.app.state.settings,
            sender=sender,
        )
        latest = session.query(NotificationDeliveryModel).order_by(NotificationDeliveryModel.id.desc()).first()
        assert latest.event_type == "severity_escalated"
        assert latest.status == "succeeded"

        old = datetime.now(timezone.utc) - timedelta(minutes=31)
        for item in session.query(IssueEventModel).filter(IssueEventModel.issue_id == issue.id):
            item.occurred_at = old
        first[0].created_at = old
        recovered_after_cooldown = IssueEventModel(
            issue_id=issue.id,
            event_type="recovered",
            trigger="scheduled",
            occurred_at=datetime.now(timezone.utc),
            summary="recovered after cooldown",
            evidence_codes=[],
        )
        issue.status = "recovered"
        issue.recovered_at = datetime.now(timezone.utc)
        session.add(recovered_after_cooldown)
        session.commit()
        notification_service.dispatch_lifecycle_changes(
            session,
            plan_id=plan.id,
            changes=[LifecycleChange(issue, recovered_after_cooldown)],
            settings=client.app.state.settings,
            sender=sender,
        )
        resumed = session.query(NotificationDeliveryModel).order_by(NotificationDeliveryModel.id.desc()).first()
        assert resumed.event_type == "issue_recovered"
        assert resumed.status == "succeeded"


def test_info_open_and_recovered_are_silent_but_escalation_is_not(client, monkeypatch):
    monkeypatch.setattr(notification_delivery, "validate_outbound_target", lambda *args, **kwargs: _target())
    sender = lambda *args, **kwargs: SendResult(200)
    now = datetime.now(timezone.utc)
    with client.app.state.session_factory() as session:
        cipher = SensitiveValueCipher.from_key(client.app.state.settings.encryption_key)
        channel = NotificationChannelModel(
            name="Info渠道",
            normalized_name="info渠道",
            type="generic_webhook",
            enabled=True,
            encrypted_webhook_url=cipher.encrypt(
                "https://hooks.example.com/v1/notify",
                purpose="notification_webhook_url",
            ),
            endpoint_masked="https://hooks.example.com/***",
            mention_all_on_critical=False,
            timeout_seconds=1,
        )
        plan = InspectionPlanModel(
            name="Info计划",
            normalized_name="info计划",
            enabled=True,
            scope={"type": "namespaces", "namespaces": ["demo"]},
            schedule={"interval": "10m", "daily_at": None, "timezone": "UTC"},
            include_template_matching=True,
        )
        issue = IssueModel(
            cluster_id="cluster-a",
            issue_code="JOB_FAILED",
            fingerprint="c" * 64,
            severity="info",
            status="open",
            scope="workload",
            resource_kind="Job",
            resource_namespace="demo",
            resource_name="job-a",
            summary="Job 长时间未完成",
            reason="超过提示阈值",
            suggestion="检查业务预期",
            evidence=[],
            first_seen_at=now,
            last_seen_at=now,
            occurrence_count=1,
            source_check="workload.status",
        )
        session.add_all([channel, plan, issue])
        session.commit()
        session.execute(
            inspection_plan_channels.insert().values(plan_id=plan.id, channel_id=channel.id)
        )
        opened = IssueEventModel(
            issue_id=issue.id,
            event_type="opened",
            trigger="scheduled",
            occurred_at=now,
            summary="opened",
            evidence_codes=[],
        )
        session.add(opened)
        session.commit()
        notification_service.dispatch_lifecycle_changes(
            session,
            plan_id=plan.id,
            changes=[LifecycleChange(issue, opened)],
            settings=client.app.state.settings,
            sender=sender,
        )
        recovered = IssueEventModel(
            issue_id=issue.id,
            event_type="recovered",
            trigger="scheduled",
            occurred_at=now,
            summary="recovered",
            evidence_codes=[],
        )
        issue.status = "recovered"
        issue.recovered_at = now
        session.add(recovered)
        session.commit()
        notification_service.dispatch_lifecycle_changes(
            session,
            plan_id=plan.id,
            changes=[LifecycleChange(issue, recovered)],
            settings=client.app.state.settings,
            sender=sender,
        )
        assert session.query(NotificationDeliveryModel).count() == 0

        escalated = IssueEventModel(
            issue_id=issue.id,
            event_type="severity_escalated",
            trigger="scheduled",
            occurred_at=now,
            summary="severity escalated",
            evidence_codes=[],
        )
        issue.status = "open"
        issue.recovered_at = None
        issue.severity = "warning"
        session.add(escalated)
        session.commit()
        notification_service.dispatch_lifecycle_changes(
            session,
            plan_id=plan.id,
            changes=[LifecycleChange(issue, escalated)],
            settings=client.app.state.settings,
            sender=sender,
        )
        deliveries = session.query(NotificationDeliveryModel).all()
        assert len(deliveries) == 1
        assert deliveries[0].event_type == "severity_escalated"
        assert deliveries[0].status == "succeeded"


def test_maintenance_silence_window_crud_api(client):
    start = datetime.now(timezone.utc).replace(microsecond=0)
    end = start + timedelta(hours=2)
    created = client.post(
        "/api/v1/maintenance-silence-windows",
        json={
            "name": "数据库维护",
            "enabled": True,
            "start_at": start.isoformat(),
            "end_at": end.isoformat(),
            "scope": {"type": "namespace", "namespace": "payments"},
            "note": "发布期间减少重复告警",
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["name"] == "数据库维护"
    assert body["scope"] == {"type": "namespace", "namespace": "payments", "resource_kind": None, "label_selector": None}

    listed = client.get("/api/v1/maintenance-silence-windows")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    updated = client.put(
        f"/api/v1/maintenance-silence-windows/{body['id']}",
        json={
            "enabled": False,
            "scope": {"type": "resource_kind", "resource_kind": "Deployment"},
        },
    )
    assert updated.status_code == 200
    assert updated.json()["enabled"] is False
    assert updated.json()["scope"]["resource_kind"] == "Deployment"

    deleted = client.delete(f"/api/v1/maintenance-silence-windows/{body['id']}")
    assert deleted.status_code == 204
    assert client.get("/api/v1/maintenance-silence-windows").json()["total"] == 0


def test_maintenance_silence_suppresses_notifications_and_records_issue_event(client, monkeypatch):
    monkeypatch.setattr(notification_delivery, "validate_outbound_target", lambda *args, **kwargs: _target())
    sender_calls = {"count": 0}

    def sender(*args, **kwargs):
        sender_calls["count"] += 1
        return SendResult(200)

    now = datetime.now(timezone.utc)
    with client.app.state.session_factory() as session:
        cipher = SensitiveValueCipher.from_key(client.app.state.settings.encryption_key)
        channel = NotificationChannelModel(
            name="静默渠道",
            normalized_name="静默渠道",
            type="generic_webhook",
            enabled=True,
            encrypted_webhook_url=cipher.encrypt(
                "https://hooks.example.com/v1/notify",
                purpose="notification_webhook_url",
            ),
            endpoint_masked="https://hooks.example.com/***",
            mention_all_on_critical=False,
            timeout_seconds=1,
        )
        plan = InspectionPlanModel(
            name="静默计划",
            normalized_name="静默计划",
            enabled=True,
            scope={"type": "namespaces", "namespaces": ["demo"]},
            schedule={"interval": "10m", "daily_at": None, "timezone": "UTC"},
            include_template_matching=True,
        )
        issue = IssueModel(
            cluster_id="cluster-a",
            issue_code="POD_NOT_READY",
            fingerprint="d" * 64,
            severity="warning",
            status="open",
            scope="pod",
            resource_kind="Pod",
            resource_namespace="demo",
            resource_name="api-0",
            summary="Pod 未就绪",
            reason="Ready=False",
            suggestion="检查容器状态",
            evidence=[{"facts": {"labels": {"app": "api"}}, "summary": "labels", "source": "kubernetes_api"}],
            first_seen_at=now,
            last_seen_at=now,
            occurrence_count=1,
            source_check="pod.runtime",
        )
        window = MaintenanceSilenceWindowModel(
            name="demo 维护",
            enabled=True,
            start_at=now - timedelta(minutes=5),
            end_at=now + timedelta(minutes=30),
            scope_type="namespace",
            namespace="demo",
            note="变更窗口",
        )
        session.add_all([channel, plan, issue, window])
        session.commit()
        session.execute(
            inspection_plan_channels.insert().values(plan_id=plan.id, channel_id=channel.id)
        )
        opened = IssueEventModel(
            issue_id=issue.id,
            event_type="opened",
            trigger="scheduled",
            occurred_at=now,
            summary="opened",
            evidence_codes=[],
        )
        session.add(opened)
        session.commit()

        notification_service.dispatch_lifecycle_changes(
            session,
            plan_id=plan.id,
            changes=[LifecycleChange(issue, opened)],
            settings=client.app.state.settings,
            sender=sender,
        )

        delivery = session.query(NotificationDeliveryModel).one()
        assert delivery.status == "suppressed"
        assert delivery.error_code == "MAINTENANCE_SILENCE"
        assert sender_calls["count"] == 0
        silence_event = (
            session.query(IssueEventModel)
            .filter(IssueEventModel.event_type == "notification_silenced")
            .one()
        )
        assert "通知已静默" in silence_event.summary
        assert session.get(MaintenanceSilenceWindowModel, window.id).pending_summary_recorded_at is not None

        escalated = IssueEventModel(
            issue_id=issue.id,
            event_type="severity_escalated",
            trigger="scheduled",
            occurred_at=now,
            summary="severity escalated",
            evidence_codes=[],
        )
        issue.severity = "critical"
        session.add(escalated)
        session.commit()
        notification_service.dispatch_lifecycle_changes(
            session,
            plan_id=plan.id,
            changes=[LifecycleChange(issue, escalated)],
            settings=client.app.state.settings,
            sender=sender,
        )
        latest = session.query(NotificationDeliveryModel).order_by(NotificationDeliveryModel.id.desc()).first()
        assert latest.event_type == "severity_escalated"
        assert latest.status == "suppressed"
        assert sender_calls["count"] == 0

        client.app.state.settings.notification_escalation_breaks_silence = True
        escalated_again = IssueEventModel(
            issue_id=issue.id,
            event_type="severity_escalated",
            trigger="scheduled",
            occurred_at=now,
            summary="severity escalated again",
            evidence_codes=[],
        )
        session.add(escalated_again)
        session.commit()
        notification_service.dispatch_lifecycle_changes(
            session,
            plan_id=plan.id,
            changes=[LifecycleChange(issue, escalated_again)],
            settings=client.app.state.settings,
            sender=sender,
        )
        delivered = session.query(NotificationDeliveryModel).order_by(NotificationDeliveryModel.id.desc()).first()
        assert delivered.event_type == "severity_escalated"
        assert delivered.status == "succeeded"
        assert sender_calls["count"] == 1


def test_expired_maintenance_silence_sends_one_open_issue_summary(client, monkeypatch):
    monkeypatch.setattr(notification_delivery, "validate_outbound_target", lambda *args, **kwargs: _target())
    sender_calls = {"count": 0}

    def sender(*args, **kwargs):
        sender_calls["count"] += 1
        return SendResult(200)

    now = datetime.now(timezone.utc)
    with client.app.state.session_factory() as session:
        cipher = SensitiveValueCipher.from_key(client.app.state.settings.encryption_key)
        channel = NotificationChannelModel(
            name="摘要渠道",
            normalized_name="摘要渠道",
            type="generic_webhook",
            enabled=True,
            encrypted_webhook_url=cipher.encrypt(
                "https://hooks.example.com/v1/summary",
                purpose="notification_webhook_url",
            ),
            endpoint_masked="https://hooks.example.com/***",
            mention_all_on_critical=False,
            timeout_seconds=1,
        )
        open_issue = IssueModel(
            cluster_id="cluster-a",
            issue_code="POD_NOT_READY",
            fingerprint="e" * 64,
            severity="warning",
            status="open",
            scope="pod",
            resource_kind="Pod",
            resource_namespace="demo",
            resource_name="api-0",
            summary="Pod 未就绪",
            reason="Ready=False",
            suggestion="检查容器状态",
            evidence=[],
            first_seen_at=now - timedelta(hours=1),
            last_seen_at=now,
            occurrence_count=1,
            source_check="pod.runtime",
        )
        recovered_issue = IssueModel(
            cluster_id="cluster-a",
            issue_code="POD_NOT_READY",
            fingerprint="f" * 64,
            severity="warning",
            status="recovered",
            scope="pod",
            resource_kind="Pod",
            resource_namespace="demo",
            resource_name="api-1",
            summary="已恢复 Pod",
            reason="Ready=True",
            suggestion="无需处理",
            evidence=[],
            first_seen_at=now - timedelta(hours=1),
            last_seen_at=now,
            recovered_at=now,
            occurrence_count=1,
            source_check="pod.runtime",
        )
        window = MaintenanceSilenceWindowModel(
            name="demo 维护结束",
            enabled=True,
            start_at=now - timedelta(hours=2),
            end_at=now - timedelta(minutes=1),
            scope_type="namespace",
            namespace="demo",
            note="发布完成",
            pending_summary_recorded_at=now - timedelta(minutes=30),
        )
        session.add_all([channel, open_issue, recovered_issue, window])
        session.commit()

        notification_service.dispatch_due_maintenance_silence_summaries(
            session,
            settings=client.app.state.settings,
            sender=sender,
        )

        delivery = session.query(NotificationDeliveryModel).one()
        assert delivery.event_type == "maintenance_summary"
        assert delivery.status == "succeeded"
        assert sender_calls["count"] == 1
        assert session.get(MaintenanceSilenceWindowModel, window.id).pending_summary_recorded_at is None

        notification_service.dispatch_due_maintenance_silence_summaries(
            session,
            settings=client.app.state.settings,
            sender=sender,
        )
        assert session.query(NotificationDeliveryModel).count() == 1
        assert sender_calls["count"] == 1
