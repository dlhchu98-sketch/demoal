"""
Dịch vụ tiếp nhận, chuẩn hóa, chia chunk, đồng bộ Qdrant và quản lý kho văn bản pháp luật thật.

Nguyên tắc bắt buộc:
- Chỉ tiếp nhận văn bản pháp luật thật từ thư mục `data/legal_documents/` (.txt, .json).
- Tuyệt đối không tự tạo văn bản pháp luật giả hay tự suy đoán ngày hiệu lực / trạng thái hiệu lực.
- Chống nạp trùng bằng SHA-256 checksum.
- Không tự động ghi đè dữ liệu cũ khi chưa xác định được phiên bản mới (trừ khi allow_update=True).
- Cập nhật hoặc xóa theo đúng `document_id`, không bao giờ xóa toàn bộ collection Qdrant.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from backend.app.core.config import PROJECT_ROOT, get_settings
from backend.app.core.database import IngestionLogORM, LegalChunkORM, LegalDocumentORM
from backend.app.schemas.legal import (
    IngestionFileResult,
    IngestionLogItem,
    LegalChunk,
    LegalDocumentChunksResponse,
    LegalDocumentDetailResponse,
    LegalDocumentListResponse,
    LegalDocumentsStatsResponse,
    LegalDocumentSummary,
    ScanAndIngestResponse,
)
from rag.pipeline import (
    SUPPORTED_EXTENSIONS,
    ChunkValidationError,
    LegalDocumentChunk,
    LegalDocumentParseError,
    ParsedLegalDocument,
    chunk_legal_document,
    clean_legal_text,
    parse_legal_document_file,
    validate_chunks,
)
from rag.retriever import (
    EmbeddingError,
    QdrantConnectionError,
    QdrantLegalRetriever,
)

logger = logging.getLogger(__name__)

EMPTY_CORPUS_MESSAGE = (
    "Chưa có dữ liệu văn bản pháp luật. Vui lòng thêm văn bản vào thư mục data/legal_documents/ và thực hiện đồng bộ."
)


class LegalIngestionService:
    def __init__(
        self,
        documents_dir: Path | None = None,
        retriever: QdrantLegalRetriever | None = None,
        project_root: Path | None = None,
    ) -> None:
        self._custom_documents_dir = documents_dir
        self._custom_retriever = retriever
        self._project_root = project_root or PROJECT_ROOT

    @property
    def documents_dir(self) -> Path:
        if self._custom_documents_dir is not None:
            self._custom_documents_dir.mkdir(parents=True, exist_ok=True)
            return self._custom_documents_dir
        settings = get_settings()
        settings.legal_documents_dir.mkdir(parents=True, exist_ok=True)
        return settings.legal_documents_dir

    def get_retriever(self) -> QdrantLegalRetriever:
        if self._custom_retriever is not None:
            return self._custom_retriever
        settings = get_settings()
        return QdrantLegalRetriever(
            qdrant_url=settings.qdrant_url,
            collection_name=settings.qdrant_collection,
            embedding_model=settings.embedding_model,
            qdrant_mode=settings.qdrant_mode,
            qdrant_local_path=settings.qdrant_local_path,
        )

    def _normalize_rel_path(self, file_path: Path) -> str:
        try:
            return file_path.resolve().relative_to(self._project_root.resolve()).as_posix()
        except ValueError:
            return file_path.resolve().as_posix()

    def _list_directory_files(self) -> list[Path]:
        if not self.documents_dir.exists():
            return []
        return sorted(
            [
                p
                for p in self.documents_dir.iterdir()
                if p.is_file() and not p.name.startswith(".")
            ],
            key=lambda p: p.name.lower(),
        )

    def _log_event(
        self,
        db: Session,
        *,
        file_path: str,
        action: str,
        status: str,
        message: str,
        document_id: str | None = None,
        checksum: str | None = None,
        chunk_count: int = 0,
    ) -> None:
        log_row = IngestionLogORM(
            id=f"LOG-{uuid.uuid4().hex[:12].upper()}",
            file_path=file_path,
            document_id=document_id,
            action=action,
            status=status,
            message=message,
            checksum=checksum,
            chunk_count=chunk_count,
            created_at=datetime.now(timezone.utc),
        )
        db.add(log_row)

    @staticmethod
    def _is_confirmed_newer_version(existing: LegalDocumentORM, parsed: ParsedLegalDocument) -> bool:
        """
        Chỉ coi là phiên bản mới nếu có căn cứ phiên bản hoặc ngày ban hành mới hơn rõ ràng.
        """
        if parsed.version and existing.version and parsed.version.strip() != existing.version.strip():
            return parsed.version.strip() > existing.version.strip()
        if parsed.issue_date and existing.issue_date and parsed.issue_date > existing.issue_date:
            return True
        return False

    def _build_chunks_for_parsed(
        self,
        parsed: ParsedLegalDocument,
        document_id: str,
        filename: str,
    ) -> list[LegalDocumentChunk]:
        if parsed.pre_structured_chunks:
            chunks: list[LegalDocumentChunk] = []
            for idx, item in enumerate(parsed.pre_structured_chunks, start=1):
                c_text = clean_legal_text(str(item.get("content", "")))
                if not c_text:
                    continue
                chunk_id = str(item.get("chunk_id") or f"{document_id}-chunk-{idx:04d}")
                chunks.append(
                    LegalDocumentChunk(
                        chunk_id=chunk_id,
                        document_id=document_id,
                        document_name=parsed.title,
                        document_number=parsed.document_number,
                        document_type=parsed.document_type,
                        issuing_authority=parsed.issuing_authority,
                        issue_date=parsed.issue_date,
                        effective_date=item.get("effective_date") or parsed.effective_date,
                        expiry_date=parsed.expiry_date,
                        document_status=parsed.status,
                        part=item.get("part"),
                        chapter=item.get("chapter"),
                        section=item.get("section"),
                        article=item.get("article"),
                        clause=item.get("clause"),
                        point=item.get("point"),
                        content=c_text,
                        embedding_text=f"{parsed.title} | {item.get('chapter') or ''} | {item.get('article') or ''}\n{c_text}".strip(),
                        source=item.get("source") or parsed.source,
                        source_file=filename,
                        page_number=item.get("page_number"),
                        chunk_index=idx,
                        needs_review=not bool(item.get("article") or item.get("chapter") or item.get("part")),
                    )
                )
            return chunks

        meta = {
            "document_id": document_id,
            "title": parsed.title,
            "document_number": parsed.document_number,
            "document_type": parsed.document_type,
            "issuing_authority": parsed.issuing_authority,
            "issue_date": parsed.issue_date,
            "effective_date": parsed.effective_date,
            "expiry_date": parsed.expiry_date,
            "status": parsed.status,
            "source": parsed.source,
        }
        return chunk_legal_document(parsed.content, filename=filename, metadata=meta, document_id=document_id)

    def ingest_file(
        self,
        db: Session,
        file_path: Path,
        *,
        allow_update: bool = False,
    ) -> IngestionFileResult:
        rel_path = self._normalize_rel_path(file_path)

        # 1. Đọc, kiểm tra định dạng, kiểm tra rỗng/lỗi & chuẩn hóa metadata
        try:
            parsed = parse_legal_document_file(file_path, project_root=self._project_root)
        except LegalDocumentParseError as exc:
            msg = str(exc)
            logger.warning("Lỗi đọc tệp pháp luật '%s': %s", rel_path, msg)
            self._log_event(db, file_path=rel_path, action="parse", status="error", message=msg)
            db.commit()
            return IngestionFileResult(
                file_path=rel_path,
                action="error",
                status="error",
                message=msg,
            )

        # 2. Chống nạp trùng bằng checksum SHA-256
        dup_by_checksum = db.execute(
            select(LegalDocumentORM).where(LegalDocumentORM.checksum == parsed.checksum)
        ).scalar_one_or_none()

        if dup_by_checksum is not None:
            if dup_by_checksum.qdrant_sync_status == "synced":
                msg = (
                    f"Tệp trùng lặp nội dung (checksum trùng với văn bản '{dup_by_checksum.title}', "
                    f"mã {dup_by_checksum.document_id}). Bỏ qua không nạp trùng."
                )
                self._log_event(
                    db,
                    file_path=rel_path,
                    document_id=dup_by_checksum.document_id,
                    action="skip_duplicate",
                    status="skipped",
                    message=msg,
                    checksum=parsed.checksum,
                    chunk_count=dup_by_checksum.chunk_count,
                )
                db.commit()
                return IngestionFileResult(
                    file_path=rel_path,
                    document_id=dup_by_checksum.document_id,
                    title=dup_by_checksum.title,
                    action="skipped_duplicate",
                    status="skipped",
                    message=msg,
                    chunk_count=dup_by_checksum.chunk_count,
                    qdrant_sync_status=dup_by_checksum.qdrant_sync_status,
                    needs_review=dup_by_checksum.needs_review,
                )
            # Nếu văn bản đã lưu DB nhưng trước đó đồng bộ Qdrant bị lỗi -> thử đồng bộ lại Qdrant
            return self._resync_existing_document_to_qdrant(db, dup_by_checksum, rel_path)

        # 3. Kiểm tra xung đột cập nhật (cùng đường dẫn file hoặc cùng số hiệu + tên nhưng khác checksum)
        existing_doc = db.execute(
            select(LegalDocumentORM).where(LegalDocumentORM.file_path == parsed.file_path)
        ).scalar_one_or_none()

        if existing_doc is None and parsed.document_number:
            existing_doc = db.execute(
                select(LegalDocumentORM).where(
                    LegalDocumentORM.document_number == parsed.document_number,
                    LegalDocumentORM.title == parsed.title,
                )
            ).scalar_one_or_none()

        is_update = False
        if existing_doc is not None:
            if not allow_update and not self._is_confirmed_newer_version(existing_doc, parsed):
                msg = (
                    f"Văn bản '{existing_doc.title}' ({existing_doc.document_id}) đã tồn tại nhưng nội dung file thay đổi "
                    f"và chưa xác định được phiên bản mới. Không tự động ghi đè; hãy chọn cập nhật có kiểm soát (allow_update=true)."
                )
                self._log_event(
                    db,
                    file_path=rel_path,
                    document_id=existing_doc.document_id,
                    action="conflict",
                    status="conflict",
                    message=msg,
                    checksum=parsed.checksum,
                )
                db.commit()
                return IngestionFileResult(
                    file_path=rel_path,
                    document_id=existing_doc.document_id,
                    title=existing_doc.title,
                    action="conflict_requires_update",
                    status="conflict",
                    message=msg,
                    chunk_count=existing_doc.chunk_count,
                    qdrant_sync_status=existing_doc.qdrant_sync_status,
                    needs_review=existing_doc.needs_review,
                )
            is_update = True
            document_id = existing_doc.document_id
        else:
            document_id = f"DOC-{uuid.uuid4().hex[:12].upper()}"

        # 4. Chia chunk theo cấu trúc pháp luật & kiểm tra tính toàn vẹn chunk trước khi lưu
        chunks = self._build_chunks_for_parsed(parsed, document_id=document_id, filename=file_path.name)
        valid, val_errors = validate_chunks(parsed.content, chunks)
        if not valid:
            err_msg = "Kiểm tra chunk trước khi lưu thất bại: " + "; ".join(val_errors)
            logger.error("Chunk validation failed for '%s': %s", rel_path, err_msg)
            self._log_event(
                db,
                file_path=rel_path,
                document_id=document_id,
                action="validate_chunks",
                status="error",
                message=err_msg,
                checksum=parsed.checksum,
            )
            db.commit()
            return IngestionFileResult(
                file_path=rel_path,
                document_id=document_id,
                title=parsed.title,
                action="error",
                status="error",
                message=err_msg,
            )

        needs_review = any(c.needs_review for c in chunks)
        review_note = (
            "Không nhận diện được cấu trúc Phần/Chương/Mục/Điều/Khoản/Điểm; đánh dấu cần kiểm tra thủ công (không tạo cấu trúc giả)."
            if needs_review
            else None
        )
        now = datetime.now(timezone.utc)

        # 5. Lưu / Cập nhật metadata và danh sách chunk vào DB
        if is_update and existing_doc is not None:
            existing_doc.title = parsed.title
            existing_doc.document_number = parsed.document_number
            existing_doc.document_type = parsed.document_type
            existing_doc.issuing_authority = parsed.issuing_authority
            existing_doc.issue_date = parsed.issue_date
            existing_doc.effective_date = parsed.effective_date
            existing_doc.expiry_date = parsed.expiry_date
            existing_doc.status = parsed.status
            existing_doc.source = parsed.source
            existing_doc.file_path = parsed.file_path
            existing_doc.checksum = parsed.checksum
            existing_doc.version = parsed.version
            existing_doc.chunk_count = len(chunks)
            existing_doc.qdrant_sync_status = "pending"
            existing_doc.qdrant_synced_chunks = 0
            existing_doc.needs_review = needs_review
            existing_doc.review_note = review_note
            existing_doc.last_error = None
            existing_doc.updated_at = now
            doc_row = existing_doc

            db.query(LegalChunkORM).filter(LegalChunkORM.document_id == document_id).delete()
        else:
            doc_row = LegalDocumentORM(
                document_id=document_id,
                title=parsed.title,
                document_number=parsed.document_number,
                document_type=parsed.document_type,
                issuing_authority=parsed.issuing_authority,
                issue_date=parsed.issue_date,
                effective_date=parsed.effective_date,
                expiry_date=parsed.expiry_date,
                status=parsed.status,
                source=parsed.source,
                file_path=parsed.file_path,
                checksum=parsed.checksum,
                version=parsed.version,
                chunk_count=len(chunks),
                qdrant_sync_status="pending",
                qdrant_synced_chunks=0,
                needs_review=needs_review,
                review_note=review_note,
                last_error=None,
                ingestion_date=now,
                updated_at=now,
            )
            db.add(doc_row)

        for ch in chunks:
            db.add(
                LegalChunkORM(
                    chunk_id=ch.chunk_id,
                    document_id=document_id,
                    chunk_index=ch.chunk_index,
                    document_number=ch.document_number,
                    document_title=ch.document_name,
                    part=ch.part,
                    chapter=ch.chapter,
                    section=ch.section,
                    article=ch.article,
                    clause=ch.clause,
                    point=ch.point,
                    content=ch.content,
                    source=ch.source,
                    page_number=ch.page_number,
                    effective_date=ch.effective_date,
                    needs_review=ch.needs_review,
                )
            )
        db.flush()

        # 6. Tạo embedding tiếng Việt & lưu vào Qdrant (kèm kiểm tra số lượng chunk trước/sau)
        retriever = self.get_retriever()
        try:
            sync_res = retriever.upsert_document_chunks(document_id=document_id, chunks=chunks)
            doc_row.qdrant_sync_status = "synced"
            doc_row.qdrant_synced_chunks = int(sync_res["synced_chunks"])
            doc_row.embedding_model = str(sync_res["embedding_model"])
            doc_row.qdrant_collection = str(sync_res["collection"])
            doc_row.last_error = None
            doc_row.updated_at = datetime.now(timezone.utc)

            action_name: Any = "updated" if is_update else "ingested"
            msg = (
                f"{'Cập nhật' if is_update else 'Nạp mới'} thành công '{doc_row.title}' "
                f"({len(chunks)} chunks đã xác minh trên Qdrant collection '{sync_res['collection']}')."
            )
            if needs_review:
                msg += " [Cảnh báo: chưa nhận diện được cấu trúc Điều/Khoản, cần kiểm tra.]"

            self._log_event(
                db,
                file_path=rel_path,
                document_id=document_id,
                action=action_name,
                status="success",
                message=msg,
                checksum=parsed.checksum,
                chunk_count=len(chunks),
            )
            db.commit()
            return IngestionFileResult(
                file_path=rel_path,
                document_id=document_id,
                title=doc_row.title,
                action=action_name,
                status="success",
                message=msg,
                chunk_count=len(chunks),
                qdrant_sync_status="synced",
                needs_review=needs_review,
            )
        except (QdrantConnectionError, EmbeddingError, Exception) as exc:
            err_msg = f"Đã lưu văn bản vào DB nhưng đồng bộ Qdrant thất bại: {exc}"
            logger.error("Qdrant sync error for document_id=%s: %s", document_id, exc)
            doc_row.qdrant_sync_status = "failed"
            doc_row.qdrant_synced_chunks = 0
            doc_row.last_error = str(exc)
            doc_row.updated_at = datetime.now(timezone.utc)
            self._log_event(
                db,
                file_path=rel_path,
                document_id=document_id,
                action="qdrant_sync",
                status="error",
                message=err_msg,
                checksum=parsed.checksum,
                chunk_count=len(chunks),
            )
            db.commit()
            return IngestionFileResult(
                file_path=rel_path,
                document_id=document_id,
                title=doc_row.title,
                action="error",
                status="error",
                message=err_msg,
                chunk_count=len(chunks),
                qdrant_sync_status="failed",
                needs_review=needs_review,
            )

    def _resync_existing_document_to_qdrant(
        self,
        db: Session,
        doc_row: LegalDocumentORM,
        rel_path: str,
    ) -> IngestionFileResult:
        chunk_rows = db.execute(
            select(LegalChunkORM)
            .where(LegalChunkORM.document_id == doc_row.document_id)
            .order_by(LegalChunkORM.chunk_index)
        ).scalars().all()
        chunks = [
            LegalDocumentChunk(
                chunk_id=r.chunk_id,
                document_id=r.document_id,
                document_name=r.document_title,
                document_number=r.document_number,
                document_type=doc_row.document_type,
                issuing_authority=doc_row.issuing_authority,
                issue_date=doc_row.issue_date,
                effective_date=r.effective_date,
                expiry_date=doc_row.expiry_date,
                document_status=doc_row.status,
                part=r.part,
                chapter=r.chapter,
                section=r.section,
                article=r.article,
                clause=r.clause,
                point=r.point,
                content=r.content,
                embedding_text=f"{r.document_title} | {r.chapter or ''} | {r.article or ''}\n{r.content}".strip(),
                source=r.source,
                source_file=Path(doc_row.file_path).name,
                page_number=r.page_number,
                chunk_index=r.chunk_index,
                needs_review=r.needs_review,
            )
            for r in chunk_rows
        ]
        retriever = self.get_retriever()
        try:
            sync_res = retriever.upsert_document_chunks(document_id=doc_row.document_id, chunks=chunks)
            doc_row.qdrant_sync_status = "synced"
            doc_row.qdrant_synced_chunks = int(sync_res["synced_chunks"])
            doc_row.embedding_model = str(sync_res["embedding_model"])
            doc_row.qdrant_collection = str(sync_res["collection"])
            doc_row.last_error = None
            doc_row.updated_at = datetime.now(timezone.utc)
            msg = f"Đã đồng bộ lại thành công '{doc_row.title}' ({len(chunks)} chunks) lên Qdrant."
            self._log_event(
                db,
                file_path=rel_path,
                document_id=doc_row.document_id,
                action="resync",
                status="success",
                message=msg,
                checksum=doc_row.checksum,
                chunk_count=len(chunks),
            )
            db.commit()
            return IngestionFileResult(
                file_path=rel_path,
                document_id=doc_row.document_id,
                title=doc_row.title,
                action="updated",
                status="success",
                message=msg,
                chunk_count=len(chunks),
                qdrant_sync_status="synced",
                needs_review=doc_row.needs_review,
            )
        except Exception as exc:
            err_msg = f"Đồng bộ lại Qdrant thất bại cho '{doc_row.title}': {exc}"
            doc_row.qdrant_sync_status = "failed"
            doc_row.last_error = str(exc)
            self._log_event(
                db,
                file_path=rel_path,
                document_id=doc_row.document_id,
                action="resync",
                status="error",
                message=err_msg,
                checksum=doc_row.checksum,
                chunk_count=len(chunks),
            )
            db.commit()
            return IngestionFileResult(
                file_path=rel_path,
                document_id=doc_row.document_id,
                title=doc_row.title,
                action="error",
                status="error",
                message=err_msg,
                chunk_count=len(chunks),
                qdrant_sync_status="failed",
                needs_review=doc_row.needs_review,
            )

    def scan_directory(
        self,
        db: Session,
        *,
        auto_ingest: bool = True,
        allow_update: bool = False,
    ) -> ScanAndIngestResponse:
        files = self._list_directory_files()
        dir_str = self._normalize_rel_path(self.documents_dir)

        if not files:
            return ScanAndIngestResponse(
                directory=dir_str,
                total_files_found=0,
                message=EMPTY_CORPUS_MESSAGE,
            )

        results: list[IngestionFileResult] = []
        for fpath in files:
            if auto_ingest:
                results.append(self.ingest_file(db, fpath, allow_update=allow_update))
            else:
                rel = self._normalize_rel_path(fpath)
                if fpath.suffix.lower() not in SUPPORTED_EXTENSIONS:
                    results.append(
                        IngestionFileResult(
                            file_path=rel,
                            action="error",
                            status="error",
                            message=f"Định dạng '{fpath.suffix}' không được hỗ trợ (.txt, .json).",
                        )
                    )
                    continue
                try:
                    parsed = parse_legal_document_file(fpath, project_root=self._project_root)
                except LegalDocumentParseError as exc:
                    results.append(
                        IngestionFileResult(file_path=rel, action="error", status="error", message=str(exc))
                    )
                    continue

                dup = db.execute(
                    select(LegalDocumentORM).where(LegalDocumentORM.checksum == parsed.checksum)
                ).scalar_one_or_none()
                if dup is not None:
                    results.append(
                        IngestionFileResult(
                            file_path=rel,
                            document_id=dup.document_id,
                            title=dup.title,
                            action="skipped_duplicate",
                            status="skipped",
                            message="Đã nạp trước đó (trùng checksum).",
                            chunk_count=dup.chunk_count,
                            qdrant_sync_status=dup.qdrant_sync_status,
                        )
                    )
                else:
                    results.append(
                        IngestionFileResult(
                            file_path=rel,
                            title=parsed.title,
                            action="detected_new",
                            status="success",
                            message="Phát hiện tệp văn bản mới sẵn sàng nạp.",
                        )
                    )

        ingested = sum(1 for r in results if r.action == "ingested")
        updated = sum(1 for r in results if r.action == "updated")
        skipped = sum(1 for r in results if r.action == "skipped_duplicate")
        conflicts = sum(1 for r in results if r.action == "conflict_requires_update")
        errors = sum(1 for r in results if r.status == "error")

        summary_msg = (
            f"Quét thư mục hoàn tất ({len(files)} tệp): "
            f"nạp mới {ingested}, cập nhật {updated}, bỏ qua trùng lặp {skipped}, "
            f"cần xác nhận cập nhật {conflicts}, lỗi {errors}."
        )
        return ScanAndIngestResponse(
            directory=dir_str,
            total_files_found=len(files),
            ingested_count=ingested,
            updated_count=updated,
            skipped_duplicate_count=skipped,
            conflict_count=conflicts,
            error_count=errors,
            results=results,
            message=summary_msg,
        )

    def resolve_target_file(self, file_path_str: str) -> Path:
        """Giải quyết đường dẫn file an toàn nằm trong thư mục `data/legal_documents/`."""
        candidate = Path(file_path_str)
        if not candidate.is_absolute():
            if (self.documents_dir / candidate).exists():
                candidate = self.documents_dir / candidate
            elif (self._project_root / candidate).exists():
                candidate = self._project_root / candidate
            else:
                candidate = self.documents_dir / candidate.name

        resolved_dir = self.documents_dir.resolve()
        resolved_target = candidate.resolve()
        try:
            resolved_target.relative_to(resolved_dir)
        except ValueError as exc:
            raise ValueError("Đường dẫn tệp phải nằm trong thư mục data/legal_documents/.") from exc
        return resolved_target

    def save_uploaded_legal_file(
        self,
        db: Session,
        filename: str,
        content: bytes,
        *,
        allow_update: bool = False,
    ) -> IngestionFileResult:
        safe_name = Path(filename).name
        suffix = Path(safe_name).suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            msg = f"Định dạng tệp '{suffix or '(không có đuôi)'}' không được hỗ trợ. Chỉ chấp nhận .txt và .json."
            self._log_event(db, file_path=safe_name, action="upload", status="error", message=msg)
            db.commit()
            raise LegalDocumentParseError(msg)

        if not content or not content.strip():
            msg = f"Tệp '{safe_name}' rỗng, không có nội dung để nạp."
            self._log_event(db, file_path=safe_name, action="upload", status="error", message=msg)
            db.commit()
            raise LegalDocumentParseError(msg)

        target = self.documents_dir / safe_name
        # Không tự ghi đè file vật lý cũ nếu file đã tồn tại với nội dung khác và chưa bật allow_update
        if target.exists() and not allow_update:
            old_bytes = target.read_bytes()
            if old_bytes != content:
                rel = self._normalize_rel_path(target)
                msg = (
                    f"Tệp '{safe_name}' đã tồn tại với nội dung khác. "
                    f"Bật tùy chọn cập nhật (allow_update=true) để ghi đè có kiểm soát."
                )
                self._log_event(db, file_path=rel, action="conflict", status="conflict", message=msg)
                db.commit()
                return IngestionFileResult(
                    file_path=rel,
                    action="conflict_requires_update",
                    status="conflict",
                    message=msg,
                )

        target.write_bytes(content)
        return self.ingest_file(db, target, allow_update=allow_update)

    @staticmethod
    def _to_summary(row: LegalDocumentORM) -> LegalDocumentSummary:
        return LegalDocumentSummary(
            document_id=row.document_id,
            title=row.title,
            document_number=row.document_number,
            document_type=row.document_type,
            issuing_authority=row.issuing_authority,
            issue_date=row.issue_date,
            effective_date=row.effective_date,
            expiry_date=row.expiry_date,
            status=row.status,
            source=row.source,
            file_path=row.file_path,
            checksum=row.checksum,
            ingestion_date=row.ingestion_date,
            updated_at=row.updated_at,
            version=row.version,
            chunk_count=row.chunk_count,
            qdrant_sync_status=row.qdrant_sync_status,
            qdrant_synced_chunks=row.qdrant_synced_chunks,
            embedding_model=row.embedding_model,
            qdrant_collection=row.qdrant_collection,
            needs_review=row.needs_review,
            review_note=row.review_note,
            last_error=row.last_error,
        )

    @staticmethod
    def _to_chunk(row: LegalChunkORM) -> LegalChunk:
        return LegalChunk(
            chunk_id=row.chunk_id,
            document_id=row.document_id,
            document_number=row.document_number,
            document_title=row.document_title,
            part=row.part,
            chapter=row.chapter,
            section=row.section,
            article=row.article,
            clause=row.clause,
            point=row.point,
            content=row.content,
            source=row.source,
            page_number=row.page_number,
            effective_date=row.effective_date,
            chunk_index=row.chunk_index,
            needs_review=row.needs_review,
        )

    def list_documents(
        self,
        db: Session,
        *,
        search: str | None = None,
        document_type: str | None = None,
        issuing_authority: str | None = None,
        status: str | None = None,
        qdrant_sync_status: str | None = None,
    ) -> LegalDocumentListResponse:
        all_rows = db.execute(
            select(LegalDocumentORM).order_by(desc(LegalDocumentORM.ingestion_date))
        ).scalars().all()

        dir_files = self._list_directory_files()
        known_paths = {r.file_path for r in all_rows}
        pending_files = sum(1 for f in dir_files if self._normalize_rel_path(f) not in known_paths)

        all_types = sorted({r.document_type for r in all_rows if r.document_type})
        all_authorities = sorted({r.issuing_authority for r in all_rows if r.issuing_authority})
        all_statuses = sorted({r.status for r in all_rows if r.status})

        if not all_rows:
            return LegalDocumentListResponse(
                loaded=False,
                total_documents=0,
                total_chunks=0,
                synced_documents=0,
                failed_documents=0,
                pending_files_in_dir=pending_files,
                document_types=[],
                issuing_authorities=[],
                statuses=[],
                items=[],
                note=EMPTY_CORPUS_MESSAGE,
            )

        filtered = list(all_rows)
        if document_type and document_type.strip():
            dt = document_type.strip().lower()
            filtered = [r for r in filtered if (r.document_type or "chưa xác định").lower() == dt]

        if issuing_authority and issuing_authority.strip():
            ia = issuing_authority.strip().lower()
            filtered = [r for r in filtered if (r.issuing_authority or "chưa xác định").lower() == ia]

        if status and status.strip():
            st = status.strip().lower()
            filtered = [r for r in filtered if (r.status or "chưa xác định").lower() == st]

        if qdrant_sync_status and qdrant_sync_status.strip():
            qs = qdrant_sync_status.strip().lower()
            filtered = [r for r in filtered if (r.qdrant_sync_status or "").lower() == qs]

        if search and search.strip():
            term = search.strip().lower()
            filtered = [
                r
                for r in filtered
                if term in r.title.lower()
                or (r.document_number and term in r.document_number.lower())
                or (r.issuing_authority and term in r.issuing_authority.lower())
                or (r.document_type and term in r.document_type.lower())
                or term in r.file_path.lower()
            ]

        synced_cnt = sum(1 for r in all_rows if r.qdrant_sync_status == "synced")
        failed_cnt = sum(1 for r in all_rows if r.qdrant_sync_status == "failed")
        total_chunks_filtered = sum(r.chunk_count for r in filtered)

        return LegalDocumentListResponse(
            loaded=True,
            total_documents=len(filtered),
            total_chunks=total_chunks_filtered,
            synced_documents=synced_cnt,
            failed_documents=failed_cnt,
            pending_files_in_dir=pending_files,
            document_types=all_types,
            issuing_authorities=all_authorities,
            statuses=all_statuses,
            items=[self._to_summary(r) for r in filtered],
            note=(
                f"Đang quản lý {len(all_rows)} văn bản pháp luật thực tế "
                f"({synced_cnt} đồng bộ Qdrant thành công, {failed_cnt} lỗi)."
            ),
        )

    def get_document_detail(self, db: Session, document_id: str) -> LegalDocumentDetailResponse | None:
        row = db.get(LegalDocumentORM, document_id)
        if row is None:
            return None
        chunk_rows = db.execute(
            select(LegalChunkORM)
            .where(LegalChunkORM.document_id == document_id)
            .order_by(LegalChunkORM.chunk_index)
        ).scalars().all()
        summary = self._to_summary(row)
        return LegalDocumentDetailResponse(
            **summary.model_dump(),
            chunks=[self._to_chunk(c) for c in chunk_rows],
        )

    def get_document_chunks(
        self,
        db: Session,
        document_id: str,
        *,
        search: str | None = None,
        article: str | None = None,
    ) -> LegalDocumentChunksResponse | None:
        doc = db.get(LegalDocumentORM, document_id)
        if doc is None:
            return None
        rows = db.execute(
            select(LegalChunkORM)
            .where(LegalChunkORM.document_id == document_id)
            .order_by(LegalChunkORM.chunk_index)
        ).scalars().all()

        if article and article.strip():
            art_q = article.strip().lower()
            rows = [r for r in rows if r.article and art_q in r.article.lower()]
        if search and search.strip():
            term = search.strip().lower()
            rows = [
                r
                for r in rows
                if term in r.content.lower()
                or (r.article and term in r.article.lower())
                or (r.chapter and term in r.chapter.lower())
                or (r.clause and term in r.clause.lower())
            ]

        return LegalDocumentChunksResponse(
            document_id=doc.document_id,
            document_title=doc.title,
            document_number=doc.document_number,
            total_chunks=len(rows),
            needs_review=doc.needs_review,
            items=[self._to_chunk(r) for r in rows],
        )

    def delete_document(
        self,
        db: Session,
        document_id: str,
        *,
        delete_source_file: bool = False,
    ) -> dict[str, Any] | None:
        doc = db.get(LegalDocumentORM, document_id)
        if doc is None:
            return None

        retriever = self.get_retriever()
        deleted_vectors = 0
        qdrant_warning: str | None = None
        try:
            deleted_vectors = retriever.delete_document_vectors(document_id)
        except Exception as exc:
            # Nếu văn bản đã sync trước đó mà Qdrant mất kết nối, báo lỗi rõ ràng thay vì âm thầm để vector mồ côi
            if doc.qdrant_sync_status == "synced":
                raise QdrantConnectionError(
                    f"Không thể xóa vector của văn bản '{doc.title}' trên Qdrant: {exc}"
                ) from exc
            qdrant_warning = str(exc)

        deleted_chunks = (
            db.query(LegalChunkORM).filter(LegalChunkORM.document_id == document_id).delete()
        )
        file_path_str = doc.file_path
        title = doc.title
        db.delete(doc)

        file_deleted = False
        if delete_source_file:
            candidate = self._project_root / file_path_str
            if candidate.exists() and candidate.is_file():
                try:
                    candidate.resolve().relative_to(self.documents_dir.resolve())
                    candidate.unlink()
                    file_deleted = True
                except Exception:
                    file_deleted = False

        self._log_event(
            db,
            file_path=file_path_str,
            document_id=document_id,
            action="deleted",
            status="success",
            message=f"Đã xóa văn bản '{title}' ({deleted_chunks} chunks DB, {deleted_vectors} vectors Qdrant).",
            chunk_count=deleted_chunks,
        )
        db.commit()
        return {
            "status": "deleted",
            "document_id": document_id,
            "title": title,
            "deleted_chunks": deleted_chunks,
            "deleted_vectors": deleted_vectors,
            "source_file_deleted": file_deleted,
            "qdrant_warning": qdrant_warning,
        }

    def get_stats(self, db: Session, log_limit: int = 25) -> LegalDocumentsStatsResponse:
        rows = db.execute(select(LegalDocumentORM)).scalars().all()
        logs = db.execute(
            select(IngestionLogORM).order_by(desc(IngestionLogORM.created_at)).limit(log_limit)
        ).scalars().all()

        retriever = self.get_retriever()
        q_stats = retriever.get_collection_stats()
        settings = get_settings()

        synced = sum(1 for r in rows if r.qdrant_sync_status == "synced")
        failed = sum(1 for r in rows if r.qdrant_sync_status == "failed")
        pending = sum(1 for r in rows if r.qdrant_sync_status not in {"synced", "failed"})
        needs_review = sum(1 for r in rows if r.needs_review)
        total_chunks = sum(r.chunk_count for r in rows)

        active_model = next((r.embedding_model for r in rows if r.embedding_model), settings.embedding_model)
        files_in_dir = len(self._list_directory_files())

        return LegalDocumentsStatsResponse(
            total_documents=len(rows),
            total_chunks=total_chunks,
            synced_documents=synced,
            failed_documents=failed,
            pending_documents=pending,
            needs_review_documents=needs_review,
            qdrant_connected=bool(q_stats["connected"]),
            qdrant_backend=str(q_stats["backend"]),
            qdrant_collection=str(q_stats["collection"]),
            qdrant_points_count=int(q_stats["points_count"]),
            qdrant_detail=str(q_stats["detail"]),
            embedding_model=active_model,
            documents_dir=self._normalize_rel_path(self.documents_dir),
            files_in_dir=files_in_dir,
            document_types=sorted({r.document_type for r in rows if r.document_type}),
            issuing_authorities=sorted({r.issuing_authority for r in rows if r.issuing_authority}),
            recent_logs=[
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
                for lg in logs
            ],
        )

    def update_document_metadata(
        self,
        db: Session,
        document_id: str,
        updates: dict[str, Any],
    ) -> LegalDocumentSummary | None:
        doc = db.get(LegalDocumentORM, document_id)
        if doc is None:
            return None

        allowed_fields = {
            "title",
            "document_number",
            "document_type",
            "issuing_authority",
            "issue_date",
            "effective_date",
            "expiry_date",
            "status",
            "source",
            "version",
        }
        changed = False
        for key, val in updates.items():
            if key in allowed_fields and val is not None:
                cleaned = val.strip() if isinstance(val, str) else val
                setattr(doc, key, cleaned or None if key != "title" else (cleaned or doc.title))
                changed = True

        if changed:
            doc.updated_at = datetime.now(timezone.utc)
            # Cập nhật lại các trường metadata phản chiếu trên bảng chunk
            chunks = db.execute(
                select(LegalChunkORM).where(LegalChunkORM.document_id == document_id)
            ).scalars().all()
            for ch in chunks:
                ch.document_title = doc.title
                ch.document_number = doc.document_number
                if doc.effective_date:
                    ch.effective_date = doc.effective_date
                if doc.source:
                    ch.source = doc.source
            self._log_event(
                db,
                file_path=doc.file_path,
                document_id=document_id,
                action="metadata_updated",
                status="success",
                message=f"Đã cập nhật metadata cho văn bản '{doc.title}'.",
                checksum=doc.checksum,
                chunk_count=doc.chunk_count,
            )
            db.commit()
            db.refresh(doc)
        return self._to_summary(doc)

    def reingest_document(self, db: Session, document_id: str) -> IngestionFileResult | None:
        doc = db.get(LegalDocumentORM, document_id)
        if doc is None:
            return None
        candidate = self._project_root / doc.file_path
        if candidate.exists() and candidate.is_file():
            return self.ingest_file(db, candidate, allow_update=True)
        return self._resync_existing_document_to_qdrant(db, doc, doc.file_path)

    def resync_failed_documents(self, db: Session) -> ScanAndIngestResponse:
        """Đồng bộ lại lên Qdrant tất cả văn bản đang ở trạng thái failed hoặc pending."""
        rows = db.execute(
            select(LegalDocumentORM).where(LegalDocumentORM.qdrant_sync_status != "synced")
        ).scalars().all()
        results: list[IngestionFileResult] = []
        for doc in rows:
            results.append(self._resync_existing_document_to_qdrant(db, doc, doc.file_path))

        updated = sum(1 for r in results if r.status == "success")
        errors = sum(1 for r in results if r.status == "error")
        msg = (
            f"Đã đồng bộ lại {len(rows)} văn bản chưa đồng bộ Qdrant: thành công {updated}, lỗi {errors}."
            if rows
            else "Tất cả văn bản hiện đều đã đồng bộ Qdrant thành công."
        )
        return ScanAndIngestResponse(
            directory=self._normalize_rel_path(self.documents_dir),
            total_files_found=len(rows),
            updated_count=updated,
            error_count=errors,
            results=results,
            message=msg,
        )


legal_ingestion_service = LegalIngestionService()
