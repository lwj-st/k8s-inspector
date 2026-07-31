from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.schemas.v1_1 import (
    Issue,
    IssueAcknowledgeRequest,
    IssueEvent,
    IssueFilterOptions,
    IssueListFilter,
    IssueSeverity,
    IssueSortMode,
    IssueStatus,
    Page,
)
from app.services import issue_lifecycle, issue_query, settings_service


router = APIRouter(prefix="/issues", tags=["issues"])


@router.get("", response_model=Page[Issue])
def list_issues(
    request: Request,
    status_filter: IssueStatus | None = Query(default=None, alias="status"),
    severity: IssueSeverity | None = None,
    namespace: str | None = None,
    resource_kind: str | None = None,
    source_check: str | None = None,
    sort: IssueSortMode = IssueSortMode.priority,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_db_session),
) -> Page[Issue]:
    cluster_id = settings_service.get_effective_cluster_id(session, request.app.state.settings)
    return issue_query.list_issues(
        session,
        IssueListFilter(
            status=status_filter,
            severity=severity,
            namespace=namespace,
            resource_kind=resource_kind,
            source_check=source_check,
            sort=sort,
            page=page,
            page_size=page_size,
        ),
        cluster_id=cluster_id,
    )


@router.get("/filter-options", response_model=IssueFilterOptions)
def list_issue_filter_options(
    request: Request,
    session: Session = Depends(get_db_session),
) -> IssueFilterOptions:
    cluster_id = settings_service.get_effective_cluster_id(session, request.app.state.settings)
    return issue_query.list_issue_filter_options(
        session,
        cluster_id=cluster_id,
    )


@router.get("/{issue_id}", response_model=Issue)
def get_issue(issue_id: int, request: Request, session: Session = Depends(get_db_session)) -> Issue:
    cluster_id = settings_service.get_effective_cluster_id(session, request.app.state.settings)
    row = issue_query.get_issue(
        session,
        issue_id,
        cluster_id=cluster_id,
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="问题不存在")
    return issue_query.issue_from_model(row)


@router.get("/{issue_id}/events", response_model=Page[IssueEvent])
def list_issue_events(
    request: Request,
    issue_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_db_session),
) -> Page[IssueEvent]:
    cluster_id = settings_service.get_effective_cluster_id(session, request.app.state.settings)
    result = issue_query.list_issue_events(
        session,
        issue_id=issue_id,
        page=page,
        page_size=page_size,
        cluster_id=cluster_id,
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="问题不存在")
    return result


@router.post("/{issue_id}/acknowledge", response_model=Issue)
def acknowledge_issue(
    issue_id: int,
    payload: IssueAcknowledgeRequest,
    request: Request,
    session: Session = Depends(get_db_session),
) -> Issue:
    cluster_id = settings_service.get_effective_cluster_id(session, request.app.state.settings)
    if issue_query.get_issue(
        session,
        issue_id,
        cluster_id=cluster_id,
    ) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="问题不存在")
    result = issue_lifecycle.acknowledge_issue(
        session,
        issue_id=issue_id,
        payload=payload,
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="问题不存在")
    return result


@router.post("/{issue_id}/ignore", response_model=Issue)
def ignore_issue(
    issue_id: int,
    request: Request,
    session: Session = Depends(get_db_session),
) -> Issue:
    cluster_id = settings_service.get_effective_cluster_id(session, request.app.state.settings)
    if issue_query.get_issue(
        session,
        issue_id,
        cluster_id=cluster_id,
    ) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="问题不存在")
    result = issue_lifecycle.ignore_issue(session, issue_id=issue_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="问题不存在")
    return result


@router.post("/{issue_id}/unignore", response_model=Issue)
def unignore_issue(
    issue_id: int,
    request: Request,
    session: Session = Depends(get_db_session),
) -> Issue:
    cluster_id = settings_service.get_effective_cluster_id(session, request.app.state.settings)
    if issue_query.get_issue(
        session,
        issue_id,
        cluster_id=cluster_id,
    ) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="问题不存在")
    result = issue_lifecycle.unignore_issue(session, issue_id=issue_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="问题不存在")
    return result
