from __future__ import annotations

import json
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.database import (
    CitationRecordORM,
    EvaluationRunORM,
    LegalChunkORM,
    LegalDocumentORM,
    QueryHistoryORM,
)
from backend.app.schemas.legal import (
    CitationLogItem,
    DocumentsResponse,
    EvaluationResultsResponse,
    EvaluationRunRequest,
    EvaluationVariantMetric,
    LegalChunk,
    LegalDocumentItem,
    QuestionCategory,
    QuestionItem,
    QuestionsResponse,
    StatisticsResponse,
)
from backend.app.services.docx_parser import export_questions_json, parse_legal_questions_docx
from backend.app.services.legal_ingestion_service import EMPTY_CORPUS_MESSAGE
from evaluation.runner import DIFFICULTY_SPLITS, EVALUATION_VARIANTS


class LegalDataService:
    def __init__(self) -> None:
        self._cached_docx_mtime: float | None = None
        self._cached_docx_path: Path | None = None
        self._categories: list[QuestionCategory] = []
        self._questions: list[QuestionItem] = []

    def _find_question_docx(self) -> Path | None:
        settings = get_settings()
        candidates = sorted(settings.questions_dir.glob("*.docx"))
        if candidates:
            return candidates[0]
        return None

    def _load_questions_if_needed(self) -> tuple[bool, Path | None]:
        docx_path = self._find_question_docx()
        if docx_path is None or not docx_path.exists():
            self._cached_docx_mtime = None
            self._cached_docx_path = None
            self._categories = []
            self._questions = []
            return False, None

        mtime = docx_path.stat().st_mtime
        if self._cached_docx_path == docx_path and self._cached_docx_mtime == mtime:
            return True, docx_path

        categories, questions = parse_legal_questions_docx(docx_path)
        self._categories = categories
        self._questions = questions
        self._cached_docx_path = docx_path
        self._cached_docx_mtime = mtime

        # Tự động đồng bộ JSON dataset (chỉ là QUESTION DATASET, tuyệt đối không nạp vào Qdrant)
        try:
            export_questions_json(docx_path, docx_path.parent)
        except Exception:
            pass

        return True, docx_path

    def get_categories(self) -> tuple[bool, list[QuestionCategory], str | None]:
        loaded, path = self._load_questions_if_needed()
        return loaded, self._categories, (path.name if path else None)

    def get_questions(
        self,
        search: str | None = None,
        category_id: int | None = None,
        domain: str | None = None,
        difficulty: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> QuestionsResponse:
        loaded, path = self._load_questions_if_needed()
        if not loaded:
            return QuestionsResponse(
                loaded=False,
                source_file=None,
                expected_categories=17,
                total_domains=0,
                total_categories=0,
                total_questions=0,
                domains=[],
                difficulties=[],
                page=page,
                page_size=page_size,
                items=[],
                note=(
                    "Chưa tìm thấy tệp 'Bộ câu hỏi pháp luật.docx' trong thư mục data/questions/. "
                    "Bạn có thể tải tệp .docx lên trực tiếp hoặc chép vào data/questions/ để tự động phân loại."
                ),
            )

        all_domains = sorted({c.domain for c in self._categories})
        all_difficulties = ["Easy", "Medium", "Multi-document", "Hard", "Citation-focused"]

        filtered = self._questions
        if domain and domain.strip():
            dom_q = domain.strip().lower()
            filtered = [q for q in filtered if q.domain.lower() == dom_q]
        if category_id is not None:
            filtered = [q for q in filtered if q.category_id == category_id]
        if difficulty and difficulty.strip():
            diff_q = difficulty.strip().lower()
            filtered = [q for q in filtered if q.difficulty.lower() == diff_q]
        if search and search.strip():
            term = search.strip().lower()
            filtered = [
                q
                for q in filtered
                if term in q.question.lower()
                or term in q.category_name.lower()
                or term in q.domain.lower()
            ]

        total = len(filtered)
        start = max((page - 1) * page_size, 0)
        end = start + page_size
        return QuestionsResponse(
            loaded=True,
            source_file=path.name if path else None,
            expected_categories=len(self._categories),
            total_domains=len(all_domains),
            total_categories=len(self._categories),
            total_questions=total,
            domains=all_domains,
            difficulties=all_difficulties,
            page=page,
            page_size=page_size,
            items=filtered[start:end],
            note=(
                f"Đã đọc trực tiếp từ {path.name} ({len(all_domains)} lĩnh vực lớn, "
                f"{len(self._categories)} nhóm chủ đề, {len(self._questions)} câu hỏi — QUESTION DATASET, không nạp vào Qdrant)."
            ),
        )

    def save_uploaded_question_docx(self, filename: str, content: bytes) -> QuestionsResponse:
        settings = get_settings()
        safe_name = Path(filename).name
        if not safe_name.lower().endswith(".docx"):
            raise ValueError("Chỉ hỗ trợ tệp định dạng .docx (Bộ câu hỏi pháp luật.docx).")
        target = settings.questions_dir / safe_name
        target.write_bytes(content)
        self._cached_docx_mtime = None
        return self.get_questions(page=1, page_size=20)

    def get_documents(
        self,
        db: Session | None = None,
        search: str | None = None,
        doc_type: str | None = None,
    ) -> DocumentsResponse:
        if db is None:
            from backend.app.core.database import SessionLocal

            with SessionLocal() as local_db:
                return self.get_documents(db=local_db, search=search, doc_type=doc_type)

        rows = db.execute(
            select(LegalDocumentORM).order_by(desc(LegalDocumentORM.ingestion_date))
        ).scalars().all()

        if not rows:
            return DocumentsResponse(
                loaded=False,
                total_documents=0,
                total_chunks=0,
                document_types=[],
                items=[],
                note=EMPTY_CORPUS_MESSAGE,
            )

        types_set = sorted({r.document_type or "Chưa xác định" for r in rows})
        filtered_rows = list(rows)
        if doc_type and doc_type.strip():
            dt = doc_type.strip().lower()
            filtered_rows = [r for r in filtered_rows if (r.document_type or "Chưa xác định").lower() == dt]
        if search and search.strip():
            term = search.strip().lower()
            filtered_rows = [
                r
                for r in filtered_rows
                if term in r.title.lower()
                or (r.document_number and term in r.document_number.lower())
                or (r.issuing_authority and term in r.issuing_authority.lower())
            ]

        items: list[LegalDocumentItem] = []
        for r in filtered_rows:
            chunk_rows = db.execute(
                select(LegalChunkORM)
                .where(LegalChunkORM.document_id == r.document_id)
                .order_by(LegalChunkORM.chunk_index)
            ).scalars().all()
            chunks = [
                LegalChunk(
                    chunk_id=c.chunk_id,
                    document_id=c.document_id,
                    document_number=c.document_number,
                    document_title=c.document_title,
                    part=c.part,
                    chapter=c.chapter,
                    section=c.section,
                    article=c.article,
                    clause=c.clause,
                    point=c.point,
                    content=c.content,
                    source=c.source,
                    page_number=c.page_number,
                    effective_date=c.effective_date,
                    chunk_index=c.chunk_index,
                    needs_review=c.needs_review,
                )
                for c in chunk_rows
            ]
            items.append(
                LegalDocumentItem(
                    id=r.document_id,
                    title=r.title,
                    document_number=r.document_number,
                    document_type=r.document_type or "Chưa xác định",
                    issuing_authority=r.issuing_authority,
                    issued_date=r.issue_date,
                    effective_date=r.effective_date,
                    status=r.status,
                    source_file=Path(r.file_path).name,
                    qdrant_sync_status=r.qdrant_sync_status,
                    chunks=chunks,
                )
            )

        return DocumentsResponse(
            loaded=True,
            total_documents=len(items),
            total_chunks=sum(len(d.chunks) for d in items),
            document_types=types_set,
            items=items,
            note=f"Đã nạp {len(rows)} văn bản pháp luật thực tế từ data/legal_documents/.",
        )

    def get_citations(
        self,
        db: Session,
        status: str | None = None,
        limit: int = 100,
    ) -> list[CitationLogItem]:
        stmt = select(CitationRecordORM).order_by(desc(CitationRecordORM.created_at)).limit(limit)
        if status and status.upper() in {"PASS", "FAIL", "UNVERIFIED"}:
            stmt = stmt.where(CitationRecordORM.validation_status == status.upper())
        rows = db.execute(stmt).scalars().all()
        return [
            CitationLogItem(
                id=r.id,
                request_id=r.request_id,
                question=r.question,
                claim=r.claim,
                document_name=r.document_name,
                document_number=r.document_number,
                article=r.article,
                clause=r.clause,
                point=r.point,
                evidence=r.evidence,
                validation_status=r.validation_status,  # type: ignore[arg-type]
                validation_reason=r.validation_reason,
                relevance_score=r.relevance_score,
                is_mock=r.is_mock,
                created_at=r.created_at,
            )
            for r in rows
        ]

    def get_statistics(self, db: Session, current_mode: str) -> StatisticsResponse:
        loaded_q, categories, _ = self.get_categories()
        total_documents = db.query(LegalDocumentORM).count()

        history_rows = db.execute(select(QueryHistoryORM).order_by(QueryHistoryORM.created_at)).scalars().all()
        total_queries = len(history_rows)
        pass_count = sum(1 for h in history_rows if h.citation_status == "PASS")
        fail_count = sum(1 for h in history_rows if h.citation_status == "FAIL")
        unverified_count = sum(1 for h in history_rows if h.citation_status == "UNVERIFIED")

        verified_total = pass_count + fail_count
        pass_rate = round((pass_count / verified_total) * 100, 1) if verified_total > 0 else None
        avg_ms = (
            round(sum(h.processing_time_ms for h in history_rows) / total_queries, 1)
            if total_queries > 0
            else None
        )

        by_day: dict[str, int] = defaultdict(int)
        for h in history_rows:
            day_key = h.created_at.strftime("%Y-%m-%d") if h.created_at else "N/A"
            by_day[day_key] += 1

        queries_over_time = [{"date": d, "count": c} for d, c in sorted(by_day.items())]
        questions_by_category = (
            [{"category": c.name, "domain": c.domain, "count": c.question_count} for c in categories]
            if loaded_q
            else []
        )

        is_demo_data = current_mode == "demo" or any(h.is_mock for h in history_rows)
        return StatisticsResponse(
            app_mode=current_mode,
            is_demo_data=is_demo_data,
            total_question_categories=len(categories),
            expected_question_categories=len(categories) if loaded_q else 17,
            total_questions=len(self._questions),
            total_documents=total_documents,
            total_queries=total_queries,
            pass_count=pass_count,
            fail_count=fail_count,
            unverified_count=unverified_count,
            pass_rate=pass_rate,
            avg_response_time_ms=avg_ms,
            queries_over_time=queries_over_time,
            questions_by_category=questions_by_category,
        )

    def get_latest_evaluation(self, db: Session, current_mode: str) -> EvaluationResultsResponse:
        row = db.execute(select(EvaluationRunORM).order_by(desc(EvaluationRunORM.created_at)).limit(1)).scalar_one_or_none()
        if row is None:
            return EvaluationResultsResponse(
                has_results=False,
                run_id=None,
                run_mode=current_mode,
                is_mock=current_mode == "demo",
                dataset_size=0,
                difficulty_splits=DIFFICULTY_SPLITS,
                variants=[EvaluationVariantMetric(variant=v) for v in EVALUATION_VARIANTS],
                note=(
                    "Chưa có dữ liệu thực nghiệm đánh giá 4 phiên bản. "
                    "Hệ thống giữ trống các chỉ số (N/A) theo nguyên tắc trung thực khoa học — tuyệt đối không bịa số liệu benchmark."
                ),
                created_at=None,
            )

        parsed = json.loads(row.results_json)
        return EvaluationResultsResponse(
            has_results=True,
            run_id=row.id,
            run_mode=row.run_mode,
            is_mock=row.is_mock,
            dataset_size=row.dataset_size,
            difficulty_splits=DIFFICULTY_SPLITS,
            variants=[EvaluationVariantMetric(**v) for v in parsed],
            note=row.summary_note,
            created_at=row.created_at,
        )

    def run_evaluation(
        self,
        db: Session,
        payload: EvaluationRunRequest,
        current_mode: str,
    ) -> EvaluationResultsResponse:
        loaded_q, _, _ = self.get_categories()
        has_docs = db.query(LegalDocumentORM).count() > 0
        run_id = f"EVAL-{uuid.uuid4().hex[:8].upper()}"

        if current_mode == "live" and loaded_q and has_docs:
            note = (
                "Đã khởi tạo cấu hình đánh giá 4 phiên bản (Model A..D). "
                "Để tính chính xác Answer Accuracy, Recall@K và Citation Support Rate, cần hoàn thiện Ground Truth được kiểm duyệt trong data/questions/benchmark_questions.json."
            )
            is_mock = False
        else:
            note = (
                "Không thể tạo số liệu thực nghiệm thật vì thiếu kho văn bản pháp luật nạp vào Qdrant hoặc hệ thống đang ở chế độ DEMO. "
                "Hệ thống giữ trống các chỉ số (N/A) theo nguyên tắc trung thực khoa học — tuyệt đối không bịa số liệu benchmark."
            )
            is_mock = True

        variants = [EvaluationVariantMetric(variant=v) for v in EVALUATION_VARIANTS]
        record = EvaluationRunORM(
            id=run_id,
            run_mode=current_mode,
            is_mock=is_mock,
            dataset_size=min(payload.sample_size, len(self._questions)) if loaded_q else 0,
            summary_note=note,
            results_json=json.dumps([v.model_dump() for v in variants], ensure_ascii=False),
            created_at=datetime.now(timezone.utc),
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return self.get_latest_evaluation(db, current_mode)


data_service = LegalDataService()
