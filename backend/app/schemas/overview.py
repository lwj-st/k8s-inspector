from pydantic import BaseModel


class OverviewIssue(BaseModel):
    name: str
    component: str | None = None
    namespace: str | None = None
    node: str | None = None
    status: str
    summary: str


class OverviewResponse(BaseModel):
    health_status: str
    health_score: int
    last_checked_at: str
    issues: list[OverviewIssue]
    recent_summary: str
