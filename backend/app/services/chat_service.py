from __future__ import annotations

import json
import uuid
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from agent.graph import LegalAgentOrchestrator
from agent.validator import CitationValidator
from backend.app.core.config import get_settings
from backend.app.core.database import (
    AgentRunLogORM,
    ChatFeedbackORM,
    CitationRecordORM,
    QueryHistoryORM,
    UserORM,
)
from backend.app.schemas.legal import (
    AppMode,
    ChatFeedbackRequest,
    ChatFeedbackResponse,
    ChatRequest,
    ChatResponse,
    CitationItem,
    ConversationSummary,
    HistorySummary,
    LegalIssueItem,
    PipelineTraceStep,
    ProcessingStatusInfo,
    SelfCorrectionInfo,
    ValidationDetailItem,
)
from backend.app.services.ai_integration import enrich_chat_response
from backend.app.services.legal_ingestion_service import legal_ingestion_service
from backend.app.services.mock_service import build_demo_chat_response


class RuntimeState:
    def __init__(self) -> None:
        settings = get_settings()
        self.app_mode: AppMode = "live" if settings.app_mode.lower() == "live" else "demo"
        self.llm_model: str = settings.llm_model
        self.max_self_correction_attempts: int = settings.max_self_correction_attempts


runtime_state = RuntimeState()


def process_chat(
    db: Session,
    request: ChatRequest,
    current_user: UserORM | None = None,
) -> ChatResponse:
    settings = get_settings()
    mode = runtime_state.app_mode
    max_attempts = runtime_state.max_self_correction_attempts
    error_message: str | None = None

    if mode == "demo":
        response = build_demo_chat_response(
            request=request,
            max_attempts=max_attempts,
        )
    else:
        retriever = legal_ingestion_service.get_retriever()
        orchestrator = LegalAgentOrchestrator(
            retriever=retriever,
            validator=CitationValidator(),
            llm_api_key=settings.llm_api_key,
            llm_model=runtime_state.llm_model or settings.llm_model,
            llm_base_url=settings.llm_base_url,
            max_attempts=max_attempts,
        )
        try:
            response = orchestrator.run_live(
                question=request.question,
                conversation_id=request.conversation_id,
            )
        except Exception as exc:
            error_message = str(exc)
            raise

    # Bổ sung hợp đồng API Mục 5.1 + tiến trình 7 bước thật + kiểm chứng 6 tiêu chí
    response = enrich_chat_response(db, response)

    structured_payload = {
        "conclusion": response.conclusion,
        "explanation": response.explanation,
        "limitations": response.limitations,
        "verification_label": response.verification_label,
        "validation_details": [v.model_dump() for v in response.validation_details],
        "processing_status": response.processing_status.model_dump(),
    }

    now = response.created_at or datetime.now(timezone.utc)
    user_id = current_user.id if current_user else None

    # Lưu lịch sử tra cứu vào DB
    history_row = QueryHistoryORM(
        id=response.request_id,
        conversation_id=response.conversation_id,
        user_id=user_id,
        question=response.question,
        answer=response.answer,
        analysis_json=json.dumps([a.model_dump() for a in response.analysis], ensure_ascii=False),
        citations_json=json.dumps([c.model_dump() for c in response.citations], ensure_ascii=False),
        citation_status=response.citation_status,
        self_correction_json=json.dumps(response.self_correction.model_dump(), ensure_ascii=False),
        pipeline_trace_json=json.dumps([p.model_dump() for p in response.pipeline_trace], ensure_ascii=False),
        structured_result_json=json.dumps(structured_payload, ensure_ascii=False),
        is_mock=response.is_mock,
        app_mode=response.app_mode,
        processing_time_ms=response.processing_time_ms,
        created_at=now,
    )
    db.add(history_row)

    # Lưu nhật ký thực thi Agent cho Admin Portal
    db.add(
        AgentRunLogORM(
            id=f"AGT-{uuid.uuid4().hex[:10].upper()}",
            request_id=response.request_id,
            conversation_id=response.conversation_id,
            user_id=user_id,
            question=response.question,
            stages_json=json.dumps([s.model_dump() for s in response.processing_status.steps], ensure_ascii=False),
            overall_status=response.citation_status,
            self_correction_attempts=response.self_correction.attempts,
            error_message=error_message,
            latency_ms=response.processing_time_ms,
            is_mock=response.is_mock,
            created_at=now,
        )
    )

    for cit in response.citations:
        db.add(
            CitationRecordORM(
                id=str(uuid.uuid4()),
                request_id=response.request_id,
                question=response.question,
                claim=cit.claim or response.question,
                document_name=cit.document_name,
                document_number=cit.document_number,
                article=cit.article,
                clause=cit.clause,
                point=cit.point,
                evidence=cit.evidence,
                validation_status=cit.validation_status,
                validation_reason=cit.validation_reason or "",
                relevance_score=cit.relevance_score,
                is_mock=response.is_mock,
                created_at=now,
            )
        )

    db.commit()
    return response


