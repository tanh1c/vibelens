"""
VibeLens Database Layer using SQLModel.

Benefits over raw SQLite:
- Type-safe models with Pydantic validation
- Better IDE support and autocomplete
- Cleaner code with less raw SQL
- Automatic schema generation
- Async support ready
"""

import json
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from sqlmodel import Field, Relationship, Session, SQLModel, create_engine, select, col

# Database path
DB_PATH = Path(__file__).parent.parent.parent / "vibelens.db"

# Create engine (singleton)
engine = None


def get_engine():
    """Get or create the database engine (singleton pattern)."""
    global engine
    if engine is None:
        engine = create_engine(
            f"sqlite:///{DB_PATH}",
            connect_args={"check_same_thread": False},
            echo=False,  # Set to True for SQL debugging
        )
        # Create tables on first run
        SQLModel.metadata.create_all(engine)
    return engine


def get_session():
    """Get a database session."""
    return Session(get_engine())


# ──────────────────────────────────────────────
# SQLModel Models (Type-safe)
# ──────────────────────────────────────────────

class SessionRecord(SQLModel, table=True):
    """Recording session model."""
    __tablename__ = "sessions"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    name: Optional[str] = Field(default=None)
    domain: str = Field(index=True)
    started_at: Optional[str] = Field(default=None)
    ended_at: Optional[str] = Field(default=None)
    request_count: int = Field(default=0)
    tags: Optional[str] = Field(default=None)  # JSON array
    notes: Optional[str] = Field(default=None)
    status: str = Field(default="active")  # active, completed, archived


class RequestRecord(SQLModel, table=True):
    """Individual request model."""
    __tablename__ = "requests"

    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: str = Field(foreign_key="sessions.id", index=True)
    request_id: Optional[str] = Field(default=None)
    url: str = Field(index=True)
    method: str = Field(index=True)
    status: Optional[int] = Field(default=None, index=True)
    mime_type: Optional[str] = Field(default=None)
    domain: Optional[str] = Field(default=None, index=True)
    timestamp: Optional[float] = Field(default=None)
    headers: Optional[str] = Field(default=None)  # JSON
    response_headers: Optional[str] = Field(default=None)  # JSON
    post_data: Optional[str] = Field(default=None)
    response_body: Optional[str] = Field(default=None)
    timing: Optional[str] = Field(default=None)  # JSON
    cookies: Optional[str] = Field(default=None)
    set_cookies: Optional[str] = Field(default=None)  # JSON array
    redirect_chain: Optional[str] = Field(default=None)  # JSON array
    encoded_size: Optional[int] = Field(default=None)
    completed: bool = Field(default=False)


class DomainCookieRecord(SQLModel, table=True):
    """Domain cookies snapshot."""
    __tablename__ = "domain_cookies"

    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: str = Field(foreign_key="sessions.id", index=True)
    domain: str = Field(index=True)
    cookies: str = Field(default="[]")  # JSON array
    captured_at: Optional[str] = Field(default=None)


# ──────────────────────────────────────────────
# Database Functions
# ──────────────────────────────────────────────

def init_db():
    """Initialize database tables."""
    get_engine()


def create_session(domain: str, name: str = None) -> str:
    """Create a new recording session."""
    session_record = SessionRecord(
        name=name or f"Session - {domain} ({time.strftime('%H:%M:%S')})",
        domain=domain,
        started_at=time.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )

    with get_session() as session:
        session.add(session_record)
        session.commit()
        return session_record.id


def save_requests(session_id: str, requests_data: list[dict[str, Any]]):
    """Save requests to database."""
    if not requests_data:
        return

    with get_session() as session:
        # Clear existing requests for this session
        session.exec(
            select(RequestRecord).where(RequestRecord.session_id == session_id)
        ).all()
        for req in session.exec(
            select(RequestRecord).where(RequestRecord.session_id == session_id)
        ):
            session.delete(req)

        # Insert new requests
        for req in requests_data:
            record = RequestRecord(
                session_id=session_id,
                request_id=req.get('requestId'),
                url=req.get('url', ''),
                method=req.get('method', 'GET'),
                status=req.get('status'),
                mime_type=req.get('mimeType'),
                domain=req.get('domain'),
                timestamp=req.get('timestamp'),
                headers=json.dumps(req.get('headers', {})),
                response_headers=json.dumps(req.get('responseHeaders', {})),
                post_data=(
                    req.get('postData')
                    if isinstance(req.get('postData'), str)
                    else json.dumps(req.get('postData', {}))
                ),
                response_body=req.get('responseBody'),
                timing=json.dumps(req.get('timing', {})),
                completed=bool(req.get('responseHeaders')),
            )
            session.add(record)

        # Update session request count
        db_session = session.get(SessionRecord, session_id)
        if db_session:
            db_session.request_count = len(requests_data)
            db_session.ended_at = time.strftime("%Y-%m-%dT%H:%M:%SZ")

        session.commit()


