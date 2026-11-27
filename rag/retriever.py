"""
Module Embedding tiếng Việt & Truy xuất Vector trên Qdrant (RAG).
Hỗ trợ:
- Tạo embedding tiếng Việt (ưu tiên sentence-transformers nếu cài đặt, hoặc fastembed ONNX đa ngôn ngữ hỗ trợ tiếng Việt).
- Kết nối Qdrant Server (remote URL) hoặc Qdrant Local Persistent Storage (path trên đĩa).
- Upsert / Cập nhật / Xóa vector theo từng document_id (không xóa toàn bộ collection).
- Kiểm tra số lượng chunk trước và sau khi lưu vào Qdrant.
- Xử lý lỗi rõ ràng khi Qdrant mất kết nối.
"""

from __future__ import annotations

import atexit
import logging
import re
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import httpx

from rag.pipeline import LegalDocumentChunk

logger = logging.getLogger(__name__)

DEFAULT_FASTEMBED_VI_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


class QdrantConnectionError(RuntimeError):
    """Lỗi kết nối hoặc thao tác với Qdrant Vector Database."""


class EmbeddingError(RuntimeError):
    """Lỗi khi tạo vector embedding cho văn bản pháp luật."""


@dataclass
class RetrievedEvidence:
    document_name: str
    document_number: str | None
    article: str | None
    clause: str | None
    point: str | None
    content: str
    relevance_score: float
    source_file: str | None = None
    chunk_id: str | None = None
    document_id: str | None = None
    chapter: str | None = None
    part: str | None = None
    section: str | None = None
    source: str | None = None
    page_number: int | None = None
    effective_date: str | None = None
    expiry_date: str | None = None
    document_status: str | None = None


class LegalRetrieverProtocol(Protocol):
    def is_available(self) -> tuple[bool, str]: ...
    def search(self, query: str, top_k: int = 5) -> list[RetrievedEvidence]: ...


# ---------------------------------------------------------------------------
# Singleton caches (tránh load lại model ONNX và tránh xung đột lock Qdrant local)
# ---------------------------------------------------------------------------
_EMBEDDER_LOCK = threading.Lock()
_EMBEDDER_CACHE: dict[str, "VietnameseEmbedder"] = {}

_LOCAL_QDRANT_LOCK = threading.Lock()
_LOCAL_QDRANT_CLIENTS: dict[str, Any] = {}


def close_local_qdrant_client(path: str) -> None:
    """Đóng client Qdrant local theo đường dẫn (hữu ích khi dọn dẹp test)."""
    resolved = str(Path(path).resolve())
    with _LOCAL_QDRANT_LOCK:
        client = _LOCAL_QDRANT_CLIENTS.pop(resolved, None)
        if client is not None:
            try:
                client.close()
            except Exception:
                pass


def _close_all_local_qdrant_clients() -> None:
    with _LOCAL_QDRANT_LOCK:
        for client in list(_LOCAL_QDRANT_CLIENTS.values()):
            try:
                client.close()
            except Exception:
                pass
        _LOCAL_QDRANT_CLIENTS.clear()


atexit.register(_close_all_local_qdrant_clients)


