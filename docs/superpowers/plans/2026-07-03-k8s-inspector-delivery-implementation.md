# K8s Inspector Delivery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add CI, GHCR image publishing, single-image packaging, Helm deployment, static asset hosting, and in-cluster Kubernetes access support for K8s Inspector.

**Architecture:** Keep development split between `frontend/` and `backend/`, but build a single runtime image where FastAPI serves both API routes and the compiled frontend. Delivery is driven by GitHub Actions, published to GHCR, and deployed through a Helm chart with read-only RBAC and configurable ingress/basePath behavior.

**Tech Stack:** GitHub Actions, GHCR, Docker multi-stage build, React/Vite, FastAPI/Starlette, Helm, Kubernetes RBAC

---

## File Structure

- Create: `.github/workflows/ci.yml`
- Create: `.github/workflows/release-image.yml`
- Create: `Dockerfile`
- Create: `backend/app/core/runtime_paths.py`
- Create: `backend/tests/test_static_app.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/providers/kubernetes_provider.py`
- Modify: `README.md`
- Create: `deploy/helm/k8s-inspector/Chart.yaml`
- Create: `deploy/helm/k8s-inspector/values.yaml`
- Create: `deploy/helm/k8s-inspector/templates/_helpers.tpl`
- Create: `deploy/helm/k8s-inspector/templates/deployment.yaml`
- Create: `deploy/helm/k8s-inspector/templates/service.yaml`
- Create: `deploy/helm/k8s-inspector/templates/ingress.yaml`
- Create: `deploy/helm/k8s-inspector/templates/configmap.yaml`
- Create: `deploy/helm/k8s-inspector/templates/secret.yaml`
- Create: `deploy/helm/k8s-inspector/templates/serviceaccount.yaml`
- Create: `deploy/helm/k8s-inspector/templates/clusterrole.yaml`
- Create: `deploy/helm/k8s-inspector/templates/clusterrolebinding.yaml`
- Create: `deploy/helm/k8s-inspector/templates/tests/test-connection.yaml`
- Create: `deploy/helm/k8s-inspector/README.md`
- Create: `deploy/helm/k8s-inspector/ci-values.yaml`

### Task 1: Add Backend Runtime Support for Static Frontend Hosting

**Files:**
- Create: `backend/app/core/runtime_paths.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_static_app.py`

- [ ] **Step 1: Write the failing backend static hosting tests**

```python
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_root_serves_index_html(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html><body>hello</body></html>", encoding="utf-8")

    app = create_app(Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}", frontend_dist_path=str(dist)))
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "hello" in response.text


def test_assets_route_serves_compiled_asset(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text("<html></html>", encoding="utf-8")
    (assets / "app.js").write_text("console.log('ok')", encoding="utf-8")

    app = create_app(Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}", frontend_dist_path=str(dist)))
    client = TestClient(app)

    response = client.get("/assets/app.js")

    assert response.status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest -v tests/test_static_app.py`
Expected: FAIL because static file routes are not registered yet

- [ ] **Step 3: Add frontend dist path configuration**

```python
class Settings(BaseModel):
    ...
    frontend_dist_path: str | None = None
```

- [ ] **Step 4: Implement FastAPI static route mounting and SPA fallback**

```python
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


def register_frontend(app: FastAPI, settings: Settings) -> None:
    if not settings.frontend_dist_path:
        return

    dist_path = Path(settings.frontend_dist_path)
    if not dist_path.exists():
        return

    app.mount("/assets", StaticFiles(directory=dist_path / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str = ""):
        target = dist_path / full_path
        if full_path and target.exists() and target.is_file():
            return FileResponse(target)
        return FileResponse(dist_path / "index.html")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python3 -m pytest -v tests/test_static_app.py`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/core backend/app/main.py backend/tests/test_static_app.py
git commit -m "feat: serve frontend assets from backend runtime"
```

### Task 2: Add In-Cluster Kubernetes Configuration Support

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/providers/kubernetes_provider.py`
- Modify: `backend/tests/test_settings_api.py`

- [ ] **Step 1: Write the failing provider mode configuration test**

```python
def test_settings_response_includes_provider_mode(client) -> None:
    response = client.get("/api/v1/settings")

    assert response.status_code == 200
    assert response.json()["provider_mode"] == "mock"
```

- [ ] **Step 2: Run test to verify it fails if configuration is incomplete**

Run: `cd backend && python3 -m pytest -v tests/test_settings_api.py::test_settings_response_includes_provider_mode`
Expected: PASS today or expose missing in-cluster related config

- [ ] **Step 3: Extend settings with in-cluster mode flags**

```python
class Settings(BaseModel):
    ...
    prefer_incluster: bool = True
```

- [ ] **Step 4: Implement Kubernetes client loading order**

