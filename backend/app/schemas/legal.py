from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator


CitationStatus = Literal["PASS", "FAIL", "UNVERIFIED"]
AppMode = Literal["demo", "live"]
QdrantSyncStatus = Literal["synced", "pending", "failed", "not_synced"]
UserRole = Literal["user", "admin"]
SavedItemType = Literal["document", "clause", "answer"]


# ---------------------------------------------------------------------------
# Authentication & User Schemas
# ---------------------------------------------------------------------------
class UserRegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    email: str = Field(..., min_length=5, max_length=255)
    full_name: str = Field(..., min_length=2, max_length=255)
    password: str = Field(..., min_length=6, max_length=128)

    @field_validator("username", "email", "full_name")
    @classmethod
    def strip_text(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Trường thông tin không được để trống.")
        return s

    @field_validator("email")
    @classmethod
    def validate_email_basic(cls, v: str) -> str:
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Địa chỉ email không hợp lệ.")
        return v.lower()


class UserLoginRequest(BaseModel):
    identifier: str = Field(..., min_length=2, max_length=255, description="Email hoặc tên đăng nhập")
    password: str = Field(..., min_length=1, max_length=128)


class UserProfile(BaseModel):
    id: str
    username: str
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None = None


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserProfile


class UserUpdateProfileRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=255)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=6, max_length=128)


class AdminUserUpdateRoleRequest(BaseModel):
    role: UserRole


class AdminUserUpdateStatusRequest(BaseModel):
    is_active: bool


class ActivityLogItem(BaseModel):
    id: str
    user_id: str | None = None
    username: str
    action: str
    resource: str
    detail: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Chat, Agent 7-step Trace, Citation & Validation Contract (Section 5.1)
# ---------------------------------------------------------------------------
class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000, description="Câu hỏi pháp luật bằng tiếng Việt")
    conversation_id: str | None = Field(default=None, description="Mã hội thoại nếu tiếp nối")
    simulate_self_correction: bool = Field(
        default=False,
        description="Trong DEMO mode, cho phép mô phỏng quy trình FAIL -> tự điều chỉnh -> kiểm tra lại",
    )

    @field_validator("question")
    @classmethod
    def validate_question_not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Câu hỏi không được để trống.")
        return cleaned


class LegalIssueItem(BaseModel):
    issue: str
    legal_domain: str | None = None
    sub_query: str | None = None


class CitationChecks(BaseModel):
    document_exists: bool | None = None
    number_valid: bool | None = None
    structure_exists: bool | None = None
    quote_matches: bool | None = None
    supports_claim: bool | None = None
    validity_verified: bool | None = None


class CitationItem(BaseModel):
    claim: str | None = None
    chunk_id: str | None = None
    document_id: str | None = None
    document_name: str
    document_title: str | None = None
    document_number: str | None = None
    chapter: str | None = None
    article: str | None = None
    clause: str | None = None
    point: str | None = None
    evidence: str
    quoted_text: str | None = None
    source: str | None = None
    source_url: str | None = None
    effective_date: str | None = None
    validity_status: str | None = None
    relevance_score: float | None = None
    validation_status: CitationStatus = "UNVERIFIED"
    support_status: Literal["SUPPORTED", "UNSUPPORTED", "CONTRADICTED", "INSUFFICIENT_EVIDENCE"] = "INSUFFICIENT_EVIDENCE"
    validation_reason: str | None = None
    checks: CitationChecks | None = None


class ValidationDetailItem(BaseModel):
    citation_index: int
    document_title: str
    document_number: str | None = None
    location: str
    validation_status: CitationStatus
    support_status: str
    validity_status: str
    reason: str
    checks: CitationChecks


class SelfCorrectionStep(BaseModel):
    attempt: int
    initial_status: CitationStatus
    action: str
    resulting_status: CitationStatus
    detail: str


class SelfCorrectionInfo(BaseModel):
    attempts: int = 0
    performed: bool = False
    max_attempts: int = 2
    steps: list[SelfCorrectionStep] = Field(default_factory=list)


class PipelineTraceStep(BaseModel):
    stage: str
    label: str
    status: Literal["done", "warning", "skipped", "error"]
    detail: str
    duration_ms: int | None = None


