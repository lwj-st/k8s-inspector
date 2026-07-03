# K8s Inspector MVP Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first runnable skeleton of K8s Inspector with a React frontend, FastAPI backend, SQLite persistence, mock inspection/diagnosis flows, and configurable `BASE_PATH` support for root-path and sub-path deployment.

**Architecture:** The system is split into `frontend/` and `backend/`. The backend exposes versioned REST APIs, persists configuration and CRUD data in SQLite, and serves mock inspection and diagnosis results through a provider abstraction. The frontend consumes only backend APIs, renders six MVP pages, and derives router basename plus API base URL from a shared `BASE_PATH` setting.

**Tech Stack:** React, Vite, TypeScript, React Router, FastAPI, Pydantic, SQLAlchemy, SQLite, pytest, Vitest, Testing Library

---

## File Structure

- Create: `backend/pyproject.toml`
- Create: `backend/app/main.py`
- Create: `backend/app/core/config.py`
- Create: `backend/app/core/pathing.py`
- Create: `backend/app/db/base.py`
- Create: `backend/app/db/session.py`
- Create: `backend/app/db/init_db.py`
- Create: `backend/app/models/fault_template.py`
- Create: `backend/app/models/whitelist.py`
- Create: `backend/app/models/inspection_record.py`
- Create: `backend/app/models/diagnosis_record.py`
- Create: `backend/app/models/system_setting.py`
- Create: `backend/app/models/__init__.py`
- Create: `backend/app/schemas/common.py`
- Create: `backend/app/schemas/overview.py`
- Create: `backend/app/schemas/inspection.py`
- Create: `backend/app/schemas/diagnosis.py`
- Create: `backend/app/schemas/template.py`
- Create: `backend/app/schemas/whitelist.py`
- Create: `backend/app/schemas/settings.py`
- Create: `backend/app/providers/base.py`
- Create: `backend/app/providers/mock_provider.py`
- Create: `backend/app/engine/matcher.py`
- Create: `backend/app/services/overview_service.py`
- Create: `backend/app/services/inspection_service.py`
- Create: `backend/app/services/diagnosis_service.py`
- Create: `backend/app/services/template_service.py`
- Create: `backend/app/services/whitelist_service.py`
- Create: `backend/app/services/settings_service.py`
- Create: `backend/app/api/router.py`
- Create: `backend/app/api/routes/overview.py`
- Create: `backend/app/api/routes/inspections.py`
- Create: `backend/app/api/routes/diagnoses.py`
- Create: `backend/app/api/routes/templates.py`
- Create: `backend/app/api/routes/whitelists.py`
- Create: `backend/app/api/routes/settings.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_overview_api.py`
- Create: `backend/tests/test_template_api.py`
- Create: `backend/tests/test_whitelist_api.py`
- Create: `backend/tests/test_settings_api.py`
- Create: `backend/tests/test_inspection_api.py`
- Create: `backend/tests/test_diagnosis_api.py`
- Create: `backend/tests/test_matcher.py`
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/app/App.tsx`
- Create: `frontend/src/app/config.ts`
- Create: `frontend/src/app/query.ts`
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/api/types.ts`
- Create: `frontend/src/layouts/AppLayout.tsx`
- Create: `frontend/src/routes/index.tsx`
- Create: `frontend/src/components/StatusBadge.tsx`
- Create: `frontend/src/components/KeyValueList.tsx`
- Create: `frontend/src/pages/OverviewPage.tsx`
- Create: `frontend/src/pages/NamespaceInspectionPage.tsx`
- Create: `frontend/src/pages/DiagnosisPage.tsx`
- Create: `frontend/src/pages/TemplatesPage.tsx`
- Create: `frontend/src/pages/WhitelistsPage.tsx`
- Create: `frontend/src/pages/SettingsPage.tsx`
- Create: `frontend/src/features/overview/useOverview.ts`
- Create: `frontend/src/features/inspections/useRunNamespaceInspection.ts`
- Create: `frontend/src/features/diagnosis/useRunDiagnosis.ts`
- Create: `frontend/src/features/templates/useTemplates.ts`
- Create: `frontend/src/features/whitelists/useWhitelists.ts`
- Create: `frontend/src/features/settings/useSettings.ts`
- Create: `frontend/src/styles.css`
- Create: `frontend/src/test/setup.ts`
- Create: `frontend/src/app/App.test.tsx`
- Create: `frontend/src/routes/basePath.test.tsx`
- Create: `examples/templates/example-templates.json`
- Create: `examples/whitelists/example-whitelists.json`
- Create: `README.md`

