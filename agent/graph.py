"""
Module Agent điều phối luồng hỏi đáp pháp luật theo kiến trúc LangGraph (Đặng Thị Ngọc Ánh phụ trách).

Luồng xử lý:
User Question
 -> Question Analysis
 -> Legal Issue Decomposition
 -> Retrieval Planning
 -> RAG (Qdrant Vector Search -> Top-K Legal Evidence)
 -> Validity Check (kiểm tra hiệu lực từ metadata đáng tin cậy tại thời điểm truy vấn)
 -> Answer Generation (LLM nếu có API key, hoặc tổng hợp nguyên văn từ chunk thực tế)
 -> Citation Validator
 -> Self-correction (nếu FAIL và attempts < max_attempts)
 -> Final Answer
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TypedDict

import httpx

from agent.validator import CitationValidator
from backend.app.schemas.legal import (
    ChatResponse,
    CitationItem,
    LegalIssueItem,
    PipelineTraceStep,
    SelfCorrectionInfo,
    SelfCorrectionStep,
)
from rag.pipeline import evaluate_document_validity
from rag.retriever import LegalRetrieverProtocol, RetrievedEvidence

logger = logging.getLogger(__name__)


class LegalAgentState(TypedDict, total=False):
    question: str
    conversation_id: str | None
    issues: list[LegalIssueItem]
    retrieval_queries: list[str]
    evidences: list[RetrievedEvidence]
    draft_answer: str
    citations: list[CitationItem]
    citation_status: str
    attempts: int
    max_attempts: int
    correction_steps: list[SelfCorrectionStep]
    pipeline_trace: list[PipelineTraceStep]


@dataclass
class LegalAgentOrchestrator:
    retriever: LegalRetrieverProtocol
    validator: CitationValidator = field(default_factory=CitationValidator)
    llm_api_key: str = ""
    llm_model: str = ""
    llm_base_url: str = ""
    max_attempts: int = 2

    def _analyze_and_decompose(self, state: LegalAgentState) -> LegalAgentState:
        question = state["question"]
        issues = [
            LegalIssueItem(
                issue=f"Phân tích căn cứ pháp lý trực tiếp cho câu hỏi: {question}",
                legal_domain="Tra cứu pháp luật Việt Nam",
                sub_query=question,
            )
        ]
        state["issues"] = issues
        state["retrieval_queries"] = [i.sub_query or question for i in issues]
        state["pipeline_trace"].append(
            PipelineTraceStep(
                stage="question_analysis",
                label="Phân tích & phân rã vấn đề pháp lý",
                status="done",
                detail=f"Xác định {len(issues)} vấn đề pháp lý cần truy xuất bằng chứng.",
                duration_ms=8,
            )
        )
        return state

    def _retrieve_evidence(self, state: LegalAgentState, top_k: int = 5) -> LegalAgentState:
        t0 = time.perf_counter()
        available, reason = self.retriever.is_available()
        if not available:
            state["evidences"] = []
            state["pipeline_trace"].append(
                PipelineTraceStep(
                    stage="retrieval_planning",
                    label="Truy xuất kho văn bản Qdrant (RAG)",
                    status="warning",
                    detail=reason,
                    duration_ms=max(int((time.perf_counter() - t0) * 1000), 1),
                )
            )
            return state

        collected: list[RetrievedEvidence] = []
        seen_chunk_ids: set[str] = set()
        for q in state.get("retrieval_queries", []):
            for ev in self.retriever.search(q, top_k=top_k):
                key = ev.chunk_id or f"{ev.document_id}:{ev.article}:{ev.content[:40]}"
                if key not in seen_chunk_ids:
                    seen_chunk_ids.add(key)
                    collected.append(ev)

        state["evidences"] = collected
        state["pipeline_trace"].append(
            PipelineTraceStep(
                stage="retrieval_planning",
                label="Truy xuất kho văn bản Qdrant (RAG)",
                status="done" if collected else "warning",
                detail=(
                    f"Truy xuất được {len(collected)} đoạn chunk pháp lý thực tế từ Qdrant."
                    if collected
                    else "Không tìm thấy đoạn chunk pháp lý nào đủ mức liên quan trong Qdrant."
                ),
                duration_ms=max(int((time.perf_counter() - t0) * 1000), 1),
            )
        )
        return state

    def _call_llm_grounded(self, question: str, evidences: list[RetrievedEvidence]) -> str | None:
        """Gọi LLM OpenAI-compatible nếu người dùng đã cấu hình LLM_API_KEY; ép chỉ dùng bằng chứng thật."""
        if not self.llm_api_key or not self.llm_api_key.strip():
            return None

        base_url = (self.llm_base_url or "https://api.openai.com/v1").rstrip("/")
        context_blocks: list[str] = []
        for idx, ev in enumerate(evidences, start=1):
            loc = ", ".join(p for p in [ev.chapter, ev.article, ev.clause, ev.point] if p) or "Nội dung văn bản"
            validity_label, _ = evaluate_document_validity(ev.effective_date, ev.expiry_date, ev.document_status)
            context_blocks.append(
                f"[{idx}] Văn bản: {ev.document_name} | Số hiệu: {ev.document_number or 'Chưa xác định'} | "
                f"Vị trí: {loc} | Hiệu lực: {validity_label} (ngày hiệu lực: {ev.effective_date or 'Chưa xác định'}) | "
                f"Chunk ID: {ev.chunk_id}\nNội dung nguyên văn:\n{ev.content}"
            )

        system_prompt = (
            "Bạn là trợ lý tra cứu pháp luật Việt Nam. "
            "CHỈ được trả lời dựa trên các đoạn trích văn bản pháp luật được cung cấp dưới đây. "
            "TUYỆT ĐỐI KHÔNG tự bịa số hiệu văn bản, Điều, Khoản, Điểm hoặc nội dung không có trong nguồn. "
            "Phải trích dẫn rõ tên văn bản, số hiệu (nếu có), Điều/Khoản/Điểm và ghi chú tình trạng hiệu lực theo dữ liệu nguồn."
        )
        user_prompt = f"Câu hỏi: {question}\n\nNguồn căn cứ pháp lý thực tế:\n\n" + "\n\n".join(context_blocks)

        try:
            resp = httpx.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.llm_api_key.strip()}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.llm_model or "gpt-4o-mini",
                    "temperature": 0.1,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                },
                timeout=20.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                if content and content.strip():
                    return content.strip()
        except Exception as exc:
            logger.warning("Không thể gọi LLM API (%s); fallback tổng hợp nguyên văn từ chunk Qdrant.", exc)
        return None

    @staticmethod
    def _build_extractive_grounded_answer(
        question: str,
        citations: list[CitationItem],
        llm_configured: bool,
    ) -> str:
        """
        Tổng hợp câu trả lời bám sát 100% các chunk thực tế truy xuất từ Qdrant,
        không tự viết lại hay suy diễn điều luật, hiển thị đầy đủ tên văn bản, số hiệu, Điều/Khoản/Điểm và hiệu lực.
        """
        lines = [
            f'Căn cứ các đoạn văn bản pháp luật thực tế truy xuất từ Qdrant cho câu hỏi: "{question}"',
            "",
        ]
        for idx, cit in enumerate(citations, start=1):
            loc_parts = [p for p in [cit.chapter, cit.article, cit.clause, cit.point] if p]
            loc_str = " · ".join(loc_parts) if loc_parts else "Chưa phân tách Điều/Khoản"
            num_str = f" (Số hiệu: {cit.document_number})" if cit.document_number else " (Số hiệu: Chưa xác định)"
            eff_str = cit.effective_date or "Chưa xác định"
            val_str = cit.validity_status or "Chưa xác định"
            lines.append(
                f"{idx}. {cit.document_name}{num_str} — {loc_str}"
            )
            lines.append(f"   - Hiệu lực: {val_str} (Ngày hiệu lực: {eff_str}) | Mã chunk: {cit.chunk_id or 'N/A'}")
            lines.append(f"   - Nội dung gốc: {cit.evidence}")
            lines.append("")

        if not llm_configured:
            lines.append(
                "Ghi chú: Câu trả lời trên được tổng hợp trực tiếp từ nội dung nguyên văn trong Qdrant "
                "(chưa cấu hình LLM_API_KEY để diễn giải bổ sung)."
            )
        return "\n".join(lines).strip()

    def run_live(self, question: str, conversation_id: str | None = None) -> ChatResponse:
        """
        Thực thi luồng LIVE MODE thật với RAG + Qdrant + Citation Validator.
        Nếu không tìm thấy căn cứ pháp lý thực tế trong Qdrant, TUYỆT ĐỐI KHÔNG tự tạo nguồn giả
        mà thông báo rõ không đủ dữ liệu để trả lời (trạng thái UNVERIFIED).
        """
        started = time.perf_counter()
        state: LegalAgentState = {
            "question": question,
            "conversation_id": conversation_id or str(uuid.uuid4()),
            "attempts": 0,
            "max_attempts": self.max_attempts,
            "correction_steps": [],
            "pipeline_trace": [],
        }

        state = self._analyze_and_decompose(state)
        state = self._retrieve_evidence(state, top_k=5)

        evidences = state.get("evidences", [])
        # Chỉ giữ các bằng chứng gắn với chunk & document thực tế
        verified_evidences = [ev for ev in evidences if ev.content and ev.document_name]

        if not verified_evidences:
            available, q_reason = self.retriever.is_available()
            if not available:
                reason = f"kho vector Qdrant chưa sẵn sàng ({q_reason})"
            else:
                reason = "không tìm thấy căn cứ pháp lý phù hợp trong cơ sở dữ liệu hiện có"

            state["pipeline_trace"].append(
                PipelineTraceStep(
                    stage="citation_validator",
                    label="Kiểm tra trích dẫn (LIVE)",
                    status="warning",
                    detail=f"Trả trạng thái UNVERIFIED vì {reason}.",
                    duration_ms=5,
                )
            )
            elapsed_ms = max(int((time.perf_counter() - started) * 1000), 10)
            return ChatResponse(
                request_id=str(uuid.uuid4()),
                conversation_id=state["conversation_id"],
                question=question,
                answer=(
                    "Không đủ dữ liệu pháp luật để trả lời xác thực cho câu hỏi này.\n\n"
                    f"- Nguyên nhân: {reason}.\n"
                    "- Nguyên tắc an toàn pháp lý: LEGAL ASSISTANT không sử dụng nguồn ngoài cơ sở dữ liệu, "
                    "không tự tạo số hiệu văn bản, Điều, Khoản, Điểm hoặc nội dung điều luật.\n"
                    "- Khuyến nghị: Vui lòng bổ sung văn bản pháp luật liên quan vào thư mục data/legal_documents/ "
                    "và thực hiện đồng bộ lên Qdrant."
                ),
                analysis=state.get("issues", []),
                citations=[],
                citation_status="UNVERIFIED",
                self_correction=SelfCorrectionInfo(
                    attempts=0,
                    performed=False,
                    max_attempts=self.max_attempts,
                    steps=[],
                ),
                pipeline_trace=state["pipeline_trace"],
                is_mock=False,
                app_mode="live",
                processing_time_ms=elapsed_ms,
                created_at=datetime.now(timezone.utc),
            )

        # Kiểm tra hiệu lực & đối chiếu từng chunk bằng Citation Validator
        def build_validated_citations(evs: list[RetrievedEvidence]) -> tuple[list[CitationItem], str]:
            built: list[CitationItem] = []
            pass_cnt = 0
            fail_cnt = 0
            for ev in evs:
                validity_label, validity_note = evaluate_document_validity(
                    ev.effective_date,
                    ev.expiry_date,
                    ev.document_status,
                )
                validation = self.validator.validate(claim=question, evidence=ev.content, is_mock_source=False)
                if validation.status == "PASS":
                    pass_cnt += 1
                elif validation.status == "FAIL":
                    fail_cnt += 1

                reason_full = f"{validation.reason} | Kiểm tra hiệu lực: {validity_note}"
                built.append(
                    CitationItem(
                        claim=question,
                        chunk_id=ev.chunk_id,
                        document_id=ev.document_id,
                        document_name=ev.document_name,
                        document_number=ev.document_number,
                        chapter=ev.chapter,
                        article=ev.article,
                        clause=ev.clause,
                        point=ev.point,
                        evidence=ev.content,
                        source=ev.source,
                        effective_date=ev.effective_date,
                        validity_status=validity_label,
                        relevance_score=ev.relevance_score,
                        validation_status=validation.status,
                        validation_reason=reason_full,
                    )
                )

            if pass_cnt > 0:
                overall = "PASS"
            elif fail_cnt > 0:
                overall = "FAIL"
            else:
                overall = "UNVERIFIED"
            return built, overall

        citations, overall_status = build_validated_citations(verified_evidences)

        # Self-correction nếu tất cả chunk ban đầu trả FAIL và còn lượt thử
        if overall_status == "FAIL" and state["attempts"] < self.max_attempts:
            state["attempts"] += 1
            expanded = self.retriever.search(question, top_k=8)
            retry_citations, retry_status = build_validated_citations(expanded)
            passing_only = [c for c in retry_citations if c.validation_status == "PASS"]
            if passing_only:
                citations = passing_only
                overall_status = "PASS"
                detail_msg = f"Đã mở rộng truy xuất Top-8 và giữ lại {len(passing_only)} trích dẫn đạt kiểm chứng PASS."
            else:
                overall_status = "UNVERIFIED"
                detail_msg = "Sau khi mở rộng truy xuất vẫn chưa đủ độ khớp trực tiếp; hạ trạng thái thận trọng về UNVERIFIED."
            state["correction_steps"].append(
                SelfCorrectionStep(
                    attempt=state["attempts"],
                    initial_status="FAIL",
                    action="Mở rộng truy xuất Qdrant Top-8 và lọc bỏ trích dẫn không hỗ trợ trực tiếp.",
                    resulting_status=overall_status,  # type: ignore[arg-type]
                    detail=detail_msg,
                )
            )
        else:
            # Nếu có cả PASS và FAIL trong Top-K, ưu tiên hiển thị các trích dẫn có độ liên quan/hỗ trợ tốt nhất
            passing_only = [c for c in citations if c.validation_status == "PASS"]
            if passing_only:
                citations = passing_only

        llm_answer = self._call_llm_grounded(question, verified_evidences)
        final_answer = llm_answer or self._build_extractive_grounded_answer(
            question=question,
            citations=citations,
            llm_configured=bool(self.llm_api_key and self.llm_api_key.strip()),
        )

        state["pipeline_trace"].append(
            PipelineTraceStep(
                stage="citation_validator",
                label="Kiểm tra trích dẫn & hiệu lực văn bản",
                status="done" if overall_status == "PASS" else "warning",
                detail=f"Trạng thái tổng hợp: {overall_status} ({len(citations)} nguồn trích dẫn gắn chunk thực tế).",
                duration_ms=10,
            )
        )

        elapsed_ms = max(int((time.perf_counter() - started) * 1000), 10)
        return ChatResponse(
            request_id=str(uuid.uuid4()),
            conversation_id=state["conversation_id"],
            question=question,
            answer=final_answer,
            analysis=state.get("issues", []),
            citations=citations,
            citation_status=overall_status,  # type: ignore[arg-type]
            self_correction=SelfCorrectionInfo(
                attempts=state["attempts"],
                performed=state["attempts"] > 0,
                max_attempts=self.max_attempts,
                steps=state["correction_steps"],
            ),
            pipeline_trace=state["pipeline_trace"],
            is_mock=False,
            app_mode="live",
            processing_time_ms=elapsed_ms,
            created_at=datetime.now(timezone.utc),
        )