class ProcessingStepItem(BaseModel):
    step_number: int
    stage: str
    label: str
    status: Literal["completed", "warning", "error", "pending"]
    detail: str
    duration_ms: int | None = None


class ProcessingStatusInfo(BaseModel):
    current_step: int = 7
    total_steps: int = 7
    overall_state: Literal["completed", "completed_with_warnings", "insufficient_evidence", "error"] = "completed_with_warnings"
    steps: list[ProcessingStepItem] = Field(default_factory=list)


class ChatResponse(BaseModel):
    request_id: str
    conversation_id: str | None = None
    question: str
    answer: str
    conclusion: str = ""
    explanation: str = ""
    limitations: list[str] = Field(default_factory=list)
    analysis: list[LegalIssueItem] = Field(default_factory=list)
    citations: list[CitationItem] = Field(default_factory=list)
    citation_status: CitationStatus = "UNVERIFIED"
    verification_label: str = "Chưa đủ bằng chứng"
    validation_details: list[ValidationDetailItem] = Field(default_factory=list)
    self_correction: SelfCorrectionInfo = Field(default_factory=SelfCorrectionInfo)
    pipeline_trace: list[PipelineTraceStep] = Field(default_factory=list)
    processing_status: ProcessingStatusInfo = Field(default_factory=ProcessingStatusInfo)
    disclaimer: str = (
        "Lưu ý: Hệ thống chỉ hỗ trợ tra cứu, tổng hợp và dẫn nguồn pháp luật, không thay thế tư vấn pháp lý chính thức."
    )
    is_mock: bool = True
    app_mode: AppMode = "demo"
    processing_time_ms: int = 0
    created_at: datetime | None = None


class ChatFeedbackRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    helpful: bool = True
    comment: str | None = Field(default=None, max_length=1000)


class ChatFeedbackResponse(BaseModel):
    id: str
    request_id: str
    rating: int
    helpful: bool
    comment: str | None = None
    created_at: datetime


class ConversationSummary(BaseModel):
    conversation_id: str
    title: str
    last_question: str
    last_answer_preview: str
    message_count: int
    latest_citation_status: CitationStatus
    is_mock: bool
    updated_at: datetime


class HistorySummary(BaseModel):
    id: str
    conversation_id: str | None = None
    question: str
    answer_preview: str
    citation_status: CitationStatus
    citations_count: int
    self_correction_performed: bool
    is_mock: bool
    app_mode: str
    processing_time_ms: int
    created_at: datetime


# ---------------------------------------------------------------------------
# Saved Items (User Portal Page 7)
# ---------------------------------------------------------------------------
class SavedItemCreateRequest(BaseModel):
    item_type: SavedItemType
    target_id: str = Field(..., min_length=1, max_length=128)
    title: str = Field(..., min_length=1, max_length=512)
    subtitle: str | None = Field(default=None, max_length=512)
    content: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class SavedItemResponse(BaseModel):
    id: str
    item_type: SavedItemType
    target_id: str
    title: str
    subtitle: str | None = None
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


# ---------------------------------------------------------------------------
# Question Bank (QUESTION DATASET — never indexed into Qdrant)
# ---------------------------------------------------------------------------
class QuestionItem(BaseModel):
    id: str
    question_code: str | None = None
    domain: str = "Pháp luật Việt Nam"
    category_id: int
    category_name: str
    difficulty: str = "Medium"
    question: str
    source_file: str


class QuestionCategory(BaseModel):
    id: int
    name: str
    domain: str = "Pháp luật Việt Nam"
    question_count: int


class QuestionsResponse(BaseModel):
    loaded: bool
    source_file: str | None = None
    expected_categories: int = 17
    total_domains: int = 0
    total_categories: int = 0
    total_questions: int = 0
    domains: list[str] = Field(default_factory=list)
    difficulties: list[str] = Field(default_factory=list)
    page: int = 1
    page_size: int = 20
    items: list[QuestionItem] = Field(default_factory=list)
    note: str = ""


# ---------------------------------------------------------------------------
# Legal Documents & Ingestion Schemas
# ---------------------------------------------------------------------------
class LegalChunk(BaseModel):
    chunk_id: str
    document_id: str | None = None
    document_number: str | None = None
    document_title: str | None = None
    part: str | None = None
    chapter: str | None = None
    section: str | None = None
    article: str | None = None
    clause: str | None = None
    point: str | None = None
    content: str
    source: str | None = None
    page_number: int | None = None
    effective_date: str | None = None
    chunk_index: int = 0
    needs_review: bool = False