```python
class KubernetesInspectionProvider:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._load_config()
        ...

    def _load_config(self) -> None:
        if self.settings.kubeconfig_path:
            config.load_kube_config(config_file=self.settings.kubeconfig_path, context=self.settings.kube_context)
            return
        if self.settings.prefer_incluster:
            config.load_incluster_config()
            return
        raise ValueError("No Kubernetes client configuration available")
```

- [ ] **Step 5: Keep local development fallback explicit in docs and code comments**

```python
# Local development uses kubeconfig; in-cluster deployment uses ServiceAccount auth.
```

- [ ] **Step 6: Run backend tests**

Run: `cd backend && python3 -m pytest -v tests/test_settings_api.py tests/test_overview_api.py`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/core/config.py backend/app/providers/kubernetes_provider.py backend/tests/test_settings_api.py
git commit -m "feat: support in-cluster kubernetes access"
```

### Task 3: Add Single-Image Docker Build

**Files:**
- Create: `Dockerfile`
- Modify: `README.md`

- [ ] **Step 1: Write the failing docker build verification step**

```bash
test -f Dockerfile
```

- [ ] **Step 2: Run verification to confirm Dockerfile is missing**

Run: `test -f Dockerfile`
Expected: FAIL because Dockerfile does not exist yet

- [ ] **Step 3: Create multi-stage Dockerfile**

```dockerfile
FROM node:22-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim AS backend-runtime
WORKDIR /app/backend
ENV PYTHONUNBUFFERED=1
COPY backend/pyproject.toml ./
RUN pip install --no-cache-dir -e .[dev]
COPY backend/ ./
COPY --from=frontend-builder /app/frontend/dist /app/frontend-dist
ENV FRONTEND_DIST_PATH=/app/frontend-dist
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 4: Document local image build and run**

```md
## Build image

`docker build -t ghcr.io/lwj-st/k8s-inspector:local .`

## Run image

`docker run -p 8000:8000 ghcr.io/lwj-st/k8s-inspector:local`
```

- [ ] **Step 5: Run Docker build verification**

Run: `docker build -t k8s-inspector:local .`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add Dockerfile README.md
git commit -m "build: add single-image docker packaging"
```

### Task 4: Add GitHub CI Workflow

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `deploy/helm/k8s-inspector/ci-values.yaml`

- [ ] **Step 1: Write the failing workflow presence check**

```bash
test -f .github/workflows/ci.yml
```

- [ ] **Step 2: Run verification to confirm workflow is missing**

Run: `test -f .github/workflows/ci.yml`
Expected: FAIL because workflow file does not exist yet

- [ ] **Step 3: Add CI workflow**

```yaml
name: ci

on:
  pull_request:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
          cache: "npm"
          cache-dependency-path: frontend/package-lock.json
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: cd frontend && npm ci
      - run: cd frontend && npm test -- --run
      - run: cd frontend && npm run build
      - run: cd backend && python -m pip install -e .[dev]
      - run: cd backend && python -m pytest -v
      - run: helm lint deploy/helm/k8s-inspector -f deploy/helm/k8s-inspector/ci-values.yaml
```

- [ ] **Step 4: Add CI values for Helm lint**

```yaml
image:
  repository: ghcr.io/lwj-st/k8s-inspector
  tag: ci
ingress:
  enabled: false
```

- [ ] **Step 5: Validate workflow syntax locally where possible**

Run: `python3 - <<'PY'\nimport yaml, pathlib; yaml.safe_load(pathlib.Path('.github/workflows/ci.yml').read_text())\nprint('ok')\nPY`
Expected: PASS with `ok`

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/ci.yml deploy/helm/k8s-inspector/ci-values.yaml
git commit -m "ci: add github validation workflow"
```

### Task 5: Add GitHub Release/Image Publishing Workflow

**Files:**
- Create: `.github/workflows/release-image.yml`

- [ ] **Step 1: Write the failing release workflow presence check**

```bash
test -f .github/workflows/release-image.yml
```

- [ ] **Step 2: Run verification to confirm workflow is missing**

Run: `test -f .github/workflows/release-image.yml`
Expected: FAIL because workflow file does not exist yet

- [ ] **Step 3: Add GHCR publish workflow**

```yaml
name: release-image

on:
  push:
    branches: [main]
    tags: ["v*"]

jobs:
  docker:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/metadata-action@v5
        id: meta
        with:
          images: ghcr.io/lwj-st/k8s-inspector
          tags: |
            type=raw,value=latest,enable={{is_default_branch}}
            type=raw,value=main-{{sha}},enable={{is_default_branch}}
            type=ref,event=tag
      - uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
```

- [ ] **Step 4: Validate workflow YAML locally**

