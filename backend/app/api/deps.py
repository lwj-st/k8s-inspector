from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.orm import Session

from app.providers.mock_provider import MockInspectionProvider


def get_db_session(request: Request) -> Iterator[Session]:
    session_factory = request.app.state.session_factory
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def get_provider(request: Request) -> MockInspectionProvider:
    return request.app.state.provider