class VietnameseEmbedder:
    """
    Trình tạo vector embedding cho tiếng Việt.
    - Nếu `sentence-transformers` có sẵn và model được cấu hình phù hợp (vd: bkai-foundation-models/vietnamese-bi-encoder), dùng SentenceTransformer.
    - Ngược lại dùng `fastembed` (ONNX Runtime) với model đa ngôn ngữ hỗ trợ tiếng Việt
      (mặc định: sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2, 384 chiều).
    """

    def __init__(self, model_name: str = DEFAULT_FASTEMBED_VI_MODEL) -> None:
        self.requested_model = model_name
        self.active_model_name = model_name
        self.backend = ""
        self._model: Any = None
        self._vector_size: int | None = None
        self._load_model()

    def _load_model(self) -> None:
        # Thử sentence-transformers nếu model không nằm trong danh mục fastembed mặc định
        st_loaded = False
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore

            self._model = SentenceTransformer(self.requested_model)
            self._vector_size = int(self._model.get_sentence_embedding_dimension())
            self.active_model_name = self.requested_model
            self.backend = "sentence-transformers"
            st_loaded = True
        except Exception:
            st_loaded = False

        if st_loaded:
            return

        # Dùng fastembed ONNX Runtime
        try:
            from fastembed import TextEmbedding  # type: ignore

            supported = {m["model"]: m for m in TextEmbedding.list_supported_models()}
            chosen_model = self.requested_model if self.requested_model in supported else DEFAULT_FASTEMBED_VI_MODEL
            if chosen_model not in supported:
                # Dự phòng tìm model multilingual bất kỳ trong fastembed
                multi = [m["model"] for m in supported.values() if "multilingual" in m["model"].lower()]
                if not multi:
                    raise EmbeddingError("Không tìm thấy mô hình embedding đa ngôn ngữ/tiếng Việt trong fastembed.")
                chosen_model = multi[0]

            if chosen_model != self.requested_model:
                logger.info(
                    "Model '%s' yêu cầu sentence-transformers chưa cài; sử dụng model ONNX đa ngôn ngữ hỗ trợ tiếng Việt '%s'.",
                    self.requested_model,
                    chosen_model,
                )

            self._model = TextEmbedding(model_name=chosen_model)
            self.active_model_name = chosen_model
            self.backend = "fastembed"
            dim = supported.get(chosen_model, {}).get("dim")
            self._vector_size = int(dim) if dim else None
        except Exception as exc:
            raise EmbeddingError(
                f"Không thể khởi tạo mô hình embedding tiếng Việt ('{self.requested_model}'): {exc}"
            ) from exc

    @property
    def vector_size(self) -> int:
        if self._vector_size is None:
            sample = self.embed_query("pháp luật Việt Nam")
            self._vector_size = len(sample)
        return self._vector_size

    def _format_texts(self, texts: list[str], is_query: bool) -> list[str]:
        if "e5" in self.active_model_name.lower():
            prefix = "query: " if is_query else "passage: "
            return [f"{prefix}{t}" for t in texts]
        return texts

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        formatted = self._format_texts(texts, is_query=False)
        try:
            if self.backend == "sentence-transformers":
                vecs = self._model.encode(formatted, normalize_embeddings=True)
                result = [v.tolist() for v in vecs]
            else:
                result = [vec.tolist() for vec in self._model.embed(formatted)]
            if result and self._vector_size is None:
                self._vector_size = len(result[0])
            return result
        except Exception as exc:
            raise EmbeddingError(f"Lỗi khi tạo embedding cho danh sách chunk: {exc}") from exc

    def embed_query(self, query: str) -> list[float]:
        formatted = self._format_texts([query], is_query=True)
        try:
            if self.backend == "sentence-transformers":
                vec = self._model.encode(formatted, normalize_embeddings=True)[0]
                out = vec.tolist()
            else:
                out = next(iter(self._model.embed(formatted))).tolist()
            if self._vector_size is None:
                self._vector_size = len(out)
            return out
        except Exception as exc:
            raise EmbeddingError(f"Lỗi khi tạo embedding cho câu truy vấn: {exc}") from exc


def get_embedder(model_name: str = DEFAULT_FASTEMBED_VI_MODEL) -> VietnameseEmbedder:
    with _EMBEDDER_LOCK:
        if model_name not in _EMBEDDER_CACHE:
            _EMBEDDER_CACHE[model_name] = VietnameseEmbedder(model_name=model_name)
        return _EMBEDDER_CACHE[model_name]


def _tokenize_vi_search(text: str) -> set[str]:
    tokens = re.findall(r"[0-9A-Za-zÀ-ỹ]{2,}", text.lower())
    stop = {"của", "và", "các", "những", "được", "trong", "theo", "tại", "về", "cho", "với", "khi", "nếu", "thì", "là"}
    return {t for t in tokens if t not in stop}