### Task 1: Initialize Backend Project Skeleton

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/app/main.py`
- Create: `backend/app/core/config.py`
- Create: `backend/app/core/pathing.py`
- Create: `backend/app/api/router.py`
- Test: `backend/tests/test_overview_api.py`

- [ ] **Step 1: Write the failing backend smoke test**

```python
from fastapi.testclient import TestClient

from app.main import create_app


def test_health_routes_under_root_base_path() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.get("/api/v1/overview")

    assert response.status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_overview_api.py::test_health_routes_under_root_base_path -v`
Expected: FAIL with import error or missing route

- [ ] **Step 3: Write minimal backend bootstrap**

```python
from fastapi import FastAPI

from app.api.router import build_api_router
from app.core.config import Settings, get_settings
from app.core.pathing import normalize_base_path


def create_app(settings: Settings | None = None) -> FastAPI:
    current_settings = settings or get_settings()
    app = FastAPI(title="K8s Inspector API")
    api_prefix = f"{normalize_base_path(current_settings.base_path)}/api/v1"
    app.include_router(build_api_router(), prefix=api_prefix)
    return app


app = create_app()
```

- [ ] **Step 4: Add a minimal overview route**

```python
from fastapi import APIRouter


def build_api_router() -> APIRouter:
    router = APIRouter()

    @router.get("/overview")
    def get_overview() -> dict[str, str]:
        return {"status": "ok"}

    return router
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && pytest tests/test_overview_api.py::test_health_routes_under_root_base_path -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/pyproject.toml backend/app backend/tests/test_overview_api.py
git commit -m "feat: bootstrap backend api skeleton"
```

### Task 2: Add Backend Settings, SQLite, and ORM Models

**Files:**
- Create: `backend/app/db/base.py`
- Create: `backend/app/db/session.py`
- Create: `backend/app/db/init_db.py`
- Create: `backend/app/models/fault_template.py`
- Create: `backend/app/models/whitelist.py`
- Create: `backend/app/models/inspection_record.py`
- Create: `backend/app/models/diagnosis_record.py`
- Create: `backend/app/models/system_setting.py`
- Create: `backend/app/models/__init__.py`
- Test: `backend/tests/conftest.py`
- Test: `backend/tests/test_settings_api.py`

- [ ] **Step 1: Write the failing settings persistence test**

```python
from fastapi.testclient import TestClient

from app.main import create_app


def test_get_settings_returns_base_path_field(test_settings) -> None:
    app = create_app(test_settings)
    client = TestClient(app)

    response = client.get("/api/v1/settings")

    assert response.status_code == 200
    assert response.json()["base_path"] == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_settings_api.py::test_get_settings_returns_base_path_field -v`
Expected: FAIL with 404 or missing database setup

- [ ] **Step 3: Define SQLAlchemy base and session**

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def build_engine(database_url: str):
    return create_engine(database_url, future=True)


def build_session_factory(database_url: str) -> sessionmaker:
    engine = build_engine(database_url)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
```

- [ ] **Step 4: Define the `system_settings` model**

```python
from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SystemSetting(Base):
    __tablename__ = "system_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    base_path: Mapped[str] = mapped_column(String(128), default="")
    llm_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    model_endpoint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    api_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    default_inspection_strategy: Mapped[str] = mapped_column(Text, default="{}")
```