def _row_to_chat_response(row: QueryHistoryORM) -> ChatResponse:
    structured = json.loads(row.structured_result_json or "{}")
    resp = ChatResponse(
        request_id=row.id,
        conversation_id=row.conversation_id,
        question=row.question,
        answer=row.answer,
        conclusion=structured.get("conclusion", ""),
        explanation=structured.get("explanation", ""),
        limitations=structured.get("limitations", []),
        verification_label=structured.get("verification_label", "Chưa đủ bằng chứng"),
        validation_details=[
            ValidationDetailItem(**v) for v in structured.get("validation_details", [])
        ],
        processing_status=ProcessingStatusInfo(**structured["processing_status"])
        if structured.get("processing_status")
        else ProcessingStatusInfo(),
        analysis=[LegalIssueItem(**x) for x in json.loads(row.analysis_json or "[]")],
        citations=[CitationItem(**x) for x in json.loads(row.citations_json or "[]")],
        citation_status=row.citation_status,  # type: ignore[arg-type]
        self_correction=SelfCorrectionInfo(**json.loads(row.self_correction_json or "{}")),
        pipeline_trace=[PipelineTraceStep(**x) for x in json.loads(row.pipeline_trace_json or "[]")],
        is_mock=row.is_mock,
        app_mode=row.app_mode,  # type: ignore[arg-type]
        processing_time_ms=row.processing_time_ms,
        created_at=row.created_at,
    )
    return resp


def list_history(
    db: Session,
    search: str | None = None,
    limit: int = 100,
    current_user: UserORM | None = None,
) -> list[HistorySummary]:
    stmt = select(QueryHistoryORM).order_by(desc(QueryHistoryORM.created_at)).limit(limit)
    if current_user is not None and current_user.role != "admin":
        stmt = (
            select(QueryHistoryORM)
            .where((QueryHistoryORM.user_id == current_user.id) | (QueryHistoryORM.user_id.is_(None)))
            .order_by(desc(QueryHistoryORM.created_at))
            .limit(limit)
        )
    rows = db.execute(stmt).scalars().all()
    if search and search.strip():
        term = search.strip().lower()
        rows = [r for r in rows if term in r.question.lower() or term in r.answer.lower()]

    result: list[HistorySummary] = []
    for r in rows:
        citations = json.loads(r.citations_json or "[]")
        self_corr = json.loads(r.self_correction_json or "{}")
        preview = r.answer.replace("\n", " ").strip()
        if len(preview) > 160:
            preview = preview[:157] + "..."
        result.append(
            HistorySummary(
                id=r.id,
                conversation_id=r.conversation_id,
                question=r.question,
                answer_preview=preview,
                citation_status=r.citation_status,  # type: ignore[arg-type]
                citations_count=len(citations),
                self_correction_performed=bool(self_corr.get("performed", False)),
                is_mock=r.is_mock,
                app_mode=r.app_mode,
                processing_time_ms=r.processing_time_ms,
                created_at=r.created_at,
            )
        )
    return result


def list_conversations(
    db: Session,
    search: str | None = None,
    current_user: UserORM | None = None,
) -> list[ConversationSummary]:
    stmt = select(QueryHistoryORM).order_by(desc(QueryHistoryORM.created_at))
    if current_user is not None and current_user.role != "admin":
        stmt = stmt.where((QueryHistoryORM.user_id == current_user.id) | (QueryHistoryORM.user_id.is_(None)))
    rows = db.execute(stmt).scalars().all()

    grouped: dict[str, list[QueryHistoryORM]] = defaultdict(list)
    for r in rows:
        cid = r.conversation_id or r.id
        grouped[cid].append(r)

    summaries: list[ConversationSummary] = []
    for cid, msgs in grouped.items():
        msgs_sorted = sorted(msgs, key=lambda x: x.created_at)
        first = msgs_sorted[0]
        latest = msgs_sorted[-1]
        if search and search.strip():
            term = search.strip().lower()
            if not any(term in m.question.lower() or term in m.answer.lower() for m in msgs_sorted):
                continue
        preview = latest.answer.replace("\n", " ").strip()
        if len(preview) > 150:
            preview = preview[:147] + "..."
        summaries.append(
            ConversationSummary(
                conversation_id=cid,
                title=first.question[:90] + ("..." if len(first.question) > 90 else ""),
                last_question=latest.question,
                last_answer_preview=preview,
                message_count=len(msgs_sorted),
                latest_citation_status=latest.citation_status,  # type: ignore[arg-type]
                is_mock=latest.is_mock,
                updated_at=latest.created_at,
            )
        )
    summaries.sort(key=lambda s: s.updated_at, reverse=True)
    return summaries


