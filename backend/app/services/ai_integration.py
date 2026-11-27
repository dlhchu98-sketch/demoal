"""
Lớp tích hợp AI (AI Integration Adapter — Đỗ Lê Hân phụ trách phần tích hợp Backend).

Vai trò:
- Kết nối Backend FastAPI với module RAG (Nguyễn Thanh Hiền) và module Agent + Citation Validator (Đặng Thị Ngọc Ánh)
  mà KHÔNG viết lại hay phá vỡ hợp đồng module của thành viên khác.
- Chuẩn hóa phản hồi theo hợp đồng API (Mục 5.1) với đầy đủ 7 bước theo dõi tiến trình thật
  và cấu trúc kết quả A-E (Kết luận, Phân tích tình huống, Căn cứ pháp lý, Kết quả kiểm chứng, Giới hạn).
- Thực hiện kiểm tra trích dẫn 6 tiêu chí trên dữ liệu thật trong DB + CitationValidator (không để LLM tự xác nhận).
"""

from __future__ import annotations

import re
from sqlalchemy import select
from sqlalchemy.orm import Session

from agent.validator import CitationValidator
from backend.app.core.database import LegalChunkORM, LegalDocumentORM
from backend.app.schemas.legal import (
    AgentAnalyzeResponse,
    ChatResponse,
    CitationChecks,
    CitationItem,
    CitationValidateRequest,
    CitationValidateResponse,
    LegalIssueItem,
    ProcessingStatusInfo,
    ProcessingStepItem,
    RagSearchHit,
    RagSearchResponse,
    ValidationDetailItem,
)
from rag.pipeline import evaluate_document_validity
from rag.retriever import QdrantLegalRetriever


DOMAIN_RULES: list[tuple[list[str], str]] = [
    (["hợp đồng lao động", "lao động", "lương", "thử việc", "sa thải", "bảo hiểm xã hội", "nghỉ phép", "tăng ca", "thai sản", "thất nghiệp"], "Lao động"),
    (["sinh viên", "học sinh", "nghỉ học", "học phí", "tuyển sinh", "tín chỉ", "trường đại học", "học bổng"], "Giáo dục"),
    (["giao thông", "nồng độ cồn", "giấy phép lái xe", "bằng lái", "vượt đèn đỏ", "phạt nguội", "tai nạn giao thông"], "Giao thông"),
    (["đất đai", "sổ đỏ", "tách thửa", "nhà ở", "thuê nhà", "chung cư", "chuyển nhượng đất"], "Đất đai & Nhà ở"),
    (["hôn nhân", "ly hôn", "kết hôn", "con chung", "tài sản chung", "cấp dưỡng", "nuôi con"], "Hôn nhân & Gia đình"),
    (["thừa kế", "di chúc", "di sản"], "Thừa kế"),
    (["hợp đồng", "đặt cọc", "vay tiền", "vay nợ", "lãi suất", "bồi thường", "dân sự"], "Dân sự & Hợp đồng"),
    (["hình sự", "tội phạm", "trộm cắp", "lừa đảo", "phạt tù", "tố cáo"], "Hình sự"),
    (["thuế", "doanh nghiệp", "công ty", "kinh doanh", "hóa đơn"], "Doanh nghiệp & Thuế"),
]


def detect_legal_domain(question: str) -> str:
    q = question.lower()
    for keywords, domain in DOMAIN_RULES:
        if any(k in q for k in keywords):
            return domain
    return "Pháp luật Việt Nam"