def save_metadata(session_id: str, meta: dict[str, Any]):
    """Save session metadata (cookies)."""
    if not meta or 'capturedCookies' not in meta:
        return

    captured_cookies = meta['capturedCookies']
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ")

    with get_session() as session:
        # Delete old cookies
        for record in session.exec(
            select(DomainCookieRecord).where(DomainCookieRecord.session_id == session_id)
        ):
            session.delete(record)

        # Insert new cookies
        for domain, cookies in captured_cookies.items():
            record = DomainCookieRecord(
                session_id=session_id,
                domain=domain,
                cookies=json.dumps(cookies),
                captured_at=now,
            )
            session.add(record)

        session.commit()


def get_recent_sessions(limit: int = 10) -> list[dict[str, Any]]:
    """Get recent sessions."""
    with get_session() as session:
        records = session.exec(
            select(SessionRecord)
            .order_by(col(SessionRecord.started_at).desc())
            .limit(limit)
        ).all()
        return [record.model_dump() for record in records]


def get_session_requests(session_id: str) -> list[dict[str, Any]]:
    """Get all requests for a session."""
    with get_session() as session:
        records = session.exec(
            select(RequestRecord)
            .where(RequestRecord.session_id == session_id)
            .order_by(col(RequestRecord.timestamp))
        ).all()

        requests = []
        for record in records:
            req = record.model_dump()
            # Parse JSON fields back to dicts
            for field in ['headers', 'response_headers', 'timing']:
                if req.get(field):
                    try:
                        req[field] = json.loads(req[field])
                    except json.JSONDecodeError:
                        pass
            requests.append(req)

        return requests


def get_session_metadata(session_id: str) -> dict[str, Any]:
    """Get session metadata (cookies and tracked domains)."""
    meta = {"capturedCookies": {}, "trackedDomains": []}

    with get_session() as session:
        records = session.exec(
            select(DomainCookieRecord).where(DomainCookieRecord.session_id == session_id)
        ).all()

        for record in records:
            try:
                meta["capturedCookies"][record.domain] = json.loads(record.cookies)
                meta["trackedDomains"].append(record.domain)
            except json.JSONDecodeError:
                pass

    return meta


def delete_request(request_id: int) -> str | None:
    """Delete a single request and return its string requestId."""
    with get_session() as session:
        record = session.get(RequestRecord, request_id)
        if record:
            req_str_id = record.request_id
            session.delete(record)
            session.commit()
            return req_str_id
    return None


def delete_requests_bulk(request_ids: list[int]) -> list[str]:
    """Delete multiple requests and return their string requestIds."""
    deleted_str_ids = []
    if not request_ids:
        return deleted_str_ids

    with get_session() as session:
        for rid in request_ids:
            record = session.get(RequestRecord, rid)
            if record:
                deleted_str_ids.append(record.request_id)
                session.delete(record)
        session.commit()
    return deleted_str_ids


def delete_session(session_id: str):
    """Delete a session and all related data."""
    with get_session() as session:
        # Delete related requests
        for record in session.exec(
            select(RequestRecord).where(RequestRecord.session_id == session_id)
        ):
            session.delete(record)

        # Delete related cookies
        for record in session.exec(
            select(DomainCookieRecord).where(DomainCookieRecord.session_id == session_id)
        ):
            session.delete(record)

        # Delete session
        session_record = session.get(SessionRecord, session_id)
        if session_record:
            session.delete(session_record)

        session.commit()


# Initialize on import
init_db()