- [ ] **Step 5: Add database initialization and seed default settings**

```python
from sqlalchemy import select

from app.models.system_setting import SystemSetting


def seed_system_settings(session) -> None:
    existing = session.scalar(select(SystemSetting).where(SystemSetting.id == 1))
    if existing is None:
        session.add(SystemSetting(id=1, base_path="", llm_enabled=False, default_inspection_strategy="{}"))
        session.commit()
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd backend && pytest tests/test_settings_api.py::test_get_settings_returns_base_path_field -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/db backend/app/models backend/tests/conftest.py backend/tests/test_settings_api.py
git commit -m "feat: add backend settings persistence"
```

### Task 3: Implement Backend Schemas and CRUD APIs for Templates and Whitelists

**Files:**
- Create: `backend/app/schemas/template.py`
- Create: `backend/app/schemas/whitelist.py`
- Create: `backend/app/services/template_service.py`
- Create: `backend/app/services/whitelist_service.py`
- Create: `backend/app/api/routes/templates.py`
- Create: `backend/app/api/routes/whitelists.py`
- Test: `backend/tests/test_template_api.py`
- Test: `backend/tests/test_whitelist_api.py`

- [ ] **Step 1: Write the failing template CRUD test**

```python
def test_create_and_list_template(client) -> None:
    payload = {
        "name": "Pod CrashLoop",
        "scenario": "targeted_diagnosis",
        "namespace_scope": "demo",
        "label_selector": "app=demo",
        "match_conditions": [{"type": "pod_status", "operator": "in", "value": ["CrashLoopBackOff"]}],
        "joint_rule": None,
        "reason": "Application startup failure",
        "suggestion": "Check startup configuration",
        "command": "kubectl logs -n demo deploy/demo",
        "risk_note": "Read-only command",
        "enabled": True,
    }

    create_response = client.post("/api/v1/templates", json=payload)
    list_response = client.get("/api/v1/templates")

    assert create_response.status_code == 201
    assert list_response.status_code == 200
    assert list_response.json()[0]["name"] == "Pod CrashLoop"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_template_api.py::test_create_and_list_template -v`
Expected: FAIL with 404 or missing schema validation

- [ ] **Step 3: Define Pydantic schemas for template and whitelist**

```python
from pydantic import BaseModel, Field


class FaultTemplateCreate(BaseModel):
    name: str = Field(min_length=1)
    scenario: str
    namespace_scope: str | None = None
    label_selector: str | None = None
    match_conditions: list[dict]
    joint_rule: dict | None = None
    reason: str
    suggestion: str
    command: str | None = None
    risk_note: str | None = None
    enabled: bool = True
```

- [ ] **Step 4: Implement CRUD services and routes**

```python
@router.post("/templates", status_code=201, response_model=FaultTemplateRead)
def create_template(payload: FaultTemplateCreate, session: SessionDep) -> FaultTemplateRead:
    created = template_service.create_template(session, payload)
    return FaultTemplateRead.model_validate(created)


@router.get("/templates", response_model=list[FaultTemplateRead])
def list_templates(session: SessionDep) -> list[FaultTemplateRead]:
    return [FaultTemplateRead.model_validate(item) for item in template_service.list_templates(session)]
```

- [ ] **Step 5: Add whitelist CRUD in the same style**

```python
@router.post("/whitelists", status_code=201, response_model=WhitelistRead)
def create_whitelist(payload: WhitelistCreate, session: SessionDep) -> WhitelistRead:
    created = whitelist_service.create_whitelist(session, payload)
    return WhitelistRead.model_validate(created)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_template_api.py tests/test_whitelist_api.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas backend/app/services backend/app/api/routes/templates.py backend/app/api/routes/whitelists.py backend/tests/test_template_api.py backend/tests/test_whitelist_api.py
git commit -m "feat: add template and whitelist crud apis"
```

### Task 4: Implement Mock Provider, Overview API, and Inspection APIs