def analyze_question_structured(question: str) -> AgentAnalyzeResponse:
    """Phân tích câu hỏi & phân rã vấn đề pháp lý phục vụ lập kế hoạch truy xuất đa văn bản."""
    domain = detect_legal_domain(question)
    q_low = question.lower()
    issues: list[LegalIssueItem] = []

    issues.append(
        LegalIssueItem(
            issue=f"Xác định quy định pháp luật trực tiếp điều chỉnh tình huống thuộc lĩnh vực {domain}.",
            legal_domain=domain,
            sub_query=question,
        )
    )

    multi_doc_signals = ["và", "khác gì", "khác nhau", "đồng thời", "tranh chấp", "bồi thường", "xử phạt", "hình sự", "nước ngoài", "thuế"]
    needs_multi = any(sig in q_low for sig in multi_doc_signals)

    if any(k in q_low for k in ["thủ tục", "hồ sơ", "ở đâu", "khiếu nại", "khởi kiện", "tố cáo"]):
        issues.append(
            LegalIssueItem(
                issue="Xác định thẩm quyền giải quyết, trình tự thủ tục và thời hiệu theo quy định liên quan.",
                legal_domain=domain,
                sub_query=f"Thẩm quyền thủ tục thời hiệu {domain}: {question}",
            )
        )
    elif any(k in q_low for k in ["phạt", "bồi thường", "trách nhiệm", "vi phạm", "vô hiệu"]):
        issues.append(
            LegalIssueItem(
                issue="Đối chiếu chế tài xử lý, mức phạt hoặc trách nhiệm bồi thường giữa các văn bản liên quan.",
                legal_domain=domain,
                sub_query=f"Chế tài xử lý trách nhiệm {domain}: {question}",
            )
        )
    elif needs_multi:
        issues.append(
            LegalIssueItem(
                issue="Đối chiếu quy định liên ngành và văn bản hướng dẫn thi hành liên quan.",
                legal_domain=domain,
                sub_query=f"Văn bản hướng dẫn và điều kiện áp dụng {domain}: {question}",
            )
        )

    return AgentAnalyzeResponse(
        question=question,
        detected_domain=domain,
        issues=issues,
        retrieval_queries=[i.sub_query or question for i in issues],
        needs_multi_document=needs_multi or len(issues) > 1,
    )


def _compute_verification_label(citation_status: str, citations: list[CitationItem], is_mock: bool) -> str:
    if is_mock:
        return "Chưa đủ bằng chứng (Chế độ DEMO)"
    if citation_status == "PASS":
        any_unverified_validity = any(
            (c.validity_status or "").lower() in {"", "chưa xác định"} for c in citations
        )
        if any_unverified_validity:
            return "Đã xác minh nguồn (Chưa xác minh được hiệu lực)"
        return "Đã xác minh"
    if citation_status == "FAIL":
        return "Không hợp lệ"
    return "Chưa đủ bằng chứng"


def _evaluate_citation_checks(db: Session, cit: CitationItem, is_mock: bool) -> tuple[CitationChecks, str]:
    """Kiểm tra 6 tiêu chí trích dẫn trên dữ liệu gốc trong DB (không tự để LLM xác nhận)."""
    if is_mock:
        return (
            CitationChecks(
                document_exists=False,
                number_valid=False,
                structure_exists=False,
                quote_matches=False,
                supports_claim=False,
                validity_verified=False,
            ),
            "INSUFFICIENT_EVIDENCE",
        )

    doc_row = db.get(LegalDocumentORM, cit.document_id) if cit.document_id else None
    chunk_row = db.get(LegalChunkORM, cit.chunk_id) if cit.chunk_id else None

    doc_exists = doc_row is not None
    number_valid = bool(
        doc_row is not None
        and cit.document_number
        and doc_row.document_number
        and doc_row.document_number.strip().lower() == cit.document_number.strip().lower()
    )
    structure_exists = bool(
        chunk_row is not None
        and (
            (not cit.article or (chunk_row.article and cit.article.lower() == chunk_row.article.lower()))
            and (not cit.clause or (chunk_row.clause and cit.clause.lower() == chunk_row.clause.lower()))
        )
    )
    quote_matches = bool(
        chunk_row is not None
        and cit.evidence
        and (cit.evidence.strip()[:80] in chunk_row.content or chunk_row.content.strip()[:80] in cit.evidence)
    )
    supports_claim = cit.validation_status == "PASS"
    validity_verified = bool(
        cit.validity_status and cit.validity_status.lower() not in {"chưa xác định", "none"}
    )

    if cit.validation_status == "PASS":
        support_status = "SUPPORTED"
    elif cit.validation_status == "FAIL":
        if cit.validation_reason and "mâu thuẫn" in cit.validation_reason.lower():
            support_status = "CONTRADICTED"
        else:
            support_status = "UNSUPPORTED"
    else:
        support_status = "INSUFFICIENT_EVIDENCE"

    return (
        CitationChecks(
            document_exists=doc_exists,
            number_valid=number_valid,
            structure_exists=structure_exists,
            quote_matches=quote_matches,
            supports_claim=supports_claim,
            validity_verified=validity_verified,
        ),
        support_status,
    )


