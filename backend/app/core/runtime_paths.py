from pathlib import Path


def resolve_frontend_dist_path(configured_path: str | None) -> Path | None:
    if configured_path:
        candidate = Path(configured_path).expanduser().resolve()
        return candidate if candidate.exists() else None

    candidates = [
        Path(__file__).resolve().parents[3] / "frontend" / "dist",
        Path("/app/frontend-dist"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None
