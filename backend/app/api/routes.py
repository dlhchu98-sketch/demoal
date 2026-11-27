from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import desc, select, text
from sqlalchemy.orm import Session

from backend.app.api.routers.admin import router as admin_router
from backend.app.api.routers.auth import router as auth_router
from backend.app.api.routers.saved import router as saved_router
from backend.app.core.config import get_settings
from backend.app.core.database import AgentRunLogORM, CitationRecordORM, UserORM, get_db
from backend.app.core.security import get_current_user_optional
from backend.app.schemas.legal import (
    AgentAnalyzeRequest,
    AgentAnalyzeResponse,
    AgentRunLogItem,
    ChatFeedbackRequest,
    ChatFeedbackResponse,
    ChatRequest,
    ChatResponse,
    CitationLogItem,
    CitationReportResponse,
    CitationValidateRequest,
    CitationValidateResponse,
    ConversationSummary,
    DocumentsResponse,
    EvaluationResultsResponse,
    EvaluationRunRequest,
    FolderUploadFileItem,
    FolderUploadResponse,
    HistorySummary,
    IngestionFileResult,
    IngestRequest,
    LegalDocumentChunksResponse,
    LegalDocumentCreateTextRequest,
    LegalDocumentDetailResponse,
    LegalDocumentListResponse,
    LegalDocumentsStatsResponse,
    LegalDocumentSummary,
    LegalDocumentUpdateRequest,
    ModeUpdateRequest,
    ProcessingStepItem,
    QuestionCategory,
    QuestionsResponse,
    RagSearchRequest,
    RagSearchResponse,
    ScanAndIngestResponse,
    ScanRequest,
    ServiceHealthItem,
    StatisticsResponse,
    SystemStatusResponse,
)
from backend.app.services.admin_service import log_activity
from backend.app.services.ai_integration import (
    analyze_question_structured,
    search_rag_corpus,
    validate_citation_against_corpus,
)
from backend.app.services.chat_service import (
    clear_all_history,
    delete_conversation,
    delete_history_item,
    get_conversation_messages,
    get_history_detail,
    list_conversations,
    list_history,
    process_chat,
    runtime_state,
    submit_chat_feedback,
)
from backend.app.services.data_service import data_service
from backend.app.services.document_converter import (
    DocumentConversionError,
    convert_uploaded_document,
    should_ignore_folder_file,
)
from backend.app.services.legal_ingestion_service import legal_ingestion_service
from rag.pipeline import LegalDocumentParseError
from rag.retriever import QdrantConnectionError

router = APIRouter()
router.include_router(auth_router)
router.include_router(saved_router)
router.include_router(admin_router)


