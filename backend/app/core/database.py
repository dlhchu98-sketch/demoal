from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Generator

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from backend.app.core.config import get_settings


class Base(DeclarativeBase):
    pass


class UserORM(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), default="user", index=True)  # user | admin
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RevokedTokenORM(Base):
    __tablename__ = "revoked_tokens"

    jti: Mapped[str] = mapped_column(String(64), primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class QueryHistoryORM(Base):
    __tablename__ = "query_history"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    conversation_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    analysis_json: Mapped[str] = mapped_column(Text, default="[]")
    citations_json: Mapped[str] = mapped_column(Text, default="[]")
    citation_status: Mapped[str] = mapped_column(String(32), default="UNVERIFIED", index=True)
    self_correction_json: Mapped[str] = mapped_column(Text, default="{}")
    pipeline_trace_json: Mapped[str] = mapped_column(Text, default="[]")
    structured_result_json: Mapped[str] = mapped_column(Text, default="{}")
    is_mock: Mapped[bool] = mapped_column(Boolean, default=True)
    app_mode: Mapped[str] = mapped_column(String(16), default="demo")
    processing_time_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )


class CitationRecordORM(Base):
    __tablename__ = "citation_records"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    request_id: Mapped[str] = mapped_column(String(64), index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    claim: Mapped[str] = mapped_column(Text, nullable=False)
    document_name: Mapped[str] = mapped_column(String(255), nullable=False)
    document_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    article: Mapped[str | None] = mapped_column(String(64), nullable=True)
    clause: Mapped[str | None] = mapped_column(String(64), nullable=True)
    point: Mapped[str | None] = mapped_column(String(64), nullable=True)
    evidence: Mapped[str] = mapped_column(Text, default="")
    validation_status: Mapped[str] = mapped_column(String(32), default="UNVERIFIED", index=True)
    validation_reason: Mapped[str] = mapped_column(Text, default="")
    relevance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_mock: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )


class SavedItemORM(Base):
    """Lưu trữ văn bản yêu thích, điều khoản đã lưu, câu trả lời đã lưu cho User Portal."""

    __tablename__ = "saved_items"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    item_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)  # document | clause | answer
    target_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    subtitle: Mapped[str | None] = mapped_column(String(512), nullable=True)
    content: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )


class ChatFeedbackORM(Base):
    """Đánh giá chất lượng câu trả lời từ người dùng."""

    __tablename__ = "chat_feedback"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)  # 1..5
    helpful: Mapped[bool] = mapped_column(Boolean, default=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )


class AgentRunLogORM(Base):
    """Nhật ký thực thi từng bước của Agent phục vụ Admin Portal."""

    __tablename__ = "agent_run_logs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    conversation_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    stages_json: Mapped[str] = mapped_column(Text, default="[]")
    overall_status: Mapped[str] = mapped_column(String(32), default="UNVERIFIED", index=True)
    self_correction_attempts: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    is_mock: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )


class ActivityLogORM(Base):
    """Nhật ký hoạt động người dùng & quản trị viên."""

    __tablename__ = "activity_logs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    username: Mapped[str] = mapped_column(String(128), default="anonymous")
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resource: Mapped[str] = mapped_column(String(128), default="system")
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )


class TestRunReportORM(Base):
    """Lưu kết quả chạy kiểm thử thực tế (Pytest / API / RAG / Agent / Citation / E2E)."""

    __tablename__ = "test_run_reports"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    suite_name: Mapped[str] = mapped_column(String(128), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    total: Mapped[int] = mapped_column(Integer, default=0)
    passed: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    skipped: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="passed")
    output_summary: Mapped[str] = mapped_column(Text, default="")
    results_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )


class EvaluationRunORM(Base):
    __tablename__ = "evaluation_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_mode: Mapped[str] = mapped_column(String(16), default="demo")
    is_mock: Mapped[bool] = mapped_column(Boolean, default=True)
    dataset_size: Mapped[int] = mapped_column(Integer, default=0)
    summary_note: Mapped[str] = mapped_column(Text, default="")
    results_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )


class LegalDocumentORM(Base):
    """Lưu trữ chuẩn hóa metadata văn bản pháp luật thật đã tiếp nhận từ data/legal_documents/."""

    __tablename__ = "legal_documents"

    document_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    document_number: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    document_type: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    issuing_authority: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    issue_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    effective_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    expiry_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    source: Mapped[str | None] = mapped_column(String(512), nullable=True)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False, index=True)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    qdrant_sync_status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    qdrant_synced_chunks: Mapped[int] = mapped_column(Integer, default=0)
    embedding_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    qdrant_collection: Mapped[str | None] = mapped_column(String(128), nullable=True)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    ingestion_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class LegalChunkORM(Base):
    """Lưu trữ nguyên văn từng chunk theo cấu trúc Phần/Chương/Mục/Điều/Khoản/Điểm."""

    __tablename__ = "legal_chunks"

    chunk_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    document_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("legal_documents.document_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, default=0, index=True)
    document_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    document_title: Mapped[str] = mapped_column(String(512), nullable=False)
    part: Mapped[str | None] = mapped_column(String(255), nullable=True)
    chapter: Mapped[str | None] = mapped_column(String(255), nullable=True)
    section: Mapped[str | None] = mapped_column(String(255), nullable=True)
    article: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    clause: Mapped[str | None] = mapped_column(String(64), nullable=True)
    point: Mapped[str | None] = mapped_column(String(64), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str | None] = mapped_column(String(512), nullable=True)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    effective_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)


class IngestionLogORM(Base):
    """Nhật ký tiếp nhận, xử lý, trùng lặp và lỗi khi nạp văn bản pháp luật."""

    __tablename__ = "ingestion_logs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False, index=True)
    document_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )


def _create_db_engine():
    settings = get_settings()
    if settings.database_url.startswith("sqlite"):
        from sqlalchemy import event

        eng = create_engine(
            settings.database_url,
            future=True,
            connect_args={"check_same_thread": False, "timeout": 30},
        )

        @event.listens_for(eng, "connect")
        def _set_sqlite_pragma(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.execute("PRAGMA busy_timeout=30000")
            finally:
                cursor.close()

        return eng
    return create_engine(settings.database_url, future=True)


engine = _create_db_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def _ensure_additive_columns(target_engine) -> None:
    """Bổ sung an toàn các cột mới cho bảng đã tồn tại trên SQLite/PostgreSQL mà không làm mất dữ liệu cũ."""
    insp = inspect(target_engine)
    if "query_history" in insp.get_table_names():
        existing_cols = {c["name"] for c in insp.get_columns("query_history")}
        with target_engine.begin() as conn:
            if "user_id" not in existing_cols:
                conn.execute(text("ALTER TABLE query_history ADD COLUMN user_id VARCHAR(64)"))
            if "structured_result_json" not in existing_cols:
                conn.execute(text("ALTER TABLE query_history ADD COLUMN structured_result_json TEXT DEFAULT '{}'"))


def seed_default_users(db: Session) -> None:
    """Khởi tạo tài khoản quản trị viên và người dùng mẫu nếu bảng users đang trống."""
    from backend.app.core.security import hash_password

    settings = get_settings()
    if db.query(UserORM).count() > 0:
        return

    now = datetime.now(timezone.utc)
    db.add(
        UserORM(
            id=f"USR-ADMIN-{uuid.uuid4().hex[:6].upper()}",
            username="admin",
            email=settings.default_admin_email.lower(),
            full_name="Quản trị viên hệ thống Legal AI",
            password_hash=hash_password(settings.default_admin_password),
            role="admin",
            is_active=True,
            created_at=now,
        )
    )
    db.add(
        UserORM(
            id=f"USR-DEMO-{uuid.uuid4().hex[:6].upper()}",
            username="sinhvien",
            email=settings.default_user_email.lower(),
            full_name="Người dùng tra cứu (Sinh viên)",
            password_hash=hash_password(settings.default_user_password),
            role="user",
            is_active=True,
            created_at=now,
        )
    )
    db.commit()


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_additive_columns(engine)
    with SessionLocal() as db:
        seed_default_users(db)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