def get_conversation_messages(db: Session, conversation_id: str) -> list[ChatResponse]:
    rows = db.execute(
        select(QueryHistoryORM)
        .where((QueryHistoryORM.conversation_id == conversation_id) | (QueryHistoryORM.id == conversation_id))
        .order_by(QueryHistoryORM.created_at)
    ).scalars().all()
    return [_row_to_chat_response(r) for r in rows]


def delete_conversation(
    db: Session,
    conversation_id: str,
    current_user: UserORM | None = None,
) -> int:
    rows = db.execute(
        select(QueryHistoryORM).where(
            (QueryHistoryORM.conversation_id == conversation_id) | (QueryHistoryORM.id == conversation_id)
        )
    ).scalars().all()
    if not rows:
        return 0

    if current_user is not None and current_user.role != "admin":
        if any(r.user_id is not None and r.user_id != current_user.id for r in rows):
            raise PermissionError("Bạn không có quyền xóa cuộc hội thoại của người dùng khác.")

    req_ids = [r.id for r in rows]
    db.query(CitationRecordORM).filter(CitationRecordORM.request_id.in_(req_ids)).delete(synchronize_session=False)
    db.query(AgentRunLogORM).filter(AgentRunLogORM.request_id.in_(req_ids)).delete(synchronize_session=False)
    db.query(ChatFeedbackORM).filter(ChatFeedbackORM.request_id.in_(req_ids)).delete(synchronize_session=False)
    for r in rows:
        db.delete(r)
    db.commit()
    return len(rows)


def get_history_detail(db: Session, item_id: str) -> ChatResponse | None:
    row = db.get(QueryHistoryORM, item_id)
    if row is None:
        return None
    return _row_to_chat_response(row)


def delete_history_item(
    db: Session,
    item_id: str,
    current_user: UserORM | None = None,
) -> bool:
    row = db.get(QueryHistoryORM, item_id)
    if row is None:
        return False
    if current_user is not None and current_user.role != "admin":
        if row.user_id is not None and row.user_id != current_user.id:
            raise PermissionError("Bạn không có quyền xóa bản ghi lịch sử của người dùng khác.")
    db.query(CitationRecordORM).filter(CitationRecordORM.request_id == item_id).delete()
    db.query(AgentRunLogORM).filter(AgentRunLogORM.request_id == item_id).delete()
    db.query(ChatFeedbackORM).filter(ChatFeedbackORM.request_id == item_id).delete()
    db.delete(row)
    db.commit()
    return True


def clear_all_history(db: Session, current_user: UserORM | None = None) -> int:
    if current_user is not None and current_user.role != "admin":
        rows = db.execute(
            select(QueryHistoryORM).where(
                (QueryHistoryORM.user_id == current_user.id) | (QueryHistoryORM.user_id.is_(None))
            )
        ).scalars().all()
        req_ids = [r.id for r in rows]
        if req_ids:
            db.query(CitationRecordORM).filter(CitationRecordORM.request_id.in_(req_ids)).delete(synchronize_session=False)
            db.query(AgentRunLogORM).filter(AgentRunLogORM.request_id.in_(req_ids)).delete(synchronize_session=False)
            db.query(ChatFeedbackORM).filter(ChatFeedbackORM.request_id.in_(req_ids)).delete(synchronize_session=False)
            for r in rows:
                db.delete(r)
            db.commit()
        return len(rows)

    count = db.query(QueryHistoryORM).count()
    db.query(CitationRecordORM).delete()
    db.query(AgentRunLogORM).delete()
    db.query(ChatFeedbackORM).delete()
    db.query(QueryHistoryORM).delete()
    db.commit()
    return count


def submit_chat_feedback(
    db: Session,
    request_id: str,
    payload: ChatFeedbackRequest,
    current_user: UserORM | None = None,
) -> ChatFeedbackResponse | None:
    row = db.get(QueryHistoryORM, request_id)
    if row is None:
        return None
    fb = ChatFeedbackORM(
        id=f"FB-{uuid.uuid4().hex[:10].upper()}",
        request_id=request_id,
        user_id=current_user.id if current_user else None,
        rating=payload.rating,
        helpful=payload.helpful,
        comment=payload.comment,
        created_at=datetime.now(timezone.utc),
    )
    db.add(fb)
    db.commit()
    return ChatFeedbackResponse(
        id=fb.id,
        request_id=fb.request_id,
        rating=fb.rating,
        helpful=fb.helpful,
        comment=fb.comment,
        created_at=fb.created_at,
    )