class LegalDocumentSummary(BaseModel):
    document_id: str
    title: str
    document_number: str | None = None
    document_type: str | None = None
    issuing_authority: str | None = None
    issue_date: str | None = None
    effective_date: str | None = None
    expiry_date: str | None = None
    status: str | None = None
    source: str | None = None
    file_path: str
    checksum: str
    ingestion_date: datetime
    updated_at: datetime | None = None
    version: str | None = None
    chunk_count: int = 0
    qdrant_sync_status: str = "pending"
    qdrant_synced_chunks: int = 0
    embedding_model: str | None = None
    qdrant_collection: str | None = None
    needs_review: bool = False
    review_note: str | None = None
    last_error: str | None = None


class LegalDocumentDetailResponse(LegalDocumentSummary):
    chunks: list[LegalChunk] = Field(default_factory=list)


class LegalDocumentUpdateRequest(BaseModel):
    title: str | None = None
    document_number: str | None = None
    document_type: str | None = None
    issuing_authority: str | None = None
    issue_date: str | None = None
    effective_date: str | None = None
    expiry_date: str | None = None
    status: str | None = None
    source: str | None = None
    version: str | None = None


class LegalDocumentCreateTextRequest(BaseModel):
    filename: str = Field(..., min_length=3, max_length=200)
    title: str = Field(..., min_length=3, max_length=512)
    document_number: str | None = None
    document_type: str | None = None
    issuing_authority: str | None = None
    issue_date: str | None = None
    effective_date: str | None = None
    expiry_date: str | None = None
    status: str | None = None
    source: str | None = None
    content: str = Field(..., min_length=10)
    allow_update: bool = False


class LegalDocumentListResponse(BaseModel):
    loaded: bool
    total_documents: int = 0
    total_chunks: int = 0
    synced_documents: int = 0
    failed_documents: int = 0
    pending_files_in_dir: int = 0
    document_types: list[str] = Field(default_factory=list)
    issuing_authorities: list[str] = Field(default_factory=list)
    statuses: list[str] = Field(default_factory=list)
    items: list[LegalDocumentSummary] = Field(default_factory=list)
    note: str = ""


class LegalDocumentChunksResponse(BaseModel):
    document_id: str
    document_title: str
    document_number: str | None = None
    total_chunks: int = 0
    needs_review: bool = False
    items: list[LegalChunk] = Field(default_factory=list)


class IngestionFileResult(BaseModel):
    file_path: str
    document_id: str | None = None
    title: str | None = None
    action: Literal["ingested", "updated", "skipped_duplicate", "conflict_requires_update", "error", "detected_new"]
    status: Literal["success", "skipped", "conflict", "error"]
    message: str
    chunk_count: int = 0
    qdrant_sync_status: str | None = None
    needs_review: bool = False


class IngestRequest(BaseModel):
    file_path: str | None = Field(
        default=None,
        description="Tên file hoặc đường dẫn tương đối trong data/legal_documents/. Nếu bỏ trống sẽ nạp toàn bộ thư mục.",
    )
    allow_update: bool = Field(
        default=False,
        description="Cho phép cập nhật khi file đã tồn tại có nội dung thay đổi.",
    )


class ScanRequest(BaseModel):
    auto_ingest: bool = Field(default=True, description="Tự động nạp và đồng bộ các file mới phát hiện.")
    allow_update: bool = Field(default=False, description="Cho phép ghi đè cập nhật file đã thay đổi checksum.")


class ScanAndIngestResponse(BaseModel):
    directory: str
    total_files_found: int = 0
    ingested_count: int = 0
    updated_count: int = 0
    skipped_duplicate_count: int = 0
    conflict_count: int = 0
    error_count: int = 0
    results: list[IngestionFileResult] = Field(default_factory=list)
    message: str = ""


class FolderUploadFileItem(BaseModel):
    original_filename: str
    target_filename: str | None = None
    original_ext: str = ""
    converter_used: str | None = None
    converted: bool = False
    document_id: str | None = None
    title: str | None = None
    action: Literal[
        "ingested",
        "updated",
        "skipped_duplicate",
        "conflict_requires_update",
        "filtered_out",
        "error",
    ]
    status: Literal["success", "skipped", "conflict", "error"]
    message: str
    chunk_count: int = 0
    qdrant_sync_status: str | None = None


