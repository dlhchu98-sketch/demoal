from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import desc, select, text
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.database import (
    ActivityLogORM,
    AgentRunLogORM,
    CitationRecordORM,
    IngestionLogORM,
    LegalDocumentORM,
    QueryHistoryORM,
    TestRunReportORM,
    UserORM,
)
from backend.app.schemas.legal import (
    ActivityLogItem,
    AdminDashboardResponse,
    IngestionLogItem,
    ServiceHealthItem,
    SystemConfigResponse,
    TestRunReportItem,
    UserProfile,
)
from backend.app.services.chat_service import list_history, runtime_state
from backend.app.services.legal_ingestion_service import LegalIngestionService


def log_activity(
    db: Session,
    *,
    action: str,
    resource: str,
    detail: str,
    user: UserORM | None = None,
    commit: bool = False,
) -> None:
    db.add(
        ActivityLogORM(
            id=f"ACT-{uuid.uuid4().hex[:10].upper()}",
            user_id=user.id if user else None,
            username=user.username if user else "anonymous",
            action=action,
            resource=resource,
            detail=detail,
            created_at=datetime.now(timezone.utc),
        )
    )
    if commit:
        db.commit()


def to_user_profile(user: UserORM) -> UserProfile:
    return UserProfile(
        id=user.id,
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        role=user.role,  # type: ignore[arg-type]
        is_active=user.is_active,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )


def mask_api_key(key: str) -> str:
    clean = (key or "").strip()
    if not clean:
        return "Chưa cấu hình"
    if len(clean) <= 8:
        return "*" * len(clean)
    return f"{clean[:4]}••••••••{clean[-4:]}"


def get_system_config_masked() -> SystemConfigResponse:
    settings = get_settings()
    db_backend = "PostgreSQL" if settings.database_url.startswith("postgres") else "SQLite (local fallback)"
    return SystemConfigResponse(
        app_mode=runtime_state.app_mode,
        llm_provider=settings.llm_provider,
        llm_model=runtime_state.llm_model or settings.llm_model,
        llm_base_url=settings.llm_base_url or "(Mặc định theo nhà cung cấp)",
        llm_api_key_configured=bool(settings.llm_api_key.strip()),
        llm_api_key_masked=mask_api_key(settings.llm_api_key),
        embedding_model=settings.embedding_model,
        qdrant_mode=settings.qdrant_mode,
        qdrant_url=settings.qdrant_url,
        qdrant_collection=settings.qdrant_collection,
        database_backend=db_backend,
        max_self_correction_attempts=runtime_state.max_self_correction_attempts,
        auto_scan_on_startup=settings.auto_scan_on_startup,
    )