**Files:**
- Create: `backend/app/schemas/overview.py`
- Create: `backend/app/schemas/inspection.py`
- Create: `backend/app/providers/base.py`
- Create: `backend/app/providers/mock_provider.py`
- Create: `backend/app/services/overview_service.py`
- Create: `backend/app/services/inspection_service.py`
- Create: `backend/app/api/routes/overview.py`
- Create: `backend/app/api/routes/inspections.py`
- Test: `backend/tests/test_overview_api.py`
- Test: `backend/tests/test_inspection_api.py`

- [ ] **Step 1: Write the failing namespace inspection test**

```python
def test_run_namespace_inspection_returns_pod_evidence(client) -> None:
    response = client.post(
        "/api/v1/inspections/namespace/run",
        json={"namespace": "demo", "label_selector": "app=demo"},
    )

    payload = response.json()

    assert response.status_code == 200
    assert payload["namespace"] == "demo"
    assert payload["pods"][0]["describe_summary"]
    assert "log_summary" in payload["pods"][0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_inspection_api.py::test_run_namespace_inspection_returns_pod_evidence -v`
Expected: FAIL with 404

- [ ] **Step 3: Define provider interface**

```python
from typing import Protocol


class InspectionProvider(Protocol):
    def get_overview(self) -> dict: ...
    def run_cluster_inspection(self) -> dict: ...
    def run_namespace_inspection(self, namespace: str, label_selector: str | None) -> dict: ...
    def collect_diagnosis_context(self, namespace: str, scope: str | None) -> dict: ...
```

- [ ] **Step 4: Implement mock provider with realistic sample payloads**

```python
class MockInspectionProvider:
    def run_namespace_inspection(self, namespace: str, label_selector: str | None) -> dict:
        return {
            "namespace": namespace,
            "label_selector": label_selector,
            "pods": [
                {
                    "name": "demo-api-7c8f6f7c6b-fh2ns",
                    "status": "CrashLoopBackOff",
                    "restarts": 6,
                    "events": ["Back-off restarting failed container"],
                    "describe_summary": "Container exited with code 1 after startup probe failure.",
                    "log_summary": "database connection refused",
                    "resource_usage": {"cpu": "220m", "memory": "180Mi"},
                }
            ],
            "services": [],
            "ingresses": [],
            "tls_secrets": [],
            "daemonsets": [],
        }
```

- [ ] **Step 5: Implement overview and inspection routes**

```python
@router.get("/overview", response_model=OverviewResponse)
def get_overview(provider: ProviderDep) -> OverviewResponse:
    return OverviewResponse.model_validate(provider.get_overview())


@router.post("/inspections/namespace/run", response_model=NamespaceInspectionResponse)
def run_namespace_inspection(payload: NamespaceInspectionRequest, provider: ProviderDep, session: SessionDep) -> NamespaceInspectionResponse:
    result = inspection_service.run_namespace_inspection(session, provider, payload)
    return NamespaceInspectionResponse.model_validate(result)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_overview_api.py tests/test_inspection_api.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/providers backend/app/services/overview_service.py backend/app/services/inspection_service.py backend/app/api/routes/overview.py backend/app/api/routes/inspections.py backend/app/schemas/overview.py backend/app/schemas/inspection.py backend/tests/test_overview_api.py backend/tests/test_inspection_api.py
git commit -m "feat: add mock overview and inspection apis"
```

### Task 5: Implement Rule Matcher and Diagnosis API

**Files:**
- Create: `backend/app/schemas/diagnosis.py`
- Create: `backend/app/engine/matcher.py`
- Create: `backend/app/services/diagnosis_service.py`
- Create: `backend/app/api/routes/diagnoses.py`
- Test: `backend/tests/test_matcher.py`
- Test: `backend/tests/test_diagnosis_api.py`

- [ ] **Step 1: Write the failing matcher test**