class FolderUploadResponse(BaseModel):
    total_received: int = 0
    supported_count: int = 0
    filtered_out_count: int = 0
    converted_count: int = 0
    ingested_count: int = 0
    updated_count: int = 0
    skipped_duplicate_count: int = 0
    conflict_count: int = 0
    error_count: int = 0
    items: list[FolderUploadFileItem] = Field(default_factory=list)
    message: str = ""


class IngestionLogItem(BaseModel):
    id: str
    file_path: str
    document_id: str | None = None
    action: str
    status: str
    message: str
    checksum: str | None = None
    chunk_count: int = 0
    created_at: datetime


class LegalDocumentsStatsResponse(BaseModel):
    total_documents: int = 0
    total_chunks: int = 0
    synced_documents: int = 0
    failed_documents: int = 0
    pending_documents: int = 0
    needs_review_documents: int = 0
    qdrant_connected: bool = False
    qdrant_backend: str = ""
    qdrant_collection: str = ""
    qdrant_points_count: int = 0
    qdrant_detail: str = ""
    embedding_model: str = ""
    documents_dir: str = ""
    files_in_dir: int = 0
    document_types: list[str] = Field(default_factory=list)
    issuing_authorities: list[str] = Field(default_factory=list)
    recent_logs: list[IngestionLogItem] = Field(default_factory=list)


# Tương thích ngược với GET /api/documents hiện có
class LegalDocumentItem(BaseModel):
    id: str
    title: str
    document_number: str | None = None
    document_type: str
    issuing_authority: str | None = None
    issued_date: str | None = None
    effective_date: str | None = None
    status: str | None = None
    source_file: str
    qdrant_sync_status: str = "not_synced"
    chunks: list[LegalChunk] = Field(default_factory=list)


class DocumentsResponse(BaseModel):
    loaded: bool
    total_documents: int = 0
    total_chunks: int = 0
    document_types: list[str] = Field(default_factory=list)
    items: list[LegalDocumentItem] = Field(default_factory=list)
    note: str = ""


# ---------------------------------------------------------------------------
# RAG, Agent, Citation Direct API Schemas
# ---------------------------------------------------------------------------
class RagSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    top_k: int = Field(default=5, ge=1, le=20)
    score_threshold: float = Field(default=0.25, ge=0.0, le=1.0)


class RagSearchHit(BaseModel):
    chunk_id: str | None = None
    document_id: str | None = None
    document_name: str
    document_number: str | None = None
    chapter: str | None = None
    article: str | None = None
    clause: str | None = None
    point: str | None = None
    content: str
    relevance_score: float
    effective_date: str | None = None
    validity_status: str = "Chưa xác định"


class RagSearchResponse(BaseModel):
    query: str
    qdrant_available: bool
    detail: str
    total_hits: int
    hits: list[RagSearchHit] = Field(default_factory=list)


class AgentAnalyzeRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)


class AgentAnalyzeResponse(BaseModel):
    question: str
    detected_domain: str
    issues: list[LegalIssueItem]
    retrieval_queries: list[str]
    needs_multi_document: bool


class AgentRunLogItem(BaseModel):
    id: str
    request_id: str
    conversation_id: str | None = None
    question: str
    overall_status: str
    self_correction_attempts: int
    error_message: str | None = None
    latency_ms: int
    is_mock: bool
    stages: list[ProcessingStepItem] = Field(default_factory=list)
    created_at: datetime


class CitationValidateRequest(BaseModel):
    claim: str = Field(..., min_length=2, max_length=2000)
    document_name: str | None = None
    document_number: str | None = None
    article: str | None = None
    clause: str | None = None
    evidence: str | None = None


class CitationValidateResponse(BaseModel):
    claim: str
    validation_status: CitationStatus
    support_status: str
    reason: str
    overlap_ratio: float
    checks: CitationChecks
    matched_document_id: str | None = None
    matched_chunk_id: str | None = None
    matched_evidence: str | None = None


class CitationReportResponse(BaseModel):
    total_checked: int
    valid_count: int
    invalid_count: int
    insufficient_count: int
    self_correction_runs: int
    total_self_correction_attempts: int
    pass_rate: float | None = None
    mock_count: int
    live_count: int