def build_admin_dashboard(db: Session, ingestion_service: LegalIngestionService) -> AdminDashboardResponse:
    settings = get_settings()
    mode = runtime_state.app_mode

    # 1. Database health
    try:
        db.execute(text("SELECT 1"))
        db_kind = "PostgreSQL" if settings.database_url.startswith("postgres") else "SQLite (local fallback)"
        db_status = ServiceHealthItem(name="PostgreSQL / Database", status="online", detail=f"Đang hoạt động ({db_kind})")
    except Exception as exc:
        db_status = ServiceHealthItem(name="PostgreSQL / Database", status="offline", detail=str(exc))

    # 2. Qdrant health
    retriever = ingestion_service.get_retriever()
    q_conn, q_conn_detail = retriever.check_connection()
    q_avail, q_avail_detail = retriever.is_available()
    qdrant_status = ServiceHealthItem(
        name="Qdrant Vector DB",
        status="online" if q_conn else ("demo" if mode == "demo" else "offline"),
        detail=q_avail_detail if q_avail else q_conn_detail,
    )

    # 3. LLM health
    llm_ok = bool(settings.llm_api_key.strip())
    llm_status = ServiceHealthItem(
        name="LLM API",
        status="online" if llm_ok else ("demo" if mode == "demo" else "not_configured"),
        detail=(
            f"Đã cấu hình model {runtime_state.llm_model}"
            if llm_ok
            else "Chưa cấu hình LLM_API_KEY trong biến môi trường (.env)"
        ),
    )

    backend_status = ServiceHealthItem(
        name="FastAPI Backend",
        status="online",
        detail=f"Đang phục vụ API (APP_MODE={mode.upper()})",
    )

    # 4. Real DB counts — zero fake statistics
    docs = db.execute(select(LegalDocumentORM)).scalars().all()
    total_documents = len(docs)
    synced_documents = sum(1 for d in docs if d.qdrant_sync_status == "synced")
    failed_documents = sum(1 for d in docs if d.qdrant_sync_status == "failed")
    total_chunks = sum(d.chunk_count for d in docs)

    total_queries = db.query(QueryHistoryORM).count()
    total_users = db.query(UserORM).count()

    citations = db.execute(select(CitationRecordORM)).scalars().all()
    total_cit = len(citations)
    cit_pass = sum(1 for c in citations if c.validation_status == "PASS")
    cit_fail = sum(1 for c in citations if c.validation_status == "FAIL")
    cit_unv = sum(1 for c in citations if c.validation_status == "UNVERIFIED")

    self_corr_count = (
        db.query(AgentRunLogORM).filter(AgentRunLogORM.self_correction_attempts > 0).count()
    )

    recent_queries = list_history(db, limit=10)
    recent_ing_rows = db.execute(
        select(IngestionLogORM).order_by(desc(IngestionLogORM.created_at)).limit(10)
    ).scalars().all()
    recent_ingestion_logs = [
        IngestionLogItem(
            id=lg.id,
            file_path=lg.file_path,
            document_id=lg.document_id,
            action=lg.action,
            status=lg.status,
            message=lg.message,
            checksum=lg.checksum,
            chunk_count=lg.chunk_count,
            created_at=lg.created_at,
        )
        for lg in recent_ing_rows
    ]

    return AdminDashboardResponse(
        app_mode=mode,
        total_documents=total_documents,
        ingested_synced_documents=synced_documents,
        failed_documents=failed_documents,
        total_chunks=total_chunks,
        total_queries=total_queries,
        total_users=total_users,
        total_citations_checked=total_cit,
        citation_pass_count=cit_pass,
        citation_fail_count=cit_fail,
        citation_unverified_count=cit_unv,
        self_correction_count=self_corr_count,
        backend_status=backend_status,
        qdrant_status=qdrant_status,
        database_status=db_status,
        llm_status=llm_status,
        recent_queries=recent_queries,
        recent_ingestion_logs=recent_ingestion_logs,
    )


def list_activity_logs(db: Session, limit: int = 100) -> list[ActivityLogItem]:
    rows = db.execute(
        select(ActivityLogORM).order_by(desc(ActivityLogORM.created_at)).limit(limit)
    ).scalars().all()
    return [
        ActivityLogItem(
            id=r.id,
            user_id=r.user_id,
            username=r.username,
            action=r.action,
            resource=r.resource,
            detail=r.detail,
            created_at=r.created_at,
        )
        for r in rows
    ]


def list_test_reports(db: Session, limit: int = 30) -> list[TestRunReportItem]:
    rows = db.execute(
        select(TestRunReportORM).order_by(desc(TestRunReportORM.created_at)).limit(limit)
    ).scalars().all()
    return [
        TestRunReportItem(
            id=r.id,
            suite_name=r.suite_name,
            category=r.category,
            total=r.total,
            passed=r.passed,
            failed=r.failed,
            skipped=r.skipped,
            duration_ms=r.duration_ms,
            status=r.status,
            output_summary=r.output_summary,
            results=json.loads(r.results_json or "[]"),
            created_at=r.created_at,
        )
        for r in rows
    ]


def save_test_report(
    db: Session,
    *,
    suite_name: str,
    category: str,
    total: int,
    passed: int,
    failed: int,
    skipped: int,
    duration_ms: int,
    output_summary: str,
    results: list[dict],
) -> TestRunReportItem:
    status_val = "passed" if failed == 0 and total > 0 else ("failed" if failed > 0 else "empty")
    row = TestRunReportORM(
        id=f"TST-{uuid.uuid4().hex[:10].upper()}",
        suite_name=suite_name,
        category=category,
        total=total,
        passed=passed,
        failed=failed,
        skipped=skipped,
        duration_ms=duration_ms,
        status=status_val,
        output_summary=output_summary,
        results_json=json.dumps(results, ensure_ascii=False),
        created_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return TestRunReportItem(
        id=row.id,
        suite_name=row.suite_name,
        category=row.category,
        total=row.total,
        passed=row.passed,
        failed=row.failed,
        skipped=row.skipped,
        duration_ms=row.duration_ms,
        status=row.status,
        output_summary=row.output_summary,
        results=results,
        created_at=row.created_at,
    )