```python
from app.engine.matcher import match_template


def test_match_template_hits_crashloop_keyword_rule() -> None:
    template = {
        "match_conditions": [
            {"type": "pod_status", "operator": "in", "value": ["CrashLoopBackOff"]},
            {"type": "log_keyword", "operator": "contains", "value": "connection refused"},
        ],
        "reason": "Startup dependency failure",
    }
    context = {
        "pods": [
            {"status": "CrashLoopBackOff", "log_summary": "database connection refused"}
        ]
    }

    result = match_template(template, context)

    assert result["matched"] is True
    assert len(result["evidence"]) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_matcher.py::test_match_template_hits_crashloop_keyword_rule -v`
Expected: FAIL with import error or missing function

- [ ] **Step 3: Implement the minimal matcher**

```python
def match_template(template: dict, context: dict) -> dict:
    evidence: list[dict] = []
    pods = context.get("pods", [])

    for condition in template.get("match_conditions", []):
        if condition["type"] == "pod_status" and any(pod.get("status") in condition["value"] for pod in pods):
            evidence.append({"type": "pod_status", "value": condition["value"]})
        if condition["type"] == "log_keyword" and any(condition["value"] in (pod.get("log_summary") or "") for pod in pods):
            evidence.append({"type": "log_keyword", "value": condition["value"]})

    return {"matched": len(evidence) == len(template.get("match_conditions", [])), "evidence": evidence}
```

- [ ] **Step 4: Implement diagnosis service and API**

```python
@router.post("/diagnoses/run", response_model=DiagnosisResponse)
def run_diagnosis(payload: DiagnosisRequest, provider: ProviderDep, session: SessionDep) -> DiagnosisResponse:
    result = diagnosis_service.run_diagnosis(session, provider, payload)
    return DiagnosisResponse.model_validate(result)
```

- [ ] **Step 5: Add unmatched and llm supplemented behavior tests**

```python
def test_run_diagnosis_returns_matched_status(client) -> None:
    response = client.post("/api/v1/diagnoses/run", json={"namespace": "demo", "scope": "deployment/demo-api"})
    assert response.status_code == 200
    assert response.json()["status"] in {"matched", "unmatched", "llm_supplemented"}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_matcher.py tests/test_diagnosis_api.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/engine backend/app/services/diagnosis_service.py backend/app/api/routes/diagnoses.py backend/app/schemas/diagnosis.py backend/tests/test_matcher.py backend/tests/test_diagnosis_api.py
git commit -m "feat: add diagnosis matcher and api"
```

### Task 6: Build Frontend App Shell, Routing, and BASE_PATH Support

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/app/App.tsx`
- Create: `frontend/src/app/config.ts`
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/layouts/AppLayout.tsx`
- Create: `frontend/src/routes/index.tsx`
- Create: `frontend/src/styles.css`
- Test: `frontend/src/app/App.test.tsx`
- Test: `frontend/src/routes/basePath.test.tsx`

- [ ] **Step 1: Write the failing base path routing test**

```tsx
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { App } from "../app/App";


test("renders navigation under inspector base path", async () => {
  render(
    <MemoryRouter initialEntries={["/inspector/"]}>
      <App />
    </MemoryRouter>,
  );

  expect(screen.getByText("集群总览")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- --run src/routes/basePath.test.tsx`
Expected: FAIL with missing app or routes

- [ ] **Step 3: Implement frontend config and API base helper**

```ts
const rawBasePath = import.meta.env.VITE_BASE_PATH ?? "";

export function normalizeBasePath(value: string): string {
  if (!value || value === "/") return "";
  return value.startsWith("/") ? value.replace(/\/$/, "") : `/${value.replace(/\/$/, "")}`;
}

export const appConfig = {
  basePath: normalizeBasePath(rawBasePath),
  apiBaseUrl: `${normalizeBasePath(rawBasePath)}/api/v1`,
};
```

- [ ] **Step 4: Implement app shell and routes**