class CitationLogItem(BaseModel):
    id: str
    request_id: str
    question: str
    claim: str
    document_name: str
    document_number: str | None = None
    article: str | None = None
    clause: str | None = None
    point: str | None = None
    evidence: str
    validation_status: CitationStatus
    validation_reason: str
    relevance_score: float | None = None
    is_mock: bool
    created_at: datetime


# ---------------------------------------------------------------------------
# Statistics, Evaluation, Admin Dashboard, Testing & System Config Schemas
# ---------------------------------------------------------------------------
class StatisticsResponse(BaseModel):
    app_mode: str
    is_demo_data: bool
    total_question_categories: int
    expected_question_categories: int
    total_questions: int
    total_documents: int
    total_queries: int
    pass_count: int
    fail_count: int
    unverified_count: int
    pass_rate: float | None = None
    avg_response_time_ms: float | None = None
    queries_over_time: list[dict] = Field(default_factory=list)
    questions_by_category: list[dict] = Field(default_factory=list)


class EvaluationVariantMetric(BaseModel):
    variant: str
    recall_at_k: float | None = None
    answer_accuracy: float | None = None
    citation_accuracy: float | None = None
    citation_completeness: float | None = None
    citation_support_rate: float | None = None
    hallucination_rate: float | None = None
    latency_ms: float | None = None
    self_correction_rate: float | None = None


class EvaluationRunRequest(BaseModel):
    sample_size: int = Field(default=50, ge=5, le=100)
    difficulty_splits: list[str] = Field(
        default_factory=lambda: ["Easy", "Medium", "Multi-document", "Hard", "Citation-focused"]
    )


class EvaluationResultsResponse(BaseModel):
    has_results: bool
    run_id: str | None = None
    run_mode: str
    is_mock: bool = True
    dataset_size: int = 0
    difficulty_splits: list[str] = Field(
        default_factory=lambda: ["Easy", "Medium", "Multi-document", "Hard", "Citation-focused"]
    )
    variants: list[EvaluationVariantMetric] = Field(default_factory=list)
    note: str = ""
    created_at: datetime | None = None


class ServiceHealthItem(BaseModel):
    name: str
    status: Literal["online", "offline", "not_configured", "demo"]
    detail: str


class SystemStatusResponse(BaseModel):
    app_name: str
    app_mode: AppMode
    database: ServiceHealthItem
    qdrant: ServiceHealthItem
    llm: ServiceHealthItem
    rag: ServiceHealthItem
    agent: ServiceHealthItem
    citation_validator: ServiceHealthItem
    question_bank_loaded: bool
    legal_corpus_loaded: bool


class AdminDashboardResponse(BaseModel):
    app_mode: AppMode
    total_documents: int
    ingested_synced_documents: int
    failed_documents: int
    total_chunks: int
    total_queries: int
    total_users: int
    total_citations_checked: int
    citation_pass_count: int
    citation_fail_count: int
    citation_unverified_count: int
    self_correction_count: int
    backend_status: ServiceHealthItem
    qdrant_status: ServiceHealthItem
    database_status: ServiceHealthItem
    llm_status: ServiceHealthItem
    recent_queries: list[HistorySummary] = Field(default_factory=list)
    recent_ingestion_logs: list[IngestionLogItem] = Field(default_factory=list)


class SystemConfigResponse(BaseModel):
    app_mode: AppMode
    llm_provider: str
    llm_model: str
    llm_base_url: str
    llm_api_key_configured: bool
    llm_api_key_masked: str
    embedding_model: str
    qdrant_mode: str
    qdrant_url: str
    qdrant_collection: str
    database_backend: str
    max_self_correction_attempts: int
    auto_scan_on_startup: bool


class SystemConfigUpdateRequest(BaseModel):
    app_mode: AppMode | None = None
    llm_model: str | None = None
    max_self_correction_attempts: int | None = Field(default=None, ge=1, le=5)


class TestRunReportItem(BaseModel):
    id: str
    suite_name: str
    category: str
    total: int
    passed: int
    failed: int
    skipped: int
    duration_ms: int
    status: str
    output_summary: str
    results: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime


class ModeUpdateRequest(BaseModel):
    app_mode: AppMode