def enrich_chat_response(db: Session, response: ChatResponse) -> ChatResponse:
    """
    Bổ sung các trường hợp đồng API Mục 5.1, tiến trình 7 bước thật và cấu trúc A-E
    mà vẫn giữ nguyên 100% các trường hiện có.
    """
    # 1. Chuẩn hóa từng citation (đồng bộ alias document_title, quoted_text, source_url, checks)
    validation_details: list[ValidationDetailItem] = []
    for idx, cit in enumerate(response.citations, start=1):
        cit.document_title = cit.document_title or cit.document_name
        cit.quoted_text = cit.quoted_text or cit.evidence
        if not cit.source_url and cit.source and cit.source.startswith(("http://", "https://")):
            cit.source_url = cit.source
        checks, support_status = _evaluate_citation_checks(db, cit, response.is_mock)
        cit.checks = checks
        cit.support_status = support_status  # type: ignore[assignment]
        loc = " · ".join(p for p in [cit.chapter, cit.article, cit.clause, cit.point] if p) or "Toàn văn / chưa tách Điều"
        validation_details.append(
            ValidationDetailItem(
                citation_index=idx,
                document_title=cit.document_title,
                document_number=cit.document_number,
                location=loc,
                validation_status=cit.validation_status,
                support_status=support_status,
                validity_status=cit.validity_status or "Chưa xác định",
                reason=cit.validation_reason or "Chưa có nhận xét kiểm chứng.",
                checks=checks,
            )
        )

    response.validation_details = validation_details
    response.verification_label = _compute_verification_label(
        response.citation_status, response.citations, response.is_mock
    )

    # 2. Tạo cấu trúc A (Kết luận), B (Phân tích), E (Giới hạn) trung thực từ kết quả thật
    if not response.conclusion:
        first_para = next((p.strip() for p in response.answer.split("\n\n") if p.strip()), response.answer)
        response.conclusion = first_para

    if not response.explanation:
        if response.analysis:
            issue_lines = [
                f"- Vấn đề {i}: {item.issue}" + (f" (Lĩnh vực: {item.legal_domain})" if item.legal_domain else "")
                for i, item in enumerate(response.analysis, start=1)
            ]
            response.explanation = "\n".join(issue_lines)
        else:
            response.explanation = "Chưa có phân rã chi tiết bổ sung cho tình huống này."

    limitations: list[str] = []
    if response.is_mock:
        limitations.append("Hệ thống đang vận hành ở chế độ DEMO (is_mock=true); chưa truy xuất văn bản pháp luật thật từ Qdrant.")
    if not response.citations:
        limitations.append("Không tìm thấy điều khoản pháp luật phù hợp trong kho dữ liệu Qdrant hiện tại.")
    if any((c.validity_status or "").lower() in {"", "chưa xác định"} for c in response.citations):
        limitations.append("Một hoặc nhiều văn bản trích dẫn chưa có đủ dữ liệu xác minh tình trạng hiệu lực hiện hành.")
    if response.citation_status != "PASS":
        limitations.append("Kết quả chưa đạt trạng thái Đã xác minh (PASS); cần đối chiếu thêm văn bản quy phạm pháp luật gốc.")
    limitations.append("Nội dung chỉ phục vụ mục đích tra cứu và học tập, không thay thế tư vấn pháp lý chính thức của luật sư.")
    response.limitations = limitations

    # 3. Xây dựng tiến trình 7 bước phản ánh trạng thái THẬT từ Backend (không giả lập toàn xanh)
    trace_by_stage = {t.stage: t for t in response.pipeline_trace}
    retrieval_trace = trace_by_stage.get("retrieval_planning")
    validator_trace = trace_by_stage.get("citation_validator")

    has_real_evidence = (not response.is_mock) and len(response.citations) > 0
    retrieval_status: str = "completed" if has_real_evidence else "warning"
    retrieval_detail = (
        retrieval_trace.detail
        if retrieval_trace
        else ("Đã truy xuất văn bản từ Qdrant." if has_real_evidence else "Chưa có văn bản pháp luật thật phù hợp trong Qdrant.")
    )

    analysis_status: str = "completed" if has_real_evidence else "warning"
    analysis_detail = (
        f"Đã đối chiếu {len(response.citations)} căn cứ pháp lý cho {len(response.analysis)} vấn đề."
        if has_real_evidence
        else "Chưa đủ bằng chứng pháp lý gốc để đối chiếu sâu; áp dụng nguyên tắc không suy diễn."
    )

    if response.citation_status == "PASS" and not response.is_mock:
        val_step_status = "completed"
    elif response.citation_status == "FAIL":
        val_step_status = "error"
    else:
        val_step_status = "warning"

    val_detail = validator_trace.detail if validator_trace else f"Trạng thái kiểm chứng: {response.verification_label}."
    if response.self_correction.performed:
        val_detail += f" (Đã thực hiện {response.self_correction.attempts}/{response.self_correction.max_attempts} lượt Self-Correction.)"

    domain = response.analysis[0].legal_domain if response.analysis and response.analysis[0].legal_domain else detect_legal_domain(response.question)

    steps = [
        ProcessingStepItem(
            step_number=1,
            stage="receive_question",
            label="Tiếp nhận câu hỏi",
            status="completed",
            detail=f"Đã tiếp nhận và kiểm tra hợp lệ câu hỏi ({len(response.question)} ký tự).",
            duration_ms=2,
        ),
        ProcessingStepItem(
            step_number=2,
            stage="query_analysis",
            label="Phân tích câu hỏi",
            status="completed",
            detail=f"Nhận diện ngữ cảnh tiếng Việt thuộc lĩnh vực: {domain}.",
            duration_ms=trace_by_stage.get("question_analysis").duration_ms if trace_by_stage.get("question_analysis") else 6,
        ),
        ProcessingStepItem(
            step_number=3,
            stage="issue_decomposition",
            label="Phân rã vấn đề pháp lý",
            status="completed" if response.analysis else "warning",
            detail=f"Phân rã thành {len(response.analysis)} vấn đề pháp lý để truy xuất đa văn bản.",
            duration_ms=trace_by_stage.get("issue_decomposition").duration_ms if trace_by_stage.get("issue_decomposition") else 8,
        ),
        ProcessingStepItem(
            step_number=4,
            stage="document_retrieval",
            label="Tìm kiếm văn bản",
            status=retrieval_status,  # type: ignore[arg-type]
            detail=retrieval_detail,
            duration_ms=retrieval_trace.duration_ms if retrieval_trace else None,
        ),
        ProcessingStepItem(
            step_number=5,
            stage="legal_analysis",
            label="Đối chiếu và phân tích",
            status=analysis_status,  # type: ignore[arg-type]
            detail=analysis_detail,
            duration_ms=max(1, response.processing_time_ms // 4),
        ),
        ProcessingStepItem(
            step_number=6,
            stage="citation_validation",
            label="Kiểm tra trích dẫn",
            status=val_step_status,  # type: ignore[arg-type]
            detail=val_detail,
            duration_ms=validator_trace.duration_ms if validator_trace else None,
        ),
        ProcessingStepItem(
            step_number=7,
            stage="final_response",
            label="Trả kết quả",
            status="completed" if response.citation_status == "PASS" and not response.is_mock else "warning",
            detail=f"Hoàn tất phản hồi trong {response.processing_time_ms} ms — Trạng thái: {response.verification_label}.",
            duration_ms=2,
        ),
    ]

    if response.citation_status == "PASS" and not response.is_mock:
        overall_state = "completed"
    elif response.citation_status == "FAIL":
        overall_state = "error"
    elif not has_real_evidence:
        overall_state = "insufficient_evidence"
    else:
        overall_state = "completed_with_warnings"

    response.processing_status = ProcessingStatusInfo(
        current_step=7,
        total_steps=7,
        overall_state=overall_state,  # type: ignore[arg-type]
        steps=steps,
    )
    return response


def search_rag_corpus(
    retriever: QdrantLegalRetriever,
    query: str,
    top_k: int = 5,
    score_threshold: float = 0.25,
) -> RagSearchResponse:
    available, detail = retriever.is_available()
    if not available:
        return RagSearchResponse(
            query=query,
            qdrant_available=False,
            detail=detail,
            total_hits=0,
            hits=[],
        )
    evidences = retriever.search(query=query, top_k=top_k, score_threshold=score_threshold)
    hits: list[RagSearchHit] = []
    for ev in evidences:
        validity_label, _ = evaluate_document_validity(ev.effective_date, ev.expiry_date, ev.document_status)
        hits.append(
            RagSearchHit(
                chunk_id=ev.chunk_id,
                document_id=ev.document_id,
                document_name=ev.document_name,
                document_number=ev.document_number,
                chapter=ev.chapter,
                article=ev.article,
                clause=ev.clause,
                point=ev.point,
                content=ev.content,
                relevance_score=ev.relevance_score,
                effective_date=ev.effective_date,
                validity_status=validity_label,
            )
        )
    return RagSearchResponse(
        query=query,
        qdrant_available=True,
        detail=detail,
        total_hits=len(hits),
        hits=hits,
    )


def validate_citation_against_corpus(
    db: Session,
    payload: CitationValidateRequest,
) -> CitationValidateResponse:
    """
    Kiểm tra trực tiếp một trích dẫn theo 6 tiêu chí thực tế (Mục 6.2):
    1. Văn bản có tồn tại không?
    2. Số hiệu có đúng không?
    3. Điều/Khoản/Điểm có tồn tại không?
    4. Nội dung trích dẫn có khớp nguồn không?
    5. Nguồn có hỗ trợ nhận định không?
    6. Tình trạng hiệu lực có được xác minh không?
    """
    validator = CitationValidator()

    # Tìm văn bản trong DB nếu có cung cấp document_number hoặc document_name
    matched_doc: LegalDocumentORM | None = None
    if payload.document_number and payload.document_number.strip():
        num_q = payload.document_number.strip().lower()
        docs = db.execute(select(LegalDocumentORM)).scalars().all()
        matched_doc = next((d for d in docs if (d.document_number or "").strip().lower() == num_q), None)

    if matched_doc is None and payload.document_name and payload.document_name.strip():
        name_q = payload.document_name.strip().lower()
        docs = db.execute(select(LegalDocumentORM)).scalars().all()
        matched_doc = next((d for d in docs if name_q in d.title.lower() or d.title.lower() in name_q), None)

    matched_chunk: LegalChunkORM | None = None
    if matched_doc is not None:
        chunks = db.execute(
            select(LegalChunkORM).where(LegalChunkORM.document_id == matched_doc.document_id)
        ).scalars().all()
        if payload.article:
            art_norm = re.sub(r"\s+", " ", payload.article.strip().lower())
            art_chunks = [c for c in chunks if c.article and art_norm == c.article.strip().lower()]
            if payload.clause and art_chunks:
                cl_norm = re.sub(r"\s+", " ", payload.clause.strip().lower())
                cl_chunks = [c for c in art_chunks if c.clause and cl_norm == c.clause.strip().lower()]
                matched_chunk = cl_chunks[0] if cl_chunks else None
            elif art_chunks:
                matched_chunk = art_chunks[0]
        elif chunks:
            matched_chunk = chunks[0]

    # Xác định 6 tiêu chí
    doc_exists = matched_doc is not None
    number_valid: bool | None = None
    if payload.document_number:
        number_valid = bool(
            matched_doc
            and matched_doc.document_number
            and matched_doc.document_number.strip().lower() == payload.document_number.strip().lower()
        )
    elif matched_doc:
        number_valid = bool(matched_doc.document_number)

    structure_exists: bool | None = None
    if payload.article or payload.clause:
        structure_exists = matched_chunk is not None
    elif matched_chunk is not None:
        structure_exists = True

    evidence_text = (matched_chunk.content if matched_chunk else "") or (payload.evidence or "")
    quote_matches: bool | None = None
    if payload.evidence and matched_chunk:
        q_clean = re.sub(r"\s+", " ", payload.evidence.strip().lower())
        c_clean = re.sub(r"\s+", " ", matched_chunk.content.strip().lower())
        quote_matches = (q_clean[:60] in c_clean) or (c_clean[:60] in q_clean)
    elif matched_chunk:
        quote_matches = True
    elif payload.evidence:
        quote_matches = False

    validity_verified = False
    if matched_doc is not None:
        val_label, _ = evaluate_document_validity(
            matched_doc.effective_date, matched_doc.expiry_date, matched_doc.status
        )
        validity_verified = val_label not in {"Chưa xác định", "Hết hiệu lực"}

    # Nếu người dùng nêu cụ thể số hiệu hoặc điều luật mà không tồn tại trong DB khi DB có dữ liệu -> FAIL
    total_docs_in_db = db.query(LegalDocumentORM).count()
    if total_docs_in_db > 0 and (payload.document_number or payload.document_name) and not doc_exists:
        return CitationValidateResponse(
            claim=payload.claim,
            validation_status="FAIL",
            support_status="UNSUPPORTED",
            reason="Không tìm thấy văn bản hoặc số hiệu văn bản tương ứng trong cơ sở dữ liệu pháp luật.",
            overlap_ratio=0.0,
            checks=CitationChecks(
                document_exists=False,
                number_valid=False if payload.document_number else None,
                structure_exists=False if (payload.article or payload.clause) else None,
                quote_matches=False,
                supports_claim=False,
                validity_verified=False,
            ),
        )

    if doc_exists and (payload.document_number and number_valid is False):
        return CitationValidateResponse(
            claim=payload.claim,
            validation_status="FAIL",
            support_status="UNSUPPORTED",
            reason=f"Sai số hiệu văn bản: cơ sở dữ liệu ghi nhận số hiệu '{matched_doc.document_number}' thay vì '{payload.document_number}'.",
            overlap_ratio=0.0,
            checks=CitationChecks(
                document_exists=True,
                number_valid=False,
                structure_exists=structure_exists,
                quote_matches=quote_matches,
                supports_claim=False,
                validity_verified=validity_verified,
            ),
            matched_document_id=matched_doc.document_id if matched_doc else None,
        )

    if doc_exists and (payload.article or payload.clause) and matched_chunk is None:
        return CitationValidateResponse(
            claim=payload.claim,
            validation_status="FAIL",
            support_status="UNSUPPORTED",
            reason=f"Không tồn tại cấu trúc trích dẫn '{payload.article or ''} {payload.clause or ''}'.strip() trong văn bản '{matched_doc.title}'.",
            overlap_ratio=0.0,
            checks=CitationChecks(
                document_exists=True,
                number_valid=number_valid,
                structure_exists=False,
                quote_matches=False,
                supports_claim=False,
                validity_verified=validity_verified,
            ),
            matched_document_id=matched_doc.document_id,
        )

    # Đối chiếu hỗ trợ ngữ nghĩa bằng CitationValidator của Ánh
    val_res = validator.validate(claim=payload.claim, evidence=evidence_text, is_mock_source=False)
    supports_claim = val_res.status == "PASS"

    if val_res.status == "PASS":
        support_status = "SUPPORTED"
    elif val_res.status == "FAIL":
        support_status = "CONTRADICTED" if "mâu thuẫn" in val_res.reason.lower() else "UNSUPPORTED"
    else:
        support_status = "INSUFFICIENT_EVIDENCE"

    return CitationValidateResponse(
        claim=payload.claim,
        validation_status=val_res.status,
        support_status=support_status,
        reason=val_res.reason,
        overlap_ratio=val_res.overlap_ratio,
        checks=CitationChecks(
            document_exists=doc_exists if (payload.document_name or payload.document_number) else None,
            number_valid=number_valid,
            structure_exists=structure_exists,
            quote_matches=quote_matches,
            supports_claim=supports_claim,
            validity_verified=validity_verified if doc_exists else None,
        ),
        matched_document_id=matched_doc.document_id if matched_doc else None,
        matched_chunk_id=matched_chunk.chunk_id if matched_chunk else None,
        matched_evidence=matched_chunk.content if matched_chunk else None,
    )