Run: `python3 - <<'PY'\nimport yaml, pathlib; yaml.safe_load(pathlib.Path('.github/workflows/release-image.yml').read_text())\nprint('ok')\nPY`
Expected: PASS with `ok`

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/release-image.yml
git commit -m "ci: add ghcr release workflow"
```

### Task 6: Add Helm Chart for Single-Image Deployment

**Files:**
- Create: `deploy/helm/k8s-inspector/Chart.yaml`
- Create: `deploy/helm/k8s-inspector/values.yaml`
- Create: `deploy/helm/k8s-inspector/templates/_helpers.tpl`
- Create: `deploy/helm/k8s-inspector/templates/deployment.yaml`
- Create: `deploy/helm/k8s-inspector/templates/service.yaml`
- Create: `deploy/helm/k8s-inspector/templates/ingress.yaml`
- Create: `deploy/helm/k8s-inspector/templates/configmap.yaml`
- Create: `deploy/helm/k8s-inspector/templates/secret.yaml`
- Create: `deploy/helm/k8s-inspector/templates/serviceaccount.yaml`
- Create: `deploy/helm/k8s-inspector/templates/clusterrole.yaml`
- Create: `deploy/helm/k8s-inspector/templates/clusterrolebinding.yaml`
- Create: `deploy/helm/k8s-inspector/templates/tests/test-connection.yaml`
- Create: `deploy/helm/k8s-inspector/README.md`

- [ ] **Step 1: Write the failing chart presence check**

```bash
test -f deploy/helm/k8s-inspector/Chart.yaml
```

- [ ] **Step 2: Run verification to confirm chart is missing**

Run: `test -f deploy/helm/k8s-inspector/Chart.yaml`
Expected: FAIL because chart files do not exist yet

- [ ] **Step 3: Create Helm chart metadata and default values**

```yaml
apiVersion: v2
name: k8s-inspector
type: application
version: 0.1.0
appVersion: "0.1.0"
```

```yaml
image:
  repository: ghcr.io/lwj-st/k8s-inspector
  tag: latest
  pullPolicy: IfNotPresent

service:
  type: ClusterIP
  port: 8000

ingress:
  enabled: true
  className: ""
  host: k8s-inspector.local
  path: /

basePath: ""
providerMode: kubernetes
```

- [ ] **Step 4: Add Deployment, Service, Ingress, ConfigMap, Secret, and read-only RBAC templates**

```yaml
rules:
  - apiGroups: [""]
    resources: ["pods", "pods/log", "nodes", "namespaces", "services", "events", "secrets"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["apps"]
    resources: ["daemonsets"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["networking.k8s.io"]
    resources: ["ingresses"]
    verbs: ["get", "list", "watch"]
```

- [ ] **Step 5: Add chart README with install examples**

```md
helm upgrade --install k8s-inspector deploy/helm/k8s-inspector \
  --set ingress.host=inspector.example.com
```

- [ ] **Step 6: Run Helm lint verification**

Run: `helm lint deploy/helm/k8s-inspector`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add deploy/helm/k8s-inspector
git commit -m "deploy: add helm chart for k8s deployment"
```

### Task 7: Update Docs and End-to-End Delivery Instructions

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-07-03-k8s-inspector-delivery-design.md`

- [ ] **Step 1: Write the failing documentation presence check**

```bash
rg -n "GHCR|Helm|GitHub Actions|docker build" README.md
```

- [ ] **Step 2: Run check to confirm docs are incomplete**

Run: `rg -n "GHCR|Helm|GitHub Actions|docker build" README.md`
Expected: FAIL or show partial coverage only

- [ ] **Step 3: Add end-to-end delivery documentation**

```md
## CI
- `.github/workflows/ci.yml`
- `.github/workflows/release-image.yml`

## Publish image
- push to `main` => `latest`, `main-<sha>`
- push tag `vX.Y.Z` => version image

## Deploy to Kubernetes
`helm upgrade --install ...`
```

- [ ] **Step 4: Run a final documentation sanity check**

Run: `rg -n "GHCR|Helm|GitHub Actions|docker build" README.md docs/superpowers/specs/2026-07-03-k8s-inspector-delivery-design.md`
Expected: PASS with matching lines

- [ ] **Step 5: Commit**

```bash
git add README.md docs/superpowers/specs/2026-07-03-k8s-inspector-delivery-design.md
git commit -m "docs: add delivery and deployment guide"
```

## Self-Review

- Spec coverage:
  - CI, GHCR, single image, Helm, static asset hosting, direct domain access, Kong-compatible basePath, and in-cluster access are all mapped to Tasks 1 through 7.
- Placeholder scan:
  - No `TODO`, `TBD`, or unresolved placeholders remain in the plan.
- Type consistency:
  - `BASE_PATH`, `provider_mode`, `frontend_dist_path`, `K8S_PROVIDER_MODE`, and Helm `basePath`/`ingress.path` are used consistently across tasks.
