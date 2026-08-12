import re
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_provider
from app.providers.base import InspectionProvider
from app.schemas.log_recording import (
    LogRecordingCreate,
    LogRecordingLineRead,
    LogRecordingLogPage,
    LogRecordingPodRead,
    LogRecordingPreview,
    LogRecordingPreviewRequest,
    LogRecordingRead,
    LogRecordingStatus,
    LogRecordingStorageUsage,
    LogRecordingTemplateMatchRead,
    LogRecordingUpdate,
    LogRecordingViewMode,
)
from app.schemas.v1_1 import Page
from app.services import log_recording_engine
from app.services import log_recording_service


router = APIRouter(prefix="/log-recordings", tags=["log-recordings"])


def _safe_log_filename(*parts: str) -> str:
    normalized_parts = []
    for part in parts:
        normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", part.strip()).strip("-._")
        normalized_parts.append(normalized[:80] or "unknown")
    return "_".join(normalized_parts) + ".log"


def _attachment_disposition(filename: str) -> str:
    return f"attachment; filename=\"{filename}\"; filename*=UTF-8''{quote(filename)}"


@router.post("/preview", response_model=LogRecordingPreview)
def preview_log_recording(
    payload: LogRecordingPreviewRequest,
    session: Session = Depends(get_db_session),
    provider: InspectionProvider = Depends(get_provider),
) -> LogRecordingPreview:
    return log_recording_service.preview_recording(session, provider, payload.namespace)


@router.get("/storage", response_model=LogRecordingStorageUsage)
def get_log_recording_storage_usage(
    session: Session = Depends(get_db_session),
) -> LogRecordingStorageUsage:
    return log_recording_service.storage_usage(session)


@router.post("", response_model=LogRecordingRead, status_code=status.HTTP_201_CREATED)
def create_log_recording(
    payload: LogRecordingCreate,
    request: Request,
    session: Session = Depends(get_db_session),
    provider: InspectionProvider = Depends(get_provider),
) -> LogRecordingRead:
    authenticated = getattr(request.state, "authenticated_session", None)
    try:
        row = log_recording_service.create_recording(
            session,
            provider,
            payload,
            created_by=authenticated.username if authenticated else "development",
        )
    except log_recording_service.LogRecordingStorageFullError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except log_recording_service.LogRecordingScopeTooLargeError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except log_recording_service.LogRecordingDurationError as exc:
        return _validation_error(request, str(exc))
    log_recording_engine.schedule_auto_stop(request.app, row.id)
    return LogRecordingRead.model_validate(row)


@router.get("", response_model=Page[LogRecordingRead])
def list_log_recordings(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    namespace: str | None = Query(default=None, min_length=1, max_length=253),
    session: Session = Depends(get_db_session),
) -> Page[LogRecordingRead]:
    return log_recording_service.list_recordings(
        session,
        page=page,
        page_size=page_size,
        namespace=namespace,
    )


@router.get("/{recording_id}", response_model=LogRecordingRead)
def get_log_recording(
    recording_id: int,
    session: Session = Depends(get_db_session),
) -> LogRecordingRead:
    try:
        return LogRecordingRead.model_validate(log_recording_service.get_recording(session, recording_id))
    except log_recording_service.LogRecordingNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


def _validation_error(request: Request, reason: str) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    headers = {"x-request-id": request_id} if request_id else None
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "code": "REQUEST_VALIDATION_FAILED",
            "message": "请求参数校验失败",
            "request_id": request_id,
            "details": {"reason": reason},
        },
        headers=headers,
    )


@router.patch("/{recording_id}", response_model=LogRecordingRead)
def update_log_recording(
    recording_id: int,
    payload: LogRecordingUpdate,
    session: Session = Depends(get_db_session),
) -> LogRecordingRead:
    try:
        return LogRecordingRead.model_validate(log_recording_service.update_recording(session, recording_id, payload))
    except log_recording_service.LogRecordingNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/{recording_id}/stop", response_model=LogRecordingRead)
def stop_log_recording(
    recording_id: int,
    request: Request,
    session: Session = Depends(get_db_session),
    provider: InspectionProvider = Depends(get_provider),
) -> LogRecordingRead:
    try:
        try:
            log_recording_service.collect_recording_once(session, provider, recording_id)
        except Exception:
            row = log_recording_service.get_recording(session, recording_id)
            if row.status != LogRecordingStatus.recording.value:
                log_recording_engine.remove_auto_stop(request.app, recording_id)
                return LogRecordingRead.model_validate(row)
        row = log_recording_service.stop_recording(session, recording_id)
        log_recording_engine.remove_auto_stop(request.app, recording_id)
        return LogRecordingRead.model_validate(row)
    except log_recording_service.LogRecordingNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except log_recording_service.LogRecordingAlreadyStoppedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.delete("/{recording_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_log_recording(
    recording_id: int,
    request: Request,
    session: Session = Depends(get_db_session),
) -> Response:
    try:
        log_recording_service.delete_recording(session, recording_id)
        log_recording_engine.remove_auto_stop(request.app, recording_id)
    except log_recording_service.LogRecordingNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{recording_id}/template-match", response_model=list[LogRecordingTemplateMatchRead])
def match_log_recording_templates(
    recording_id: int,
    session: Session = Depends(get_db_session),
) -> list[LogRecordingTemplateMatchRead]:
    try:
        return log_recording_service.match_recording_templates(session, recording_id)
    except log_recording_service.LogRecordingNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/{recording_id}/pods", response_model=list[LogRecordingPodRead])
def list_log_recording_pods(
    recording_id: int,
    session: Session = Depends(get_db_session),
) -> list[LogRecordingPodRead]:
    try:
        return log_recording_service.list_pods(session, recording_id)
    except log_recording_service.LogRecordingNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/{recording_id}/pods/{pod_name}/containers/{container_name}/logs",
    response_model=LogRecordingLogPage,
)
def list_log_recording_logs(
    recording_id: int,
    pod_name: str,
    container_name: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    view: LogRecordingViewMode = Query(default=LogRecordingViewMode.folded),
    session: Session = Depends(get_db_session),
) -> LogRecordingLogPage:
    try:
        return log_recording_service.list_logs(
            session,
            recording_id,
            pod_name=pod_name,
            container_name=container_name,
            page=page,
            page_size=page_size,
            view=view,
        )
    except log_recording_service.LogRecordingNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/{recording_id}/pods/{pod_name}/containers/{container_name}/logs/download")
def download_log_recording_logs(
    recording_id: int,
    pod_name: str,
    container_name: str,
    view: LogRecordingViewMode = Query(default=LogRecordingViewMode.folded),
    session: Session = Depends(get_db_session),
) -> StreamingResponse:
    try:
        content = log_recording_service.download_logs(
            session,
            recording_id,
            pod_name=pod_name,
            container_name=container_name,
            view=view,
        )
    except log_recording_service.LogRecordingNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    filename = _safe_log_filename(
        f"recording-{recording_id}",
        pod_name,
        container_name,
        view.value,
    )
    return StreamingResponse(
        content,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": _attachment_disposition(filename)},
    )
