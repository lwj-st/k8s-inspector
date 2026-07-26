from datetime import datetime, timedelta, timezone
import time

from fastapi.testclient import TestClient
from app.models import InspectionRun as InspectionRunModel, InspectionRecord
from app.main import create_app
from app.schemas.v1_1 import PlanSchedule
from app.services.inspection_plan_service import next_run_at


def _plan_payload(name: str = "生产巡检") -> dict:
    return {
        "name": name,
        "enabled": True,
        "scope": {"type": "namespaces", "namespaces": ["demo", "prod"]},
        "schedule": {"interval": "10m", "timezone": "Asia/Shanghai"},
        "include_template_matching": True,
        "notification_channel_ids": [],
    }


def test_plan_crud_and_manual_run(client):
    created = client.post("/api/v1/inspection-plans", json=_plan_payload())
    assert created.status_code == 201
    plan = created.json()
    assert plan["notification_channel_ids"] == []
    assert plan["next_run_at"]

    listed = client.get("/api/v1/inspection-plans")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    updated = client.put(
        f"/api/v1/inspection-plans/{plan['id']}",
        json={"schedule": {"interval": "daily", "daily_at": "09:30", "timezone": "Asia/Shanghai"}},
    )
    assert updated.status_code == 200
    assert updated.json()["schedule"]["daily_at"] == "09:30"

    executed = client.post(f"/api/v1/inspection-plans/{plan['id']}/run")
    assert executed.status_code == 202
    body = executed.json()
    assert body["trigger"] == "scheduled"
    assert body["status"] == "queued"
    assert body["started_at"] is None
    deadline = time.monotonic() + 2
    detail_body = body
    while time.monotonic() < deadline:
        detail_body = client.get(f"/api/v1/inspection-runs/{body['id']}").json()
        if detail_body["status"] not in {"queued", "running"}:
            break
        time.sleep(0.01)
    assert detail_body["status"] in {"succeeded", "partial"}
    assert len({item["check_code"] for item in detail_body["coverage"]}) == len(detail_body["coverage"])
    runs = client.get(f"/api/v1/inspection-runs?plan_id={plan['id']}").json()
    assert runs["total"] == 1
    with client.app.state.session_factory() as session:
        record = session.get(InspectionRecord, body["inspection_record_id"])
        assert record.summary_status == detail_body["status"]
        assert record.result_payload["status"] == detail_body["status"]

    deleted = client.delete(f"/api/v1/inspection-plans/{plan['id']}")
    assert deleted.status_code == 204
    assert client.get("/api/v1/inspection-plans").json()["total"] == 0
    detail = client.get(f"/api/v1/inspection-runs/{body['id']}")
    assert detail.status_code == 200
    assert detail.json()["plan_id"] is None


def test_plan_reentry_returns_conflict(client):
    plan_id = client.post("/api/v1/inspection-plans", json=_plan_payload("禁止重入")).json()["id"]
    with client.app.state.session_factory() as session:
        session.add(
            InspectionRunModel(
                plan_id=plan_id,
                trigger="scheduled",
                status="running",
                scope={"type": "namespace", "namespaces": ["demo"], "namespace": None, "label_selector": None, "pod_name": None},
                started_at=datetime.now(timezone.utc),
                coverage=[],
            )
        )
        session.commit()
    response = client.post(f"/api/v1/inspection-plans/{plan_id}/run")
    assert response.status_code == 409


def test_daily_next_run_uses_configured_timezone():
    after = datetime(2026, 7, 26, 0, 0, tzinfo=timezone.utc)
    result = next_run_at(
        PlanSchedule(interval="daily", daily_at="09:30", timezone="Asia/Shanghai"),
        after=after,
    )
    assert result == datetime(2026, 7, 26, 1, 30, tzinfo=timezone.utc)


def test_interval_next_run_is_strictly_after_start():
    after = datetime.now(timezone.utc)
    result = next_run_at(PlanSchedule(interval="5m", timezone="UTC"), after=after)
    assert result - after == timedelta(minutes=5)


def test_queued_run_is_restored_after_application_restart(test_settings):
    first_app = create_app(test_settings)
    with TestClient(first_app) as first:
        plan_id = first.post("/api/v1/inspection-plans", json=_plan_payload("重启恢复")).json()["id"]
        first.app.state.inspection_scheduler.shutdown(wait=False)
        queued = first.post(f"/api/v1/inspection-plans/{plan_id}/run")
        assert queued.status_code == 202
        run_id = queued.json()["id"]
        assert queued.json()["status"] == "queued"

    second_app = create_app(test_settings)
    with TestClient(second_app) as second:
        deadline = time.monotonic() + 2
        body = second.get(f"/api/v1/inspection-runs/{run_id}").json()
        while time.monotonic() < deadline and body["status"] in {"queued", "running"}:
            time.sleep(0.01)
            body = second.get(f"/api/v1/inspection-runs/{run_id}").json()
        assert body["status"] in {"succeeded", "partial"}
        assert second.get(f"/api/v1/inspection-runs?plan_id={plan_id}").json()["total"] == 1