@router.get("/health", tags=["System"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/api/status", response_model=SystemStatusResponse, tags=["System"])
def get_system_status(db: Session = Depends(get_db)) -> SystemStatusResponse:
    settings = get_settings()
    mode = runtime_state.app_mode

    try:
        db.execute(text("SELECT 1"))
        db_kind = "PostgreSQL" if settings.database_url.startswith("postgres") else "SQLite (local fallback)"
        db_item = ServiceHealthItem(name="Database", status="online", detail=f"Đang hoạt động ({db_kind})")
    except Exception as exc:
        db_item = ServiceHealthItem(name="Database", status="offline", detail=str(exc))

    retriever = legal_ingestion_service.get_retriever()
    qdrant_connected, qdrant_conn_detail = retriever.check_connection()
    qdrant_has_vectors, qdrant_vec_detail = retriever.is_available()
    qdrant_item = ServiceHealthItem(
        name="Qdrant Vector DB",
        status="online" if qdrant_connected else ("demo" if mode == "demo" else "offline"),
        detail=qdrant_vec_detail if qdrant_has_vectors else qdrant_conn_detail,
    )

    llm_configured = bool(settings.llm_api_key.strip())
    llm_item = ServiceHealthItem(
        name="LLM Tiếng Việt",
        status="online" if llm_configured else ("demo" if mode == "demo" else "not_configured"),
        detail=(
            f"Đã cấu hình model {runtime_state.llm_model}"
            if llm_configured
            else "Chưa cấu hình LLM_API_KEY trong biến môi trường (.env)"
        ),
    )

    loaded_q, _, _ = data_service.get_categories()
    docs = legal_ingestion_service.list_documents(db)

    return SystemStatusResponse(
        app_name=settings.app_name,
        app_mode=mode,
        database=db_item,
        qdrant=qdrant_item,
        llm=llm_item,
        rag=ServiceHealthItem(
            name="RAG Pipeline",
            status="online" if qdrant_has_vectors else ("online" if qdrant_connected else "demo"),
            detail=(
                "Sẵn sàng truy xuất chunk pháp luật từ Qdrant."
                if qdrant_has_vectors
                else "Pipeline nạp & embedding đã sẵn sàng; cần nạp văn bản thật từ data/legal_documents/."
            ),
        ),
        agent=ServiceHealthItem(
            name="LangGraph Agent",
            status="online" if (mode == "live" and qdrant_has_vectors) else "demo",
            detail=f"Luồng phân rã vấn đề + self-correction (tối đa {runtime_state.max_self_correction_attempts} lượt).",
        ),
        citation_validator=ServiceHealthItem(
            name="Citation Validator",
            status="online",
            detail="Rule-based 6 tiêu chí + LLM hook đã sẵn sàng (không tự gán PASS cho nguồn giả lập).",
        ),
        question_bank_loaded=loaded_q,
        legal_corpus_loaded=docs.loaded,
    )


@router.put("/api/settings/mode", tags=["System"])
def update_app_mode(
    payload: ModeUpdateRequest,
    current_user: UserORM | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    runtime_state.app_mode = payload.app_mode
    log_activity(
        db,
        user=current_user,
        action="update_mode",
        resource="system",
        detail=f"Chuyển chế độ sang {runtime_state.app_mode.upper()}",
        commit=True,
    )
    return {
        "app_mode": runtime_state.app_mode,
        "message": f"Đã chuyển chế độ hệ thống sang {runtime_state.app_mode.upper()}.",
    }


# ---------------------------------------------------------------------------
# Chat, Multi-turn Conversations & History
# ---------------------------------------------------------------------------
@router.post("/api/chat", response_model=ChatResponse, tags=["Legal Chat"])
def chat_endpoint(
    payload: ChatRequest,
    current_user: UserORM | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> ChatResponse:
    return process_chat(db, payload, current_user=current_user)


@router.get("/api/chat/conversations", response_model=list[ConversationSummary], tags=["Legal Chat"])
def get_conversations(
    search: str | None = Query(default=None),
    current_user: UserORM | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> list[ConversationSummary]:
    return list_conversations(db, search=search, current_user=current_user)


@router.get("/api/chat/conversations/{conversation_id}", response_model=list[ChatResponse], tags=["Legal Chat"])
def get_conversation_detail(
    conversation_id: str,
    db: Session = Depends(get_db),
) -> list[ChatResponse]:
    items = get_conversation_messages(db, conversation_id)
    if not items:
        raise HTTPException(status_code=404, detail="Không tìm thấy cuộc hội thoại.")
    return items


@router.delete("/api/chat/conversations/{conversation_id}", tags=["Legal Chat"])
def remove_conversation(
    conversation_id: str,
    current_user: UserORM | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> dict[str, int | str]:
    try:
        deleted = delete_conversation(db, conversation_id, current_user=current_user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Không tìm thấy cuộc hội thoại cần xóa.")
    return {"status": "deleted", "conversation_id": conversation_id, "deleted_messages": deleted}


@router.post("/api/chat/{request_id}/feedback", response_model=ChatFeedbackResponse, tags=["Legal Chat"])
def submit_feedback_endpoint(
    request_id: str,
    payload: ChatFeedbackRequest,
    current_user: UserORM | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> ChatFeedbackResponse:
    res = submit_chat_feedback(db, request_id, payload, current_user=current_user)
    if res is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy lượt hỏi đáp cần đánh giá.")
    return res


@router.get("/api/history", response_model=list[HistorySummary], tags=["History"])
def get_history_list(
    search: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    current_user: UserORM | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> list[HistorySummary]:
    return list_history(db, search=search, limit=limit, current_user=current_user)


@router.get("/api/history/{history_id}", response_model=ChatResponse, tags=["History"])
def get_history_item(history_id: str, db: Session = Depends(get_db)) -> ChatResponse:
    item = get_history_detail(db, history_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy bản ghi lịch sử tra cứu.")
    return item


@router.delete("/api/history/{history_id}", tags=["History"])
def remove_history_item(
    history_id: str,
    current_user: UserORM | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    try:
        deleted = delete_history_item(db, history_id, current_user=current_user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Không tìm thấy bản ghi cần xóa.")
    return {"status": "deleted", "id": history_id}


@router.delete("/api/history", tags=["History"])
def remove_all_history(
    current_user: UserORM | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> dict[str, int | str]:
    count = clear_all_history(db, current_user=current_user)
    return {"status": "cleared", "deleted_count": count}


# ---------------------------------------------------------------------------
# Questions Bank (QUESTION DATASET — never indexed into Qdrant)
# ---------------------------------------------------------------------------
@router.get("/api/questions", response_model=QuestionsResponse, tags=["Questions"])
def get_questions(
    search: str | None = Query(default=None),
    category_id: int | None = Query(default=None),
    domain: str | None = Query(default=None),
    difficulty: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=5, le=100),
) -> QuestionsResponse:
    return data_service.get_questions(
        search=search,
        category_id=category_id,
        domain=domain,
        difficulty=difficulty,
        page=page,
        page_size=page_size,
    )


@router.get("/api/questions/categories", tags=["Questions"])
def get_question_categories() -> dict:
    loaded, categories, source_file = data_service.get_categories()
    domains = sorted({c.domain for c in categories})
    return {
        "loaded": loaded,
        "source_file": source_file,
        "expected_categories": len(categories) if loaded else 17,
        "total_domains": len(domains),
        "domains": domains,
        "total_categories": len(categories),
        "items": [QuestionCategory.model_validate(c).model_dump() for c in categories],
    }


@router.post("/api/questions/upload", response_model=QuestionsResponse, tags=["Questions"])
async def upload_question_docx(file: UploadFile = File(...)) -> QuestionsResponse:
    try:
        content = await file.read()
        return data_service.save_uploaded_question_docx(file.filename or "Bo_cau_hoi_phap_luat.docx", content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Legal Documents Management & Ingestion
# ---------------------------------------------------------------------------
@router.get("/api/legal-documents", response_model=LegalDocumentListResponse, tags=["Legal Documents"])
def list_legal_documents(
    search: str | None = Query(default=None),
    document_type: str | None = Query(default=None),
    issuing_authority: str | None = Query(default=None),
    status: str | None = Query(default=None),
    qdrant_sync_status: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> LegalDocumentListResponse:
    return legal_ingestion_service.list_documents(
        db,
        search=search,
        document_type=document_type,
        issuing_authority=issuing_authority,
        status=status,
        qdrant_sync_status=qdrant_sync_status,
    )


@router.get("/api/legal-documents/stats", response_model=LegalDocumentsStatsResponse, tags=["Legal Documents"])
def get_legal_documents_stats(db: Session = Depends(get_db)) -> LegalDocumentsStatsResponse:
    return legal_ingestion_service.get_stats(db)


@router.post("/api/legal-documents/scan", response_model=ScanAndIngestResponse, tags=["Legal Documents"])
def scan_legal_documents_dir(
    payload: ScanRequest | None = Body(default=None),
    db: Session = Depends(get_db),
) -> ScanAndIngestResponse:
    req = payload or ScanRequest()
    return legal_ingestion_service.scan_directory(
        db,
        auto_ingest=req.auto_ingest,
        allow_update=req.allow_update,
    )


@router.post("/api/legal-documents/ingest", response_model=ScanAndIngestResponse, tags=["Legal Documents"])
def ingest_legal_documents(
    payload: IngestRequest | None = Body(default=None),
    db: Session = Depends(get_db),
) -> ScanAndIngestResponse:
    req = payload or IngestRequest()
    if req.file_path:
        try:
            target = legal_ingestion_service.resolve_target_file(req.file_path)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        res = legal_ingestion_service.ingest_file(db, target, allow_update=req.allow_update)
        return ScanAndIngestResponse(
            directory=legal_ingestion_service._normalize_rel_path(legal_ingestion_service.documents_dir),
            total_files_found=1,
            ingested_count=1 if res.action == "ingested" else 0,
            updated_count=1 if res.action == "updated" else 0,
            skipped_duplicate_count=1 if res.action == "skipped_duplicate" else 0,
            conflict_count=1 if res.action == "conflict_requires_update" else 0,
            error_count=1 if res.status == "error" else 0,
            results=[res],
            message=res.message,
        )

    return legal_ingestion_service.scan_directory(
        db,
        auto_ingest=True,
        allow_update=req.allow_update,
    )


@router.post("/api/legal-documents/upload", response_model=IngestionFileResult, tags=["Legal Documents"])
async def upload_legal_document_file(
    file: UploadFile = File(...),
    allow_update: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> IngestionFileResult:
    """
    Tải lên một tệp văn bản pháp luật (.doc, .docx, .pdf, .txt, .json).
    Tự động chuyển đổi .doc/.docx/.pdf sang UTF-8 .txt chuẩn hóa trước khi nạp DB & Qdrant.
    """
    try:
        content = await file.read()
        converted = convert_uploaded_document(file.filename or "legal_document.txt", content)
        res = legal_ingestion_service.save_uploaded_legal_file(
            db,
            filename=converted.target_filename,
            content=converted.target_bytes,
            allow_update=allow_update,
        )
        if converted.converted and res.status == "success":
            res.message = f"[Đã tự chuyển đổi {converted.original_ext} → .txt] {res.message}"
        return res
    except (DocumentConversionError, LegalDocumentParseError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/legal-documents/upload-folder", response_model=FolderUploadResponse, tags=["Legal Documents"])
async def upload_legal_documents_folder(
    files: list[UploadFile] = File(...),
    allow_update: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> FolderUploadResponse:
    """
    Upload cả thư mục gốc chứa nhiều loại tệp (.doc, .docx, .pdf, .txt, .json và tệp khác):
    - Tự động lọc bỏ tệp rác/tệp tạm (~$*, Thumbs.db, ảnh, bảng tính...).
    - Tự động trích xuất và chuẩn hóa .doc / .docx / .pdf sang .txt UTF-8.
    - Nạp vào DB, chống trùng SHA-256 và đồng bộ vector lên Qdrant trong một lượt bấm duy nhất.
    """
    items: list[FolderUploadFileItem] = []
    supported_count = 0
    filtered_out_count = 0
    converted_count = 0
    ingested_count = 0
    updated_count = 0
    skipped_dup_count = 0
    conflict_count = 0
    error_count = 0

    for up in files:
        raw_name = up.filename or "unknown"
        ext = Path(raw_name.replace("\\", "/")).suffix.lower()

        ignore, ignore_reason = should_ignore_folder_file(raw_name)
        if ignore:
            filtered_out_count += 1
            items.append(
                FolderUploadFileItem(
                    original_filename=raw_name,
                    original_ext=ext,
                    action="filtered_out",
                    status="skipped",
                    message=ignore_reason,
                )
            )
            continue

        supported_count += 1
        try:
            content = await up.read()
            conv = convert_uploaded_document(raw_name, content)
            if conv.converted:
                converted_count += 1

            ing = legal_ingestion_service.save_uploaded_legal_file(
                db,
                filename=conv.target_filename,
                content=conv.target_bytes,
                allow_update=allow_update,
            )

            if ing.action == "ingested":
                ingested_count += 1
            elif ing.action == "updated":
                updated_count += 1
            elif ing.action == "skipped_duplicate":
                skipped_dup_count += 1
            elif ing.action == "conflict_requires_update":
                conflict_count += 1
            elif ing.status == "error":
                error_count += 1

            prefix = f"[Tự chuyển {conv.original_ext} → .txt] " if conv.converted else ""
            items.append(
                FolderUploadFileItem(
                    original_filename=raw_name,
                    target_filename=conv.target_filename,
                    original_ext=conv.original_ext,
                    converter_used=conv.converter_used,
                    converted=conv.converted,
                    document_id=ing.document_id,
                    title=ing.title,
                    action=ing.action if ing.action != "detected_new" else "ingested",  # type: ignore[arg-type]
                    status=ing.status,
                    message=f"{prefix}{ing.message}",
                    chunk_count=ing.chunk_count,
                    qdrant_sync_status=ing.qdrant_sync_status,
                )
            )
        except (DocumentConversionError, LegalDocumentParseError, Exception) as exc:
            error_count += 1
            items.append(
                FolderUploadFileItem(
                    original_filename=raw_name,
                    original_ext=ext,
                    action="error",
                    status="error",
                    message=str(exc),
                )
            )

    summary = (
        f"Đã xử lý {len(files)} tệp trong thư mục: "
        f"lọc hợp lệ {supported_count} (tự chuyển đổi {converted_count} tệp .doc/.docx/.pdf), "
        f"tự bỏ qua {filtered_out_count} tệp không phải văn bản | "
        f"Nạp mới {ingested_count}, cập nhật {updated_count}, trùng lặp {skipped_dup_count}, "
        f"xung đột {conflict_count}, lỗi {error_count}."
    )
    return FolderUploadResponse(
        total_received=len(files),
        supported_count=supported_count,
        filtered_out_count=filtered_out_count,
        converted_count=converted_count,
        ingested_count=ingested_count,
        updated_count=updated_count,
        skipped_duplicate_count=skipped_dup_count,
        conflict_count=conflict_count,
        error_count=error_count,
        items=items,
        message=summary,
    )


@router.post("/api/legal-documents/create", response_model=IngestionFileResult, tags=["Legal Documents"])
def create_legal_document_json(
    payload: LegalDocumentCreateTextRequest,
    db: Session = Depends(get_db),
) -> IngestionFileResult:
    """Cho phép quản trị viên thêm trực tiếp văn bản pháp luật có metadata chuẩn dưới dạng JSON và đồng bộ Qdrant."""
    safe_stem = Path(payload.filename).stem
    target_filename = f"{safe_stem}.json"
    doc_json = {
        "title": payload.title,
        "document_number": payload.document_number,
        "document_type": payload.document_type,
        "issuing_authority": payload.issuing_authority,
        "issue_date": payload.issue_date,
        "effective_date": payload.effective_date,
        "expiry_date": payload.expiry_date,
        "status": payload.status,
        "source": payload.source,
        "content": payload.content,
    }
    raw_bytes = json.dumps(doc_json, ensure_ascii=False, indent=2).encode("utf-8")
    try:
        return legal_ingestion_service.save_uploaded_legal_file(
            db,
            filename=target_filename,
            content=raw_bytes,
            allow_update=payload.allow_update,
        )
    except LegalDocumentParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/legal-documents/{document_id}", response_model=LegalDocumentDetailResponse, tags=["Legal Documents"])
def get_legal_document_detail(
    document_id: str,
    db: Session = Depends(get_db),
) -> LegalDocumentDetailResponse:
    detail = legal_ingestion_service.get_document_detail(db, document_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy văn bản pháp luật.")
    return detail


@router.put("/api/legal-documents/{document_id}", response_model=LegalDocumentSummary, tags=["Legal Documents"])
def update_legal_document_metadata(
    document_id: str,
    payload: LegalDocumentUpdateRequest,
    db: Session = Depends(get_db),
) -> LegalDocumentSummary:
    updated = legal_ingestion_service.update_document_metadata(
        db,
        document_id,
        payload.model_dump(exclude_none=True),
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy văn bản pháp luật.")
    return updated


@router.post("/api/legal-documents/{document_id}/reingest", response_model=IngestionFileResult, tags=["Legal Documents"])
def reingest_legal_document(
    document_id: str,
    db: Session = Depends(get_db),
) -> IngestionFileResult:
    res = legal_ingestion_service.reingest_document(db, document_id)
    if res is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy văn bản pháp luật.")
    return res


@router.get(
    "/api/legal-documents/{document_id}/chunks",
    response_model=LegalDocumentChunksResponse,
    tags=["Legal Documents"],
)
def get_legal_document_chunks(
    document_id: str,
    search: str | None = Query(default=None),
    article: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> LegalDocumentChunksResponse:
    res = legal_ingestion_service.get_document_chunks(db, document_id, search=search, article=article)
    if res is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy văn bản pháp luật.")
    return res


@router.delete("/api/legal-documents/{document_id}", tags=["Legal Documents"])
def delete_legal_document(
    document_id: str,
    delete_source_file: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> dict:
    try:
        res = legal_ingestion_service.delete_document(
            db,
            document_id,
            delete_source_file=delete_source_file,
        )
    except QdrantConnectionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if res is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy văn bản pháp luật cần xóa.")
    return res


# Endpoint cũ giữ nguyên tương thích ngược
@router.get("/api/documents", response_model=DocumentsResponse, tags=["Documents"])
def get_documents(
    search: str | None = Query(default=None),
    doc_type: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> DocumentsResponse:
    return data_service.get_documents(db=db, search=search, doc_type=doc_type)


# ---------------------------------------------------------------------------
# RAG Endpoints (Tích hợp module của Nguyễn Thanh Hiền)
# ---------------------------------------------------------------------------
@router.post("/api/rag/search", response_model=RagSearchResponse, tags=["RAG"])
def rag_search(payload: RagSearchRequest) -> RagSearchResponse:
    retriever = legal_ingestion_service.get_retriever()
    return search_rag_corpus(
        retriever=retriever,
        query=payload.query,
        top_k=payload.top_k,
        score_threshold=payload.score_threshold,
    )


@router.post("/api/rag/ingest", response_model=ScanAndIngestResponse, tags=["RAG"])
def rag_ingest(
    payload: IngestRequest | None = Body(default=None),
    db: Session = Depends(get_db),
) -> ScanAndIngestResponse:
    return ingest_legal_documents(payload=payload, db=db)


@router.get("/api/rag/status", response_model=LegalDocumentsStatsResponse, tags=["RAG"])
def rag_status(db: Session = Depends(get_db)) -> LegalDocumentsStatsResponse:
    return legal_ingestion_service.get_stats(db)


# ---------------------------------------------------------------------------
# Agent Endpoints (Tích hợp module của Đặng Thị Ngọc Ánh)
# ---------------------------------------------------------------------------
@router.post("/api/agent/analyze", response_model=AgentAnalyzeResponse, tags=["Agent"])
def agent_analyze(payload: AgentAnalyzeRequest) -> AgentAnalyzeResponse:
    return analyze_question_structured(payload.question)


@router.get("/api/agent/status", tags=["Agent"])
def agent_status(db: Session = Depends(get_db)) -> dict:
    total_runs = db.query(AgentRunLogORM).count()
    self_corr_runs = db.query(AgentRunLogORM).filter(AgentRunLogORM.self_correction_attempts > 0).count()
    error_runs = db.query(AgentRunLogORM).filter(AgentRunLogORM.error_message.is_not(None)).count()
    retriever = legal_ingestion_service.get_retriever()
    q_avail, q_detail = retriever.is_available()
    return {
        "status": "online" if (runtime_state.app_mode == "live" and q_avail) else "demo",
        "app_mode": runtime_state.app_mode,
        "max_self_correction_attempts": runtime_state.max_self_correction_attempts,
        "qdrant_ready": q_avail,
        "qdrant_detail": q_detail,
        "total_runs": total_runs,
        "self_correction_runs": self_corr_runs,
        "error_runs": error_runs,
        "pipeline_stages": [
            "Query Analysis",
            "Legal Issue Decomposition",
            "Retrieval",
            "Legal Analysis",
            "Citation Validation",
            "Self-Correction",
        ],
    }


@router.get("/api/agent/logs", response_model=list[AgentRunLogItem], tags=["Agent"])
def agent_logs(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[AgentRunLogItem]:
    rows = db.execute(select(AgentRunLogORM).order_by(desc(AgentRunLogORM.created_at)).limit(limit)).scalars().all()
    items: list[AgentRunLogItem] = []
    for r in rows:
        raw_stages = json.loads(r.stages_json or "[]")
        items.append(
            AgentRunLogItem(
                id=r.id,
                request_id=r.request_id,
                conversation_id=r.conversation_id,
                question=r.question,
                overall_status=r.overall_status,
                self_correction_attempts=r.self_correction_attempts,
                error_message=r.error_message,
                latency_ms=r.latency_ms,
                is_mock=r.is_mock,
                stages=[ProcessingStepItem(**s) for s in raw_stages],
                created_at=r.created_at,
            )
        )
    return items


# ---------------------------------------------------------------------------
# Citation Validator Endpoints
# ---------------------------------------------------------------------------
@router.post("/api/citations/validate", response_model=CitationValidateResponse, tags=["Citations"])
def validate_citation_endpoint(
    payload: CitationValidateRequest,
    db: Session = Depends(get_db),
) -> CitationValidateResponse:
    return validate_citation_against_corpus(db, payload)


@router.get("/api/citations/report", response_model=CitationReportResponse, tags=["Citations"])
def get_citation_report(db: Session = Depends(get_db)) -> CitationReportResponse:
    rows = db.execute(select(CitationRecordORM)).scalars().all()
    total = len(rows)
    valid = sum(1 for r in rows if r.validation_status == "PASS")
    invalid = sum(1 for r in rows if r.validation_status == "FAIL")
    insufficient = sum(1 for r in rows if r.validation_status == "UNVERIFIED")
    mock_cnt = sum(1 for r in rows if r.is_mock)
    live_cnt = total - mock_cnt

    agent_rows = db.execute(select(AgentRunLogORM)).scalars().all()
    sc_runs = sum(1 for a in agent_rows if a.self_correction_attempts > 0)
    sc_total = sum(a.self_correction_attempts for a in agent_rows)

    checked_decided = valid + invalid
    pass_rate = round((valid / checked_decided) * 100, 1) if checked_decided > 0 else None
    return CitationReportResponse(
        total_checked=total,
        valid_count=valid,
        invalid_count=invalid,
        insufficient_count=insufficient,
        self_correction_runs=sc_runs,
        total_self_correction_attempts=sc_total,
        pass_rate=pass_rate,
        mock_count=mock_cnt,
        live_count=live_cnt,
    )


@router.get("/api/citations", response_model=list[CitationLogItem], tags=["Citations"])
def get_citations(
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[CitationLogItem]:
    return data_service.get_citations(db, status=status, limit=limit)


@router.get("/api/citations/{citation_id}", response_model=CitationLogItem, tags=["Citations"])
def get_citation_detail(
    citation_id: str,
    db: Session = Depends(get_db),
) -> CitationLogItem:
    row = db.get(CitationRecordORM, citation_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy bản ghi trích dẫn.")
    return CitationLogItem(
        id=row.id,
        request_id=row.request_id,
        question=row.question,
        claim=row.claim,
        document_name=row.document_name,
        document_number=row.document_number,
        article=row.article,
        clause=row.clause,
        point=row.point,
        evidence=row.evidence,
        validation_status=row.validation_status,  # type: ignore[arg-type]
        validation_reason=row.validation_reason,
        relevance_score=row.relevance_score,
        is_mock=row.is_mock,
        created_at=row.created_at,
    )


# ---------------------------------------------------------------------------
# Statistics & Evaluation
# ---------------------------------------------------------------------------
@router.get("/api/statistics", response_model=StatisticsResponse, tags=["Statistics"])
def get_statistics(db: Session = Depends(get_db)) -> StatisticsResponse:
    return data_service.get_statistics(db, current_mode=runtime_state.app_mode)


@router.post("/api/evaluation/run", response_model=EvaluationResultsResponse, tags=["Evaluation"])
def run_evaluation(
    payload: EvaluationRunRequest,
    db: Session = Depends(get_db),
) -> EvaluationResultsResponse:
    return data_service.run_evaluation(db, payload=payload, current_mode=runtime_state.app_mode)


@router.get("/api/evaluation/results", response_model=EvaluationResultsResponse, tags=["Evaluation"])
def get_evaluation_results(db: Session = Depends(get_db)) -> EvaluationResultsResponse:
    return data_service.get_latest_evaluation(db, current_mode=runtime_state.app_mode)