class QdrantLegalRetriever:
    """
    Quản lý đồng bộ và truy xuất vector chunk pháp luật trên Qdrant.
    """

    def __init__(
        self,
        qdrant_url: str,
        collection_name: str,
        embedding_model: str = DEFAULT_FASTEMBED_VI_MODEL,
        qdrant_mode: str = "auto",
        qdrant_local_path: str | None = None,
    ) -> None:
        self.qdrant_url = (qdrant_url or "http://localhost:6333").rstrip("/")
        self.collection_name = collection_name
        self.embedding_model = embedding_model
        self.qdrant_mode = (qdrant_mode or "auto").lower()
        self.qdrant_local_path = qdrant_local_path or str(Path("data") / "qdrant_storage")
        self._active_backend: str = self.qdrant_mode

    def _probe_remote_server(self, timeout: float = 0.8) -> tuple[bool, str]:
        try:
            resp = httpx.get(f"{self.qdrant_url}/collections", timeout=timeout)
            if resp.status_code == 200:
                return True, f"Qdrant Server ({self.qdrant_url})"
            return False, f"Qdrant Server phản hồi HTTP {resp.status_code} tại {self.qdrant_url}"
        except Exception as exc:
            return False, f"Không thể kết nối Qdrant tại {self.qdrant_url}: {exc.__class__.__name__}"

    def _get_client(self):
        try:
            from qdrant_client import QdrantClient
        except ImportError as exc:
            raise QdrantConnectionError("Chưa cài đặt thư viện qdrant-client.") from exc

        if self.qdrant_mode == "remote":
            ok, msg = self._probe_remote_server(timeout=1.5)
            if not ok:
                raise QdrantConnectionError(msg)
            self._active_backend = f"remote ({self.qdrant_url})"
            return QdrantClient(url=self.qdrant_url, timeout=5.0)

        if self.qdrant_mode == "auto":
            ok, _ = self._probe_remote_server(timeout=0.6)
            if ok:
                self._active_backend = f"remote ({self.qdrant_url})"
                return QdrantClient(url=self.qdrant_url, timeout=5.0)

        # local mode hoặc auto fallback sang Qdrant Local Persistent Storage
        storage_path = Path(self.qdrant_local_path).resolve()
        storage_path.mkdir(parents=True, exist_ok=True)
        key = str(storage_path)
        with _LOCAL_QDRANT_LOCK:
            if key not in _LOCAL_QDRANT_CLIENTS:
                _LOCAL_QDRANT_CLIENTS[key] = QdrantClient(path=key)
            self._active_backend = f"local ({storage_path.name})"
            return _LOCAL_QDRANT_CLIENTS[key]

    @property
    def active_backend(self) -> str:
        return self._active_backend

    def check_connection(self) -> tuple[bool, str]:
        """Kiểm tra kết nối Qdrant (kể cả khi collection chưa có vector nào)."""
        try:
            client = self._get_client()
            cols = client.get_collections()
            col_names = [c.name for c in cols.collections]
            if self.collection_name in col_names:
                info = client.get_collection(self.collection_name)
                points = int(info.points_count or 0)
                return True, f"Kết nối Qdrant thành công [{self._active_backend}] — collection '{self.collection_name}': {points} vector chunks."
            return True, f"Kết nối Qdrant thành công [{self._active_backend}] — collection '{self.collection_name}' chưa được khởi tạo (0 chunks)."
        except Exception as exc:
            return False, f"Mất kết nối Qdrant: {exc}"

    def is_available(self) -> tuple[bool, str]:
        """Kiểm tra Qdrant sẵn sàng phục vụ truy xuất RAG (kết nối được VÀ có ít nhất 1 vector)."""
        try:
            client = self._get_client()
            if not client.collection_exists(self.collection_name):
                return False, f"Collection '{self.collection_name}' chưa có dữ liệu trên Qdrant [{self._active_backend}] (0 chunks)."
            info = client.get_collection(self.collection_name)
            points = int(info.points_count or 0)
            if points > 0:
                return True, f"Kết nối Qdrant thành công [{self._active_backend}] ({points} vector chunks)."
            return False, f"Collection '{self.collection_name}' chưa có vector nào (0 chunks)."
        except Exception as exc:
            return False, f"Không thể kết nối Qdrant ({self.qdrant_url}): {exc}"

    def ensure_collection(self, vector_size: int) -> None:
        from qdrant_client.models import Distance, VectorParams

        client = self._get_client()
        if not client.collection_exists(self.collection_name):
            client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )
            return

        info = client.get_collection(self.collection_name)
        cfg = info.config.params.vectors
        existing_size = getattr(cfg, "size", None)
        if existing_size is not None and int(existing_size) != int(vector_size):
            raise QdrantConnectionError(
                f"Kích thước vector của collection '{self.collection_name}' ({existing_size}) "
                f"không khớp mô hình embedding hiện tại ({vector_size})."
            )

    def count_document_vectors(self, document_id: str) -> int:
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        client = self._get_client()
        if not client.collection_exists(self.collection_name):
            return 0
        res = client.count(
            collection_name=self.collection_name,
            count_filter=Filter(
                must=[FieldCondition(key="document_id", match=MatchValue(value=document_id))]
            ),
            exact=True,
        )
        return int(res.count)

    def get_collection_stats(self) -> dict[str, Any]:
        ok, detail = self.check_connection()
        if not ok:
            return {
                "connected": False,
                "backend": self._active_backend,
                "collection": self.collection_name,
                "points_count": 0,
                "detail": detail,
            }
        try:
            client = self._get_client()
            exists = client.collection_exists(self.collection_name)
            points = int(client.get_collection(self.collection_name).points_count or 0) if exists else 0
            return {
                "connected": True,
                "backend": self._active_backend,
                "collection": self.collection_name,
                "points_count": points,
                "detail": detail,
            }
        except Exception as exc:
            return {
                "connected": False,
                "backend": self._active_backend,
                "collection": self.collection_name,
                "points_count": 0,
                "detail": str(exc),
            }

    def delete_document_vectors(self, document_id: str) -> int:
        """
        Xóa chỉ các vector thuộc đúng `document_id` trên Qdrant.
        TUYỆT ĐỐI KHÔNG xóa toàn bộ collection.
        """
        from qdrant_client.models import FieldCondition, Filter, FilterSelector, MatchValue

        client = self._get_client()
        if not client.collection_exists(self.collection_name):
            return 0
        before_count = self.count_document_vectors(document_id)
        if before_count == 0:
            return 0

        client.delete(
            collection_name=self.collection_name,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[FieldCondition(key="document_id", match=MatchValue(value=document_id))]
                )
            ),
            wait=True,
        )
        after_count = self.count_document_vectors(document_id)
        if after_count != 0:
            raise QdrantConnectionError(
                f"Xóa vector cho document_id={document_id} chưa hoàn tất (còn lại {after_count} vector)."
            )
        return before_count

    def upsert_document_chunks(
        self,
        document_id: str,
        chunks: list[LegalDocumentChunk],
    ) -> dict[str, Any]:
        """
        Tạo embedding và lưu toàn bộ chunk của một văn bản vào Qdrant.
        - Xóa vector cũ của riêng `document_id` trước khi nạp lại (không ảnh hưởng văn bản khác).
        - Kiểm tra số lượng chunk trước và sau khi lưu.
        """
        from qdrant_client.models import PointStruct

        if not chunks:
            raise ValueError("Không có chunk nào để lưu vào Qdrant.")

        embedder = get_embedder(self.embedding_model)
        texts = [c.embedding_text or c.content for c in chunks]
        vectors = embedder.embed_documents(texts)
        if len(vectors) != len(chunks):
            raise EmbeddingError(
                f"Số lượng vector embedding ({len(vectors)}) không khớp số lượng chunk ({len(chunks)})."
            )

        client = self._get_client()
        self.ensure_collection(len(vectors[0]))

        # Xóa vector cũ của riêng văn bản này nếu đang cập nhật (KHÔNG xóa toàn bộ collection)
        before_doc_count = self.count_document_vectors(document_id)
        if before_doc_count > 0:
            self.delete_document_vectors(document_id)

        points: list[PointStruct] = []
        for chunk, vec in zip(chunks, vectors):
            point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{document_id}:{chunk.chunk_id}"))
            payload = {
                "chunk_id": chunk.chunk_id,
                "document_id": document_id,
                "document_number": chunk.document_number,
                "document_title": chunk.document_name,
                "document_name": chunk.document_name,
                "document_type": chunk.document_type,
                "issuing_authority": chunk.issuing_authority,
                "issue_date": chunk.issue_date,
                "effective_date": chunk.effective_date,
                "expiry_date": chunk.expiry_date,
                "document_status": chunk.document_status,
                "part": chunk.part,
                "chapter": chunk.chapter,
                "section": chunk.section,
                "article": chunk.article,
                "clause": chunk.clause,
                "point": chunk.point,
                "content": chunk.content,
                "source": chunk.source,
                "source_file": chunk.source_file,
                "page_number": chunk.page_number,
                "chunk_index": chunk.chunk_index,
                "needs_review": chunk.needs_review,
            }
            points.append(PointStruct(id=point_id, vector=vec, payload=payload))

        batch_size = 64
        for start in range(0, len(points), batch_size):
            client.upsert(
                collection_name=self.collection_name,
                points=points[start : start + batch_size],
                wait=True,
            )

        after_doc_count = self.count_document_vectors(document_id)
        verified = after_doc_count == len(chunks)
        if not verified:
            raise QdrantConnectionError(
                f"Kiểm tra sau lưu thất bại cho document_id={document_id}: "
                f"kỳ vọng {len(chunks)} chunks nhưng Qdrant ghi nhận {after_doc_count} chunks."
            )

        return {
            "document_id": document_id,
            "before_count": before_doc_count,
            "expected_chunks": len(chunks),
            "synced_chunks": after_doc_count,
            "verified": verified,
            "collection": self.collection_name,
            "embedding_model": embedder.active_model_name,
            "vector_size": embedder.vector_size,
            "qdrant_backend": self._active_backend,
        }

    def search(
        self,
        query: str,
        top_k: int = 5,
        score_threshold: float = 0.25,
    ) -> list[RetrievedEvidence]:
        """
        Truy xuất các chunk pháp luật thực tế từ Qdrant bằng vector embedding tiếng Việt.
        Kết hợp điểm cosine vector và đối chiếu từ khóa pháp lý để ưu tiên đúng Điều/Khoản/Điểm.
        """
        if not query or not query.strip():
            return []

        available, _ = self.is_available()
        if not available:
            return []

        try:
            embedder = get_embedder(self.embedding_model)
            query_vector = embedder.embed_query(query.strip())
            client = self._get_client()

            candidate_limit = max(top_k * 3, 12)
            response = client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                limit=candidate_limit,
                with_payload=True,
            )
            hits = response.points or []
        except Exception as exc:
            logger.error("Lỗi truy vấn Qdrant: %s", exc)
            return []

        query_tokens = _tokenize_vi_search(query)
        scored_items: list[tuple[float, RetrievedEvidence]] = []

        for hit in hits:
            payload = hit.payload or {}
            content = str(payload.get("content") or "").strip()
            if not content:
                continue

            vec_score = float(hit.score or 0.0)
            searchable = " ".join(
                str(x)
                for x in [
                    payload.get("document_title"),
                    payload.get("document_number"),
                    payload.get("chapter"),
                    payload.get("article"),
                    payload.get("clause"),
                    payload.get("point"),
                    content,
                ]
                if x
            )
            doc_tokens = _tokenize_vi_search(searchable)
            lexical_overlap = (
                len(query_tokens & doc_tokens) / max(len(query_tokens), 1)
                if query_tokens
                else 0.0
            )
            combined_score = min(1.0, round(vec_score * 0.82 + lexical_overlap * 0.18, 4))

            if vec_score < score_threshold and lexical_overlap < 0.35:
                continue

            scored_items.append(
                (
                    combined_score,
                    RetrievedEvidence(
                        chunk_id=payload.get("chunk_id"),
                        document_id=payload.get("document_id"),
                        document_name=str(payload.get("document_title") or payload.get("document_name") or "Chưa xác định"),
                        document_number=payload.get("document_number"),
                        part=payload.get("part"),
                        chapter=payload.get("chapter"),
                        section=payload.get("section"),
                        article=payload.get("article"),
                        clause=payload.get("clause"),
                        point=payload.get("point"),
                        content=content,
                        relevance_score=combined_score,
                        source=payload.get("source"),
                        source_file=payload.get("source_file"),
                        page_number=payload.get("page_number"),
                        effective_date=payload.get("effective_date"),
                        expiry_date=payload.get("expiry_date"),
                        document_status=payload.get("document_status"),
                    ),
                )
            )

        scored_items.sort(key=lambda pair: pair[0], reverse=True)
        return [ev for _, ev in scored_items[:top_k]]