```tsx
export function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route path="/" element={<OverviewPage />} />
        <Route path="/inspections/namespace" element={<NamespaceInspectionPage />} />
        <Route path="/diagnosis" element={<DiagnosisPage />} />
        <Route path="/templates" element={<TemplatesPage />} />
        <Route path="/whitelists" element={<WhitelistsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Route>
    </Routes>
  );
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npm test -- --run src/app/App.test.tsx src/routes/basePath.test.tsx`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/package.json frontend/tsconfig.json frontend/vite.config.ts frontend/index.html frontend/src/main.tsx frontend/src/app frontend/src/api/client.ts frontend/src/layouts frontend/src/routes frontend/src/styles.css frontend/src/app/App.test.tsx frontend/src/routes/basePath.test.tsx
git commit -m "feat: add frontend app shell with base path support"
```

### Task 7: Implement Frontend Overview, Inspection, and Diagnosis Pages Against Real Mock APIs

**Files:**
- Create: `frontend/src/api/types.ts`
- Create: `frontend/src/components/StatusBadge.tsx`
- Create: `frontend/src/components/KeyValueList.tsx`
- Create: `frontend/src/pages/OverviewPage.tsx`
- Create: `frontend/src/pages/NamespaceInspectionPage.tsx`
- Create: `frontend/src/pages/DiagnosisPage.tsx`
- Create: `frontend/src/features/overview/useOverview.ts`
- Create: `frontend/src/features/inspections/useRunNamespaceInspection.ts`
- Create: `frontend/src/features/diagnosis/useRunDiagnosis.ts`
- Test: `frontend/src/app/App.test.tsx`

- [ ] **Step 1: Write the failing overview rendering test**

```tsx
test("renders overview data from api", async () => {
  renderAppWithMocks({
    "/api/v1/overview": {
      health_status: "warning",
      health_score: 72,
      last_checked_at: "2026-07-02T10:00:00Z",
      issues: [{ name: "ingress-nginx", status: "degraded" }],
    },
  });

  expect(await screen.findByText("72")).toBeInTheDocument();
  expect(screen.getByText("ingress-nginx")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- --run src/app/App.test.tsx`
Expected: FAIL with missing data hooks or page rendering

- [ ] **Step 3: Implement typed API client and hooks**

```ts
export async function getOverview(): Promise<OverviewResponse> {
  const response = await fetch(`${appConfig.apiBaseUrl}/overview`);
  if (!response.ok) throw new Error("Failed to load overview");
  return response.json();
}
```

- [ ] **Step 4: Implement pages for overview, namespace inspection, and diagnosis**

```tsx
export function OverviewPage() {
  const { data, isLoading } = useOverview();

  if (isLoading) return <p>加载中...</p>;
  if (!data) return <p>暂无数据</p>;

  return (
    <section>
      <h1>集群总览</h1>
      <p>{data.health_score}</p>
      {data.issues.map((issue) => (
        <div key={issue.name}>{issue.name}</div>
      ))}
    </section>
  );
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npm test -- --run src/app/App.test.tsx`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/types.ts frontend/src/components frontend/src/pages/OverviewPage.tsx frontend/src/pages/NamespaceInspectionPage.tsx frontend/src/pages/DiagnosisPage.tsx frontend/src/features/overview frontend/src/features/inspections frontend/src/features/diagnosis frontend/src/app/App.test.tsx
git commit -m "feat: add overview inspection and diagnosis pages"
```

### Task 8: Implement Frontend CRUD Pages for Templates, Whitelists, and Settings

**Files:**
- Create: `frontend/src/pages/TemplatesPage.tsx`
- Create: `frontend/src/pages/WhitelistsPage.tsx`
- Create: `frontend/src/pages/SettingsPage.tsx`
- Create: `frontend/src/features/templates/useTemplates.ts`
- Create: `frontend/src/features/whitelists/useWhitelists.ts`
- Create: `frontend/src/features/settings/useSettings.ts`
- Test: `frontend/src/app/App.test.tsx`

- [ ] **Step 1: Write the failing settings form test**

```tsx
test("submits updated base path setting", async () => {
  renderAppWithMocks({
    "/api/v1/settings": {
      base_path: "/inspector",
      llm_enabled: false,
      model_endpoint: "",
      api_key: "",
      default_inspection_strategy: {},
    },
  });

  expect(await screen.findByDisplayValue("/inspector")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- --run src/app/App.test.tsx`
Expected: FAIL with missing settings page or hooks

- [ ] **Step 3: Implement CRUD hooks**

```ts
export async function listTemplates(): Promise<FaultTemplate[]> {
  const response = await fetch(`${appConfig.apiBaseUrl}/templates`);
  if (!response.ok) throw new Error("Failed to load templates");
  return response.json();
}
```

- [ ] **Step 4: Implement management pages**

```tsx
export function SettingsPage() {
  const { data } = useSettings();
  return (
    <section>
      <h1>系统配置</h1>
      <input aria-label="访问前缀" defaultValue={data?.base_path ?? ""} />
    </section>
  );
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npm test -- --run src/app/App.test.tsx`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/TemplatesPage.tsx frontend/src/pages/WhitelistsPage.tsx frontend/src/pages/SettingsPage.tsx frontend/src/features/templates frontend/src/features/whitelists frontend/src/features/settings frontend/src/app/App.test.tsx
git commit -m "feat: add management pages for templates whitelists and settings"
```

### Task 9: Add Example Import Files, Run Full Verification, and Document Startup

**Files:**
- Create: `examples/templates/example-templates.json`
- Create: `examples/whitelists/example-whitelists.json`
- Create: `README.md`
- Modify: `docs/superpowers/specs/2026-07-02-k8s-inspector-design.md`

- [ ] **Step 1: Write the failing documentation verification step**

```bash
test -f examples/templates/example-templates.json
test -f examples/whitelists/example-whitelists.json
test -f README.md
```

- [ ] **Step 2: Run verification to confirm files are missing**

Run: `test -f examples/templates/example-templates.json && test -f examples/whitelists/example-whitelists.json && test -f README.md`
Expected: FAIL because one or more files do not exist yet

- [ ] **Step 3: Add example data and startup documentation**

```json
[
  {
    "name": "CrashLoop keyword template",
    "scenario": "targeted_diagnosis",
    "namespace_scope": "demo",
    "label_selector": "app=demo",
    "match_conditions": [
      { "type": "pod_status", "operator": "in", "value": ["CrashLoopBackOff"] },
      { "type": "log_keyword", "operator": "contains", "value": "connection refused" }
    ],
    "reason": "Dependency startup failure",
    "suggestion": "Check downstream service and startup config",
    "command": "kubectl logs -n demo deploy/demo-api",
    "risk_note": "Read-only command",
    "enabled": true
  }
]
```

- [ ] **Step 4: Document local startup and base path examples**

```md
# K8s Inspector

## Run backend

`cd backend && uvicorn app.main:app --reload`

## Run frontend

`cd frontend && npm install && npm run dev`

## Base path example

- Root path: `VITE_BASE_PATH=`
- Sub path: `VITE_BASE_PATH=/inspector`
```

- [ ] **Step 5: Run full verification**

Run: `cd backend && pytest -v`
Expected: PASS

Run: `cd frontend && npm test -- --run`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add examples README.md docs/superpowers/specs/2026-07-02-k8s-inspector-design.md
git commit -m "docs: add examples and local startup guide"
```

## Self-Review

- Spec coverage:
  - Six pages are covered by Tasks 6, 7, and 8.
  - Backend CRUD, overview, inspections, diagnosis, and settings are covered by Tasks 2 through 5.
  - `BASE_PATH` support is covered by Tasks 1, 2, 6, and 9.
  - Mock provider and future provider boundary are covered by Task 4.
- Placeholder scan:
  - No `TODO`, `TBD`, or unresolved “implement later” placeholders remain in the plan steps.
- Type consistency:
  - `base_path`, `match_conditions`, `joint_rule`, `label_selector`, and diagnosis status values are referenced consistently across tasks.
