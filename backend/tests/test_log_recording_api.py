from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.models import LogRecording, LogRecordingLine, LogRecordingPod
from app.providers.base import LogRecordingEntry, LogRecordingPodSnapshot, LogRecordingSnapshot
from app.schemas.log_recording import LogRecordingCreate, LogRecordingDurationSource
from app.services import log_recording_engine


def _create_recording(client, name: str = "复现支付失败") -> dict:
    response = client.post(
        "/api/v1/log-recordings",
        json={
            "name": name,
            "namespace": "demo",
            "duration_source": "preset",
            "duration_minutes": 10,
            "note": "点击下单后 500",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_preview_log_recording_allows_small_namespace(client) -> None:
    response = client.post("/api/v1/log-recordings/preview", json={"namespace": "demo"})

    assert response.status_code == 200
    assert response.json()["namespace"] == "demo"
    assert response.json()["pod_count"] == 1
    assert response.json()["allowed"] is True


def test_log_recording_crud_and_stop_flow(client) -> None:
    created = _create_recording(client)
    scheduler = client.app.state.log_recording_scheduler
    assert scheduler.get_job(f"v1.3:log-recording:auto-stop:{created['id']}") is not None
    assert scheduler.get_job(f"v1.3:log-recording:collect:{created['id']}") is not None

    assert created["name"] == "复现支付失败"
    assert created["namespace"] == "demo"
    assert created["status"] == "recording"
    assert created["duration_source"] == "preset"
    assert created["duration_minutes"] == 10
    assert created["stop_reason"] is None
    assert created["pod_count"] == 1
    assert created["created_by"] == "development"

    list_response = client.get("/api/v1/log-recordings", params={"namespace": "demo"})
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1
    assert list_response.json()["items"][0]["id"] == created["id"]

    detail_response = client.get(f"/api/v1/log-recordings/{created['id']}")
    assert detail_response.status_code == 200
    assert detail_response.json()["name"] == "复现支付失败"

    patch_response = client.patch(
        f"/api/v1/log-recordings/{created['id']}",
        json={"name": "复现支付失败-已确认", "note": "接口返回 500"},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["name"] == "复现支付失败-已确认"
    assert patch_response.json()["note"] == "接口返回 500"

    stop_response = client.post(f"/api/v1/log-recordings/{created['id']}/stop")
    assert stop_response.status_code == 200
    assert stop_response.json()["status"] == "completed"
    assert stop_response.json()["stop_reason"] == "user_stopped"
    assert stop_response.json()["ended_at"] is not None
    assert scheduler.get_job(f"v1.3:log-recording:auto-stop:{created['id']}") is None
    assert scheduler.get_job(f"v1.3:log-recording:collect:{created['id']}") is None

    second_stop = client.post(f"/api/v1/log-recordings/{created['id']}/stop")
    assert second_stop.status_code == 409

    delete_response = client.delete(f"/api/v1/log-recordings/{created['id']}")
    assert delete_response.status_code == 204
    assert client.get(f"/api/v1/log-recordings/{created['id']}").status_code == 404


def test_log_recording_create_and_collects_multi_namespace_task(client) -> None:
    class MultiNamespaceProvider:
        def __init__(self) -> None:
            self.collected: list[str] = []

        def list_namespace_pods(self, namespace: str, label_selector: str | None = None) -> dict:
            return {
                "namespace": namespace,
                "label_selector": label_selector,
                "executed_at": datetime.now(timezone.utc).isoformat(),
                "pods": [{"name": f"{namespace}-api-0", "labels": {"app": "api"}, "containers": ["api"]}],
            }

        def collect_log_recording_snapshot(
            self,
            namespace: str,
            *,
            since_time: datetime,
            max_pods: int,
            max_total_bytes: int,
            max_pod_bytes: int,
        ) -> LogRecordingSnapshot:
            self.collected.append(namespace)
            collected_at = datetime.now(timezone.utc)
            return LogRecordingSnapshot(
                namespace=namespace,
                collected_at=collected_at,
                pods=[
                    LogRecordingPodSnapshot(
                        namespace=namespace,
                        pod_uid=f"{namespace}-uid",
                        pod_name=f"{namespace}-api-0",
                        container_names=["api"],
                        entries=[
                            LogRecordingEntry(
                                pod_uid=f"{namespace}-uid",
                                pod_name=f"{namespace}-api-0",
                                container_name="api",
                                log_time=collected_at,
                                text=f"{namespace} error",
                                collected_at=collected_at,
                            )
                        ],
                    )
                ],
                total_bytes=100,
                truncated=False,
            )

    provider = MultiNamespaceProvider()
    with client.app.state.session_factory() as session:
        recording = log_recording_engine.log_recording_service.create_recording(
            session,
            provider,
            LogRecordingCreate(
                name="多名称空间复现",
                namespaces=["demo", "prod"],
                duration_source=LogRecordingDurationSource.preset,
                duration_minutes=10,
            ),
            created_by="test",
        )
        assert recording.namespace == "demo"
        result = log_recording_engine.log_recording_service.collect_recording_once(session, provider, recording.id)

    assert result.namespaces == ["demo", "prod"]
    assert provider.collected == ["demo", "prod"]
    pods_response = client.get(f"/api/v1/log-recordings/{recording.id}/pods")
    assert pods_response.status_code == 200
    assert {item["namespace"] for item in pods_response.json()} == {"demo", "prod"}


def test_log_recording_auto_stop_due_recordings(client) -> None:
    created = _create_recording(client)

    with client.app.state.session_factory() as session:
        stored = session.get(log_recording_engine.LogRecording, created["id"])
        stored.planned_end_at = datetime.now(timezone.utc)
        session.commit()

    assert log_recording_engine.auto_stop_due_recordings(client.app) == 1

    response = client.get(f"/api/v1/log-recordings/{created['id']}")
    assert response.status_code == 200
    assert response.json()["status"] == "auto_completed"
    assert response.json()["stop_reason"] == "selected_duration_timeout"


def test_log_recording_restart_marks_incomplete_recording_failed(test_settings: Settings) -> None:
    app = create_app(test_settings)
    with TestClient(app) as first_client:
        created = _create_recording(first_client)
        assert first_client.get(f"/api/v1/log-recordings/{created['id']}").json()["status"] == "recording"

    restarted = create_app(test_settings)
    with TestClient(restarted) as second_client:
        response = second_client.get(f"/api/v1/log-recordings/{created['id']}")

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["stop_reason"] == "recovery_failed_after_restart"
    assert response.json()["ended_at"] is not None


def test_log_recording_storage_usage_and_pagination(client) -> None:
    first = _create_recording(client, "first")
    second = _create_recording(client, "second")

    response = client.get("/api/v1/log-recordings", params={"page": 1, "page_size": 1})

    assert response.status_code == 200
    assert response.json()["total"] == 2
    assert response.json()["page"] == 1
    assert response.json()["page_size"] == 1
    assert response.json()["items"][0]["id"] == second["id"]

    storage = client.get("/api/v1/log-recordings/storage")
    assert storage.status_code == 200
    assert storage.json()["used_bytes"] >= 0
    assert storage.json()["max_bytes"] == 10 * 1024 * 1024 * 1024
    assert storage.json()["warning"] is False
    assert first["id"] < second["id"]


def test_log_recording_rejects_duration_over_configured_max(client) -> None:
    settings_response = client.get("/api/v1/settings")
    policy = settings_response.json()["inspection_policy"]
    policy["reproduction_logs"]["default_duration_minutes"] = 5
    policy["reproduction_logs"]["max_duration_minutes"] = 5
    update_response = client.put(
        "/api/v1/settings",
        json={
            "base_path": "",
            "provider_mode": "mock",
            "kubeconfig_path": None,
            "kube_context": None,
            "llm_enabled": False,
            "llm_provider": "qwen",
            "model_endpoint": None,
            "api_key": None,
            "default_inspection_strategy": {},
            "inspection_policy": policy,
        },
    )
    assert update_response.status_code == 200

    response = client.post(
        "/api/v1/log-recordings",
        json={
            "name": "超时长记录",
            "namespace": "demo",
            "duration_source": "preset",
            "duration_minutes": 10,
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "REQUEST_VALIDATION_FAILED"
    assert "超过上限" in response.json()["details"]["reason"]
    list_response = client.get("/api/v1/log-recordings")
    assert list_response.json()["total"] == 0


def test_log_recording_pods_and_logs_read_existing_rows(client) -> None:
    created = _create_recording(client)
    now = datetime.now(timezone.utc)

    with client.app.state.session_factory() as session:
        pod = LogRecordingPod(
            recording_id=created["id"],
            namespace="demo",
            pod_uid="pod-uid-1",
            pod_name="demo-api-1",
            node_name="node-a",
            owner_kind="Deployment",
            owner_name="demo-api",
            container_count=1,
            raw_line_count=2,
            folded_line_count=1,
            keyword_hit_count=1,
            deleted_during_recording=False,
            truncated=False,
            collection_error=None,
        )
        line = LogRecordingLine(
            recording_id=created["id"],
            pod_uid="pod-uid-1",
            pod_name="demo-api-1",
            container_name="demo-api",
            log_time=now,
            collected_at=now,
            line_text="Authorization: Bearer *** error",
            normalized_fingerprint="a" * 64,
            repeat_count=2,
            first_seen_at=now,
            last_seen_at=now,
            redacted=True,
            folded=True,
            byte_size=31,
        )
        session.add_all([pod, line])
        session.commit()

    pods_response = client.get(f"/api/v1/log-recordings/{created['id']}/pods")
    assert pods_response.status_code == 200
    assert pods_response.json()[0]["pod_name"] == "demo-api-1"
    assert pods_response.json()[0]["keyword_hit_count"] == 1

    logs_response = client.get(
        f"/api/v1/log-recordings/{created['id']}/pods/demo-api-1/containers/demo-api/logs",
        params={"view": "folded"},
    )
    assert logs_response.status_code == 200
    assert logs_response.json()["total"] == 1
    assert logs_response.json()["redacted"] is True
    assert logs_response.json()["items"][0]["repeat_count"] == 2
    assert "Bearer ***" in logs_response.json()["items"][0]["line_text"]


def test_log_recording_not_found_routes_return_404(client) -> None:
    assert client.get("/api/v1/log-recordings/999").status_code == 404
    assert client.patch("/api/v1/log-recordings/999", json={"name": "missing"}).status_code == 404
    assert client.post("/api/v1/log-recordings/999/stop").status_code == 404
    assert client.delete("/api/v1/log-recordings/999").status_code == 404
    assert client.get("/api/v1/log-recordings/999/pods").status_code == 404
    assert (
        client.get("/api/v1/log-recordings/999/pods/demo/containers/api/logs").status_code
        == 404
    )
    assert client.post("/api/v1/log-recordings/999/template-match").status_code == 404


def test_log_recording_template_match_executes_only_log_templates(client) -> None:
    created = _create_recording(client)
    with client.app.state.session_factory() as session:
        log_recording_engine.log_recording_service.collect_recording_once(
            session,
            client.app.state.provider,
            created["id"],
        )

    log_template = client.post(
        "/api/v1/templates",
        json={
            "name": "数据库连接失败",
            "scenario": "targeted_diagnosis",
            "targets": [
                {
                    "target_ref": "api",
                    "namespace": "demo",
                    "resource_scope": ["pods"],
                }
            ],
            "match_conditions": [
                {
                    "target_ref": "api",
                    "condition_type": "log_keyword",
                    "operator": "contains",
                    "expected_value": "connection refused",
                }
            ],
            "joint_rule": {"operator": "AND"},
            "reason": "数据库连接失败",
            "suggestion": "检查数据库服务和网络策略",
            "enabled": True,
        },
    )
    status_template = client.post(
        "/api/v1/templates",
        json={
            "name": "纯状态模板",
            "scenario": "targeted_diagnosis",
            "targets": [
                {
                    "target_ref": "api",
                    "namespace": "demo",
                    "resource_scope": ["pods"],
                }
            ],
            "match_conditions": [
                {
                    "target_ref": "api",
                    "condition_type": "pod_status",
                    "operator": "in",
                    "expected_value": ["CrashLoopBackOff"],
                }
            ],
            "joint_rule": {"operator": "AND"},
            "reason": "Pod 状态异常",
            "suggestion": "检查 Pod 状态",
            "enabled": True,
        },
    )
    assert log_template.status_code == 201
    assert status_template.status_code == 201

    response = client.post(f"/api/v1/log-recordings/{created['id']}/template-match")

    assert response.status_code == 200
    assert len(response.json()) == 1
    item = response.json()[0]
    assert item["template_id"] == log_template.json()["id"]
    assert item["template_name"] == "数据库连接失败"
    assert item["pod_name"] == "demo-api-7c8f6f7c6b-fh2ns"
    assert item["container_name"] == "demo-api"
    assert item["keyword"] == "connection refused"
    assert "connection refused" in item["matched_context"]
    assert item["suggestion"] == "检查数据库服务和网络策略"

    second = client.post(f"/api/v1/log-recordings/{created['id']}/template-match")
    assert second.status_code == 200
    assert len(second.json()) == 1


def test_log_recording_collects_mock_provider_snapshot(client) -> None:
    created = _create_recording(client)

    with client.app.state.session_factory() as session:
        result = log_recording_engine.log_recording_service.collect_recording_once(
            session,
            client.app.state.provider,
            created["id"],
        )

    assert result.raw_line_count >= 1
    pods_response = client.get(f"/api/v1/log-recordings/{created['id']}/pods")
    assert pods_response.status_code == 200
    assert pods_response.json()[0]["pod_name"] == "demo-api-7c8f6f7c6b-fh2ns"
    assert pods_response.json()[0]["container_count"] == 1

    logs_response = client.get(
        f"/api/v1/log-recordings/{created['id']}/pods/demo-api-7c8f6f7c6b-fh2ns/containers/demo-api/logs"
    )
    assert logs_response.status_code == 200
    assert logs_response.json()["total"] >= 1


def test_log_recording_marks_missing_pod_deleted_after_refresh(client) -> None:
    created = _create_recording(client)
    now = datetime.now(timezone.utc)
    with client.app.state.session_factory() as session:
        session.add(
            LogRecordingPod(
                recording_id=created["id"],
                namespace="demo",
                pod_uid="old-pod",
                pod_name="old-api",
                container_count=1,
                raw_line_count=0,
                folded_line_count=0,
                keyword_hit_count=0,
                deleted_during_recording=False,
                truncated=False,
                collection_error=None,
            )
        )
        stored = session.get(LogRecording, created["id"])
        stored.started_at = now
        session.commit()
        log_recording_engine.log_recording_service.collect_recording_once(
            session,
            client.app.state.provider,
            created["id"],
        )

    pods_response = client.get(f"/api/v1/log-recordings/{created['id']}/pods")
    old_pod = next(item for item in pods_response.json() if item["pod_name"] == "old-api")
    assert old_pod["deleted_during_recording"] is True


def test_log_recording_redacts_and_folds_continuous_duplicate_logs(client) -> None:
    collected_at = datetime.now(timezone.utc)

    class DuplicateLogProvider:
        def list_namespace_pods(self, namespace: str, label_selector: str | None = None) -> dict:
            return {
                "namespace": namespace,
                "label_selector": label_selector,
                "executed_at": collected_at.isoformat(),
                "pods": [{"name": "demo-api-0", "labels": {"app": "demo"}}],
            }

        def collect_log_recording_snapshot(
            self,
            namespace: str,
            *,
            since_time: datetime,
            max_pods: int,
            max_total_bytes: int,
            max_pod_bytes: int,
        ) -> LogRecordingSnapshot:
            entries = [
                LogRecordingEntry(
                    pod_uid="pod-uid",
                    pod_name="demo-api-0",
                    container_name="api",
                    log_time=datetime(2026, 8, 9, 10, 0, index, tzinfo=timezone.utc),
                    text=(
                        f"2026-08-09T10:00:0{index}Z failed request_id=req-{index} "
                        f"attempt={index} password=secret-{index} Authorization: Bearer token-{index}"
                    ),
                    collected_at=collected_at,
                )
                for index in (1, 2, 3)
            ]
            return LogRecordingSnapshot(
                namespace=namespace,
                collected_at=collected_at,
                pods=[
                    LogRecordingPodSnapshot(
                        namespace=namespace,
                        pod_uid="pod-uid",
                        pod_name="demo-api-0",
                        container_names=["api"],
                        entries=entries,
                    )
                ],
                total_bytes=1000,
                truncated=False,
            )

    provider = DuplicateLogProvider()
    with client.app.state.session_factory() as session:
        recording = log_recording_engine.log_recording_service.create_recording(
            session,
            provider,
            LogRecordingCreate(
                name="重复日志",
                namespace="demo",
                duration_source=LogRecordingDurationSource.preset,
                duration_minutes=10,
            ),
            created_by="test",
        )
        result = log_recording_engine.log_recording_service.collect_recording_once(
            session,
            provider,
            recording.id,
        )
        second_result = log_recording_engine.log_recording_service.collect_recording_once(
            session,
            provider,
            recording.id,
        )
        recording_id = recording.id

    assert result.raw_line_count == 3
    assert result.folded_line_count == 1
    assert second_result.raw_line_count == 6
    assert second_result.folded_line_count == 1
    folded_response = client.get(
        f"/api/v1/log-recordings/{recording_id}/pods/demo-api-0/containers/api/logs",
        params={"view": "folded"},
    )
    assert folded_response.status_code == 200
    assert folded_response.json()["total"] == 1
    folded = folded_response.json()["items"][0]
    assert folded["repeat_count"] == 6
    assert folded["redacted"] is True
    assert "password=***" in folded["line_text"]
    assert "Authorization: Bearer ***" in folded["line_text"]
    assert "token-1" not in folded["line_text"]
    assert "secret-1" not in folded["line_text"]

    raw_response = client.get(
        f"/api/v1/log-recordings/{recording_id}/pods/demo-api-0/containers/api/logs",
        params={"view": "raw"},
    )
    assert raw_response.status_code == 200
    assert raw_response.json()["total"] == 6
    fingerprints = {item["normalized_fingerprint"] for item in raw_response.json()["items"]}
    assert len(fingerprints) == 1


def test_log_recording_stops_with_capacity_reason_when_record_limit_reached(client) -> None:
    class EmptyProvider:
        def list_namespace_pods(self, namespace: str, label_selector: str | None = None) -> dict:
            return {
                "namespace": namespace,
                "label_selector": label_selector,
                "executed_at": datetime.now(timezone.utc).isoformat(),
                "pods": [{"name": "demo-api-0", "labels": {"app": "demo"}}],
            }

        def collect_log_recording_snapshot(
            self,
            namespace: str,
            *,
            since_time: datetime,
            max_pods: int,
            max_total_bytes: int,
            max_pod_bytes: int,
        ) -> LogRecordingSnapshot:
            raise AssertionError("容量已满时不应继续采集日志")

    provider = EmptyProvider()
    with client.app.state.session_factory() as session:
        recording = log_recording_engine.log_recording_service.create_recording(
            session,
            provider,
            LogRecordingCreate(
                name="容量上限",
                namespace="demo",
                duration_source=LogRecordingDurationSource.preset,
                duration_minutes=10,
            ),
            created_by="test",
        )
        stored = session.get(LogRecording, recording.id)
        stored.total_bytes = 200 * 1024 * 1024
        session.commit()
        result = log_recording_engine.log_recording_service.collect_recording_once(
            session,
            provider,
            recording.id,
        )

    assert result.status == "auto_completed"
    assert result.stop_reason == "max_recording_bytes_reached"
    assert result.truncated is True
