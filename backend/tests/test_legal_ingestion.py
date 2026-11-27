"""
Bộ kiểm thử bắt buộc cho chức năng tiếp nhận, chuẩn hóa, chia chunk, embedding,
đồng bộ Qdrant, API quản lý văn bản pháp luật, giao diện và truy xuất RAG (Mục 10).

Lưu ý tách bạch dữ liệu:
- Tất cả tệp fixture chỉ được tạo trong thư mục tạm `tmp_path` của pytest, hoàn toàn tách biệt
  với thư mục dữ liệu thật `data/legal_documents/` và cơ sở dữ liệu sản xuất.
- Không dùng Mock/Dummy để giả lập Qdrant hoặc Embedding: sử dụng `QdrantClient` thật
  và mô hình embedding tiếng Việt ONNX thật (`fastembed`).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.core.database import Base, get_db
from backend.app.main import app
from backend.app.services import legal_ingestion_service as lis_module
from backend.app.services.chat_service import runtime_state
from backend.app.services.legal_ingestion_service import EMPTY_CORPUS_MESSAGE, LegalIngestionService
from rag.pipeline import (
    chunk_legal_document,
    clean_legal_text,
    evaluate_document_validity,
    validate_chunks,
)
from rag.retriever import (
    DEFAULT_FASTEMBED_VI_MODEL,
    QdrantLegalRetriever,
    close_local_qdrant_client,
)

# ---------------------------------------------------------------------------
# Test Fixtures (Tách biệt rõ với dữ liệu pháp luật thật trong data/legal_documents/)
# ---------------------------------------------------------------------------
TEST_FIXTURE_MULTI_STRUCTURE_TXT = """QUỐC HỘI
CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM
Độc lập - Tự do - Hạnh phúc
Số: 45/2019/QH14
Hà Nội, ngày 20 tháng 11 năm 2019
Nguồn: Cổng thông tin điện tử Quốc hội (Test Fixture)

BỘ LUẬT LAO ĐỘNG

CHƯƠNG I
NHỮNG QUY ĐỊNH CHUNG

Điều 1. Phạm vi điều chỉnh
Bộ luật Lao động quy định tiêu chuẩn lao động; quyền, nghĩa vụ, trách nhiệm của người lao động, người sử dụng lao động, tổ chức đại diện người lao động tại cơ sở, tổ chức đại diện người sử dụng lao động trong quan hệ lao động và các quan hệ khác liên quan trực tiếp đến quan hệ lao động; quản lý nhà nước về lao động.

CHƯƠNG III
HỢP ĐỒNG LAO ĐỘNG

Mục 3
CHẤM DỨT HỢP ĐỒNG LAO ĐỘNG

Điều 35. Quyền đơn phương chấm dứt hợp đồng lao động của người lao động
1. Người lao động có quyền đơn phương chấm dứt hợp đồng lao động nhưng phải báo trước cho người sử dụng lao động như sau:
a) Ít nhất 45 ngày nếu làm việc theo hợp đồng lao động không xác định thời hạn;
b) Ít nhất 30 ngày nếu làm việc theo hợp đồng lao động xác định thời hạn có thời hạn từ 12 tháng đến 36 tháng;
c) Ít nhất 03 ngày làm việc nếu làm việc theo hợp đồng lao động xác định thời hạn có thời hạn dưới 12 tháng;
2. Người lao động có quyền đơn phương chấm dứt hợp đồng lao động không cần báo trước trong trường hợp không được bố trí theo đúng công việc, địa điểm làm việc hoặc không được bảo đảm điều kiện làm việc theo thỏa thuận.

CHƯƠNG XVII
ĐIỀU KHOẢN THI HÀNH

Điều 220. Hiệu lực thi hành
1. Bộ luật này có hiệu lực thi hành từ ngày 01 tháng 01 năm 2021.
"""

TEST_FIXTURE_VALID_JSON = {
    "title": "Nghị định quy định về bảo vệ dữ liệu cá nhân",
    "document_number": "13/2023/NĐ-CP",
    "document_type": "Nghị định",
    "issuing_authority": "CHÍNH PHỦ",
    "issue_date": "2023-04-17",
    "effective_date": "2023-07-01",
    "expiry_date": None,
    "status": "Đang áp dụng (theo nguồn kiểm thử)",
    "source": "Công báo Chính phủ (Test Fixture)",
    "content": (
        "CHƯƠNG I\n"
        "QUY ĐỊNH CHUNG\n"
        "Điều 1. Phạm vi điều chỉnh và đối tượng áp dụng\n"
        "1. Nghị định này quy định về bảo vệ dữ liệu cá nhân và trách nhiệm bảo vệ dữ liệu cá nhân của cơ quan, tổ chức, cá nhân có liên quan.\n"
        "2. Nghị định này áp dụng đối với cơ quan, tổ chức, cá nhân Việt Nam và cơ quan, tổ chức, cá nhân nước ngoài trực tiếp tham gia hoạt động xử lý dữ liệu cá nhân tại Việt Nam.\n"
        "Điều 9. Quyền của chủ thể dữ liệu\n"
        "1. Chủ thể dữ liệu được biết về hoạt động xử lý dữ liệu cá nhân của mình.\n"
        "2. Chủ thể dữ liệu được đồng ý hoặc không đồng ý cho phép xử lý dữ liệu cá nhân của mình."
    ),
}

TEST_FIXTURE_NO_EFFECTIVE_DATE_TXT = """CHÍNH PHỦ
Số: 99/2022/NĐ-CP
Hà Nội, ngày 30 tháng 11 năm 2022

NGHỊ ĐỊNH
Quy định về đăng ký biện pháp bảo đảm

Điều 1. Phạm vi điều chỉnh
Nghị định này quy định về đăng ký, cung cấp thông tin về biện pháp bảo đảm và quản lý nhà nước về đăng ký biện pháp bảo đảm.
"""

TEST_FIXTURE_UNSTRUCTURED_TXT = """Tài liệu ghi chú nội bộ về quy trình tiếp nhận hồ sơ hành chính công.
Tài liệu này không chia theo Chương hay Điều khoản chuẩn.
Cần được hệ thống đánh dấu cần kiểm tra cấu trúc thay vì tự tạo Điều 1 giả.
"""


@pytest.fixture()
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """
    Tạo môi trường tích hợp thực tế cô lập hoàn toàn trong `tmp_path`:
    - SQLite DB riêng
    - Thư mục `legal_documents` riêng
    - Qdrant Local Storage thật riêng + Embedding ONNX thật
    - FastAPI TestClient gắn đúng DB & Service cô lập
    """
    docs_dir = tmp_path / "legal_documents"
    docs_dir.mkdir(parents=True, exist_ok=True)
    qdrant_dir = tmp_path / "qdrant_storage"
    db_file = tmp_path / "test_legal.db"

    engine = create_engine(f"sqlite:///{db_file.as_posix()}", future=True, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    retriever = QdrantLegalRetriever(
        qdrant_url="http://localhost:6333",
        collection_name="test_vietnam_legal_docs",
        embedding_model=DEFAULT_FASTEMBED_VI_MODEL,
        qdrant_mode="local",
        qdrant_local_path=str(qdrant_dir),
    )

    service = LegalIngestionService(
        documents_dir=docs_dir,
        retriever=retriever,
        project_root=tmp_path,
    )

    # Override FastAPI dependency & singleton service
    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr("backend.app.api.routes.legal_ingestion_service", service)
    monkeypatch.setattr("backend.app.services.chat_service.legal_ingestion_service", service)
    monkeypatch.setattr(lis_module, "legal_ingestion_service", service)

    client = TestClient(app)

    yield {
        "client": client,
        "db_factory": TestingSessionLocal,
        "docs_dir": docs_dir,
        "qdrant_dir": qdrant_dir,
        "retriever": retriever,
        "service": service,
        "tmp_path": tmp_path,
    }

    app.dependency_overrides.pop(get_db, None)
    runtime_state.app_mode = "demo"
    close_local_qdrant_client(str(qdrant_dir))
    engine.dispose()


# ---------------------------------------------------------------------------
# Test 1: Nạp một file TXT hợp lệ
# ---------------------------------------------------------------------------
def test_01_ingest_valid_txt_file(isolated_env):
    docs_dir = isolated_env["docs_dir"]
    service: LegalIngestionService = isolated_env["service"]
    db_factory = isolated_env["db_factory"]

    txt_file = docs_dir / "bo_luat_lao_dong_fixture.txt"
    txt_file.write_text(TEST_FIXTURE_MULTI_STRUCTURE_TXT, encoding="utf-8")

    with db_factory() as db:
        res = service.ingest_file(db, txt_file)
        assert res.status == "success"
        assert res.action == "ingested"
        assert res.document_id is not None
        assert res.qdrant_sync_status == "synced"
        assert res.chunk_count >= 6

        detail = service.get_document_detail(db, res.document_id)
        assert detail is not None
        assert detail.document_number == "45/2019/QH14"
        assert detail.document_type == "Bộ luật"
        assert detail.issuing_authority == "QUỐC HỘI"
        assert detail.issue_date == "2019-11-20"
        assert detail.effective_date == "2021-01-01"
        assert detail.checksum and len(detail.checksum) == 64
        assert detail.ingestion_date is not None


# ---------------------------------------------------------------------------
# Test 2: Nạp một file JSON hợp lệ
# ---------------------------------------------------------------------------
def test_02_ingest_valid_json_file(isolated_env):
    docs_dir = isolated_env["docs_dir"]
    service: LegalIngestionService = isolated_env["service"]
    db_factory = isolated_env["db_factory"]

    json_file = docs_dir / "nghi_dinh_13_2023_fixture.json"
    json_file.write_text(json.dumps(TEST_FIXTURE_VALID_JSON, ensure_ascii=False, indent=2), encoding="utf-8")

    with db_factory() as db:
        res = service.ingest_file(db, json_file)
        assert res.status == "success"
        assert res.action == "ingested"
        assert res.qdrant_sync_status == "synced"
        assert res.chunk_count == 4  # Điều 1 (2 khoản) + Điều 9 (2 khoản)

        detail = service.get_document_detail(db, res.document_id)
        assert detail is not None
        assert detail.title == TEST_FIXTURE_VALID_JSON["title"]
        assert detail.document_number == "13/2023/NĐ-CP"
        assert detail.document_type == "Nghị định"
        assert detail.issuing_authority == "CHÍNH PHỦ"
        assert detail.issue_date == "2023-04-17"
        assert detail.effective_date == "2023-07-01"
        assert detail.source == "Công báo Chính phủ (Test Fixture)"


# ---------------------------------------------------------------------------
# Test 3: Nạp file rỗng
# ---------------------------------------------------------------------------
def test_03_ingest_empty_file_rejected(isolated_env):
    docs_dir = isolated_env["docs_dir"]
    service: LegalIngestionService = isolated_env["service"]
    db_factory = isolated_env["db_factory"]

    empty_txt = docs_dir / "empty_file.txt"
    empty_txt.write_text("   \n\t  ", encoding="utf-8")

    empty_json = docs_dir / "empty_content.json"
    empty_json.write_text(json.dumps({"title": "Văn bản rỗng", "content": "   "}), encoding="utf-8")

    with db_factory() as db:
        res_txt = service.ingest_file(db, empty_txt)
        assert res_txt.status == "error"
        assert "rỗng" in res_txt.message.lower()

        res_json = service.ingest_file(db, empty_json)
        assert res_json.status == "error"
        assert "rỗng" in res_json.message.lower()

        listing = service.list_documents(db)
        assert listing.total_documents == 0


# ---------------------------------------------------------------------------
# Test 4: Nạp file sai định dạng
# ---------------------------------------------------------------------------
def test_04_ingest_unsupported_format_rejected(isolated_env):
    docs_dir = isolated_env["docs_dir"]
    service: LegalIngestionService = isolated_env["service"]
    db_factory = isolated_env["db_factory"]

    bad_file = docs_dir / "van_ban_khong_ho_tro.pdf"
    bad_file.write_bytes(b"%PDF-1.4 dummy binary")

    bad_json = docs_dir / "corrupt_syntax.json"
    bad_json.write_text("{ invalid json", encoding="utf-8")

    with db_factory() as db:
        res_pdf = service.ingest_file(db, bad_file)
        assert res_pdf.status == "error"
        assert "không được hỗ trợ" in res_pdf.message.lower()

        res_bad_json = service.ingest_file(db, bad_json)
        assert res_bad_json.status == "error"
        assert "lỗi cú pháp" in res_bad_json.message.lower()

        stats = service.get_stats(db)
        assert len(stats.recent_logs) >= 2


# ---------------------------------------------------------------------------
# Test 5: Nạp văn bản trùng lặp & chống tự ghi đè khi thay đổi chưa xác nhận
# ---------------------------------------------------------------------------
def test_05_ingest_duplicate_and_controlled_update(isolated_env):
    docs_dir = isolated_env["docs_dir"]
    service: LegalIngestionService = isolated_env["service"]
    db_factory = isolated_env["db_factory"]

    file_a = docs_dir / "doc_a.txt"
    file_a.write_text(TEST_FIXTURE_NO_EFFECTIVE_DATE_TXT, encoding="utf-8")

    file_copy = docs_dir / "doc_a_duplicate.txt"
    file_copy.write_text(TEST_FIXTURE_NO_EFFECTIVE_DATE_TXT, encoding="utf-8")

    with db_factory() as db:
        first = service.ingest_file(db, file_a)
        assert first.status == "success"
        assert first.action == "ingested"

        # Trùng nội dung (khác tên file vẫn phát hiện qua SHA-256 checksum)
        dup = service.ingest_file(db, file_copy)
        assert dup.status == "skipped"
        assert dup.action == "skipped_duplicate"
        assert dup.document_id == first.document_id

        # Sửa đổi nội dung file_a nhưng chưa bật allow_update -> KHÔNG tự động ghi đè
        file_a.write_text(
            TEST_FIXTURE_NO_EFFECTIVE_DATE_TXT + "\nĐiều 2. Đối tượng áp dụng\nÁp dụng cho tổ chức, cá nhân có liên quan.\n",
            encoding="utf-8",
        )
        conflict = service.ingest_file(db, file_a, allow_update=False)
        assert conflict.status == "conflict"
        assert conflict.action == "conflict_requires_update"

        # Cho phép cập nhật có kiểm soát -> giữ nguyên document_id, cập nhật chunk & vector
        updated = service.ingest_file(db, file_a, allow_update=True)
        assert updated.status == "success"
        assert updated.action == "updated"
        assert updated.document_id == first.document_id
        assert updated.chunk_count > first.chunk_count


# ---------------------------------------------------------------------------
# Test 6: Nạp văn bản thiếu ngày hiệu lực (không tự suy đoán, không mặc định còn hiệu lực)
# ---------------------------------------------------------------------------
def test_06_ingest_document_missing_effective_date_not_guessed(isolated_env):
    docs_dir = isolated_env["docs_dir"]
    service: LegalIngestionService = isolated_env["service"]
    db_factory = isolated_env["db_factory"]

    f = docs_dir / "missing_effective.txt"
    f.write_text(TEST_FIXTURE_NO_EFFECTIVE_DATE_TXT, encoding="utf-8")

    with db_factory() as db:
        res = service.ingest_file(db, f)
        assert res.status == "success"
        detail = service.get_document_detail(db, res.document_id)
        assert detail is not None
        assert detail.issue_date == "2022-11-30"
        assert detail.effective_date is None  # Tuyệt đối không suy đoán từ issue_date
        assert detail.expiry_date is None
        assert detail.status is None  # Tuyệt đối không mặc định "Còn hiệu lực"

        val_label, _ = evaluate_document_validity(detail.effective_date, detail.expiry_date, detail.status)
        assert val_label == "Chưa xác định"


# ---------------------------------------------------------------------------
# Test 7: Nạp văn bản có nhiều Chương, Điều, Khoản, Điểm (+ văn bản không có cấu trúc)
# ---------------------------------------------------------------------------
def test_07_ingest_multi_chapter_article_clause_point_structure(isolated_env):
    docs_dir = isolated_env["docs_dir"]
    service: LegalIngestionService = isolated_env["service"]
    db_factory = isolated_env["db_factory"]

    f_struct = docs_dir / "multi_structure.txt"
    f_struct.write_text(TEST_FIXTURE_MULTI_STRUCTURE_TXT, encoding="utf-8")

    f_unstruct = docs_dir / "unstructured_note.txt"
    f_unstruct.write_text(TEST_FIXTURE_UNSTRUCTURED_TXT, encoding="utf-8")

    with db_factory() as db:
        res_s = service.ingest_file(db, f_struct)
        assert res_s.status == "success"
        assert res_s.needs_review is False

        chunks_res = service.get_document_chunks(db, res_s.document_id)
        assert chunks_res is not None
        items = chunks_res.items

        chapters = {c.chapter for c in items if c.chapter}
        articles = {c.article for c in items if c.article}
        clauses = {c.clause for c in items if c.clause}
        points = {c.point for c in items if c.point}

        assert any("CHƯƠNG I" in ch for ch in chapters)
        assert any("CHƯƠNG III" in ch for ch in chapters)
        assert any("CHƯƠNG XVII" in ch for ch in chapters)
        assert {"Điều 1", "Điều 35", "Điều 220"}.issubset(articles)
        assert {"Khoản 1", "Khoản 2"}.issubset(clauses)
        assert {"Điểm a", "Điểm b", "Điểm c"}.issubset(points)

        # Kiểm tra văn bản không có cấu trúc được đánh dấu needs_review, KHÔNG tự tạo cấu trúc giả
        res_u = service.ingest_file(db, f_unstruct)
        assert res_u.status == "success"
        assert res_u.needs_review is True
        u_chunks = service.get_document_chunks(db, res_u.document_id)
        assert u_chunks is not None and len(u_chunks.items) == 1
        assert u_chunks.items[0].article is None
        assert u_chunks.items[0].chapter is None
        assert u_chunks.items[0].needs_review is True


# ---------------------------------------------------------------------------
# Test 8: Kiểm tra chunk không mất nội dung & không gộp Điều khác nhau
# ---------------------------------------------------------------------------
def test_08_chunking_preserves_100_percent_content_and_no_article_merge():
    cleaned = clean_legal_text(TEST_FIXTURE_MULTI_STRUCTURE_TXT)
    chunks = chunk_legal_document(cleaned, filename="bo_luat_lao_dong_fixture.txt", document_id="DOC-TEST-08")

    ok, errors = validate_chunks(cleaned, chunks)
    assert ok is True, f"Chunk validation errors: {errors}"

    reconstructed = "\n".join(c.content for c in chunks)
    assert reconstructed == cleaned

    # Không chunk nào chứa đồng thời 2 Điều khác nhau
    for c in chunks:
        assert not ("Điều 1." in c.content and "Điều 35." in c.content)
        assert not ("Điều 35." in c.content and "Điều 220." in c.content)


# ---------------------------------------------------------------------------
# Test 9: Kiểm tra dữ liệu được lưu đúng vào Qdrant, xóa đúng theo document_id & xử lý lỗi mất kết nối
# ---------------------------------------------------------------------------
def test_09_qdrant_storage_verification_targeted_delete_and_disconnect_error(isolated_env):
    docs_dir = isolated_env["docs_dir"]
    service: LegalIngestionService = isolated_env["service"]
    retriever: QdrantLegalRetriever = isolated_env["retriever"]
    db_factory = isolated_env["db_factory"]

    f1 = docs_dir / "doc1.txt"
    f1.write_text(TEST_FIXTURE_MULTI_STRUCTURE_TXT, encoding="utf-8")
    f2 = docs_dir / "doc2.json"
    f2.write_text(json.dumps(TEST_FIXTURE_VALID_JSON, ensure_ascii=False), encoding="utf-8")

    with db_factory() as db:
        r1 = service.ingest_file(db, f1)
        r2 = service.ingest_file(db, f2)
        assert r1.qdrant_sync_status == "synced"
        assert r2.qdrant_sync_status == "synced"

        # Kiểm tra số vector thực tế trên Qdrant khớp 100% số chunk từng văn bản
        assert retriever.count_document_vectors(r1.document_id) == r1.chunk_count
        assert retriever.count_document_vectors(r2.document_id) == r2.chunk_count

        stats_q = retriever.get_collection_stats()
        assert stats_q["connected"] is True
        assert stats_q["points_count"] == r1.chunk_count + r2.chunk_count

        # Xóa văn bản 1 -> chỉ xóa vector của văn bản 1, KHÔNG xóa toàn bộ collection (văn bản 2 còn nguyên!)
        del_res = service.delete_document(db, r1.document_id)
        assert del_res is not None
        assert del_res["deleted_vectors"] == r1.chunk_count
        assert retriever.count_document_vectors(r1.document_id) == 0
        assert retriever.count_document_vectors(r2.document_id) == r2.chunk_count

    # Kiểm tra xử lý lỗi khi Qdrant mất kết nối (remote URL không tồn tại)
    offline_retriever = QdrantLegalRetriever(
        qdrant_url="http://127.0.0.1:19999",
        collection_name="offline_test_col",
        embedding_model=DEFAULT_FASTEMBED_VI_MODEL,
        qdrant_mode="remote",
    )
    offline_service = LegalIngestionService(
        documents_dir=docs_dir,
        retriever=offline_retriever,
        project_root=isolated_env["tmp_path"],
    )
    f3 = docs_dir / "doc3_offline.txt"
    f3.write_text(TEST_FIXTURE_NO_EFFECTIVE_DATE_TXT, encoding="utf-8")
    with db_factory() as db:
        r3 = offline_service.ingest_file(db, f3)
        assert r3.status == "error"
        assert r3.qdrant_sync_status == "failed"
        assert "Qdrant" in r3.message


# ---------------------------------------------------------------------------
# Test 10: Kiểm tra đầy đủ API quản lý văn bản pháp luật
# ---------------------------------------------------------------------------
def test_10_api_legal_documents_endpoints_full_lifecycle(isolated_env):
    client: TestClient = isolated_env["client"]
    docs_dir = isolated_env["docs_dir"]

    # Khi thư mục trống -> trả về thông báo chuẩn
    empty_resp = client.get("/api/legal-documents")
    assert empty_resp.status_code == 200
    empty_data = empty_resp.json()
    assert empty_data["loaded"] is False
    assert empty_data["note"] == EMPTY_CORPUS_MESSAGE

    # Thêm 2 file hợp lệ vào thư mục và gọi POST /api/legal-documents/scan
    (docs_dir / "labor_law.txt").write_text(TEST_FIXTURE_MULTI_STRUCTURE_TXT, encoding="utf-8")
    (docs_dir / "privacy_decree.json").write_text(
        json.dumps(TEST_FIXTURE_VALID_JSON, ensure_ascii=False),
        encoding="utf-8",
    )

    scan_resp = client.post("/api/legal-documents/scan", json={"auto_ingest": True, "allow_update": False})
    assert scan_resp.status_code == 200
    scan_body = scan_resp.json()
    assert scan_body["total_files_found"] == 2
    assert scan_body["ingested_count"] == 2
    assert scan_body["error_count"] == 0

    # GET /api/legal-documents (danh sách + lọc theo loại & cơ quan ban hành & tìm kiếm)
    list_resp = client.get("/api/legal-documents")
    assert list_resp.status_code == 200
    list_body = list_resp.json()
    assert list_body["loaded"] is True
    assert list_body["total_documents"] == 2
    assert list_body["synced_documents"] == 2

    filtered = client.get("/api/legal-documents", params={"document_type": "Nghị định", "issuing_authority": "CHÍNH PHỦ"})
    assert filtered.status_code == 200
    assert filtered.json()["total_documents"] == 1
    doc_id = filtered.json()["items"][0]["document_id"]

    # GET /api/legal-documents/{document_id}
    detail_resp = client.get(f"/api/legal-documents/{doc_id}")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["document_number"] == "13/2023/NĐ-CP"

    # GET /api/legal-documents/{document_id}/chunks
    chunks_resp = client.get(f"/api/legal-documents/{doc_id}/chunks")
    assert chunks_resp.status_code == 200
    assert chunks_resp.json()["total_chunks"] == 4

    # GET /api/legal-documents/stats
    stats_resp = client.get("/api/legal-documents/stats")
    assert stats_resp.status_code == 200
    stats_body = stats_resp.json()
    assert stats_body["total_documents"] == 2
    assert stats_body["synced_documents"] == 2
    assert stats_body["qdrant_connected"] is True
    assert stats_body["qdrant_points_count"] == stats_body["total_chunks"]

    # POST /api/legal-documents/ingest (file cụ thể trùng lặp -> skip)
    ingest_again = client.post("/api/legal-documents/ingest", json={"file_path": "privacy_decree.json"})
    assert ingest_again.status_code == 200
    assert ingest_again.json()["skipped_duplicate_count"] == 1

    # DELETE /api/legal-documents/{document_id}
    del_resp = client.delete(f"/api/legal-documents/{doc_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "deleted"
    assert client.get(f"/api/legal-documents/{doc_id}").status_code == 404


# ---------------------------------------------------------------------------
# Test 11: Kiểm tra giao diện chứa đủ 10 cột và phản ánh dữ liệu thực sau khi nạp
# ---------------------------------------------------------------------------
def test_11_ui_has_all_required_elements_and_updates_after_ingest(isolated_env):
    client: TestClient = isolated_env["client"]
    docs_dir = isolated_env["docs_dir"]

    html_resp = client.get("/")
    assert html_resp.status_code == 200
    html = html_resp.text

    # Xác minh giao diện chứa đủ 10 cột yêu cầu, nút quét/đồng bộ, bộ lọc và thông báo trạng thái rỗng chuẩn
    required_ui_strings = [
        "STT",
        "Tên văn bản",
        "Số hiệu",
        "Loại văn bản",
        "Cơ quan ban hành",
        "Ngày ban hành",
        "Ngày hiệu lực",
        "Trạng thái",
        "Số lượng chunk",
        "Trạng thái đồng bộ Qdrant",
        "Quét thư mục & Đồng bộ dữ liệu",
        "Tất cả cơ quan ban hành",
        "Tất cả loại văn bản",
        "/api/legal-documents/scan",
        "/api/legal-documents/stats",
        EMPTY_CORPUS_MESSAGE,
    ]
    for expected in required_ui_strings:
        assert expected in html, f"Thiếu thành phần giao diện bắt buộc: {expected}"

    # Nạp văn bản thật vào thư mục -> xác minh cả /api/legal-documents và /api/statistics cập nhật cho UI
    (docs_dir / "ui_sync_doc.json").write_text(
        json.dumps(TEST_FIXTURE_VALID_JSON, ensure_ascii=False),
        encoding="utf-8",
    )
    client.post("/api/legal-documents/scan", json={"auto_ingest": True})

    ui_list = client.get("/api/legal-documents").json()
    assert ui_list["loaded"] is True
    assert ui_list["total_documents"] == 1
    item = ui_list["items"][0]
    assert item["title"] == TEST_FIXTURE_VALID_JSON["title"]
    assert item["qdrant_sync_status"] == "synced"
    assert item["chunk_count"] == 4

    dashboard_stats = client.get("/api/statistics").json()
    assert dashboard_stats["total_documents"] == 1


# ---------------------------------------------------------------------------
# Test 12: Kiểm tra truy vấn RAG từ Qdrant trả về trích dẫn chính xác Điều/Khoản/Điểm
# ---------------------------------------------------------------------------
def test_12_rag_query_returns_accurate_citations_from_qdrant(isolated_env):
    client: TestClient = isolated_env["client"]
    docs_dir = isolated_env["docs_dir"]

    (docs_dir / "labor_code.txt").write_text(TEST_FIXTURE_MULTI_STRUCTURE_TXT, encoding="utf-8")
    scan = client.post("/api/legal-documents/scan", json={"auto_ingest": True})
    assert scan.status_code == 200
    assert scan.json()["ingested_count"] == 1
    doc_id = scan.json()["results"][0]["document_id"]

    # Chuyển sang LIVE MODE để gọi RAG + Qdrant + Citation Validator thật
    runtime_state.app_mode = "live"
    try:
        resp = client.post(
            "/api/chat",
            json={
                "question": "Người lao động đơn phương chấm dứt hợp đồng lao động không xác định thời hạn phải báo trước ít nhất bao nhiêu ngày?",
                "conversation_id": None,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["app_mode"] == "live"
        assert body["is_mock"] is False
        assert len(body["citations"]) >= 1

        # Xác minh trích dẫn liên kết với chunk thật và văn bản thật trong Qdrant
        top_cit = body["citations"][0]
        assert top_cit["document_id"] == doc_id
        assert top_cit["chunk_id"] is not None and top_cit["chunk_id"].startswith(doc_id)
        assert top_cit["document_number"] == "45/2019/QH14"
        assert top_cit["article"] == "Điều 35"
        assert any(
            c["article"] == "Điều 35" and c["clause"] == "Khoản 1" and ("45 ngày" in c["evidence"] or c["point"] == "Điểm a")
            for c in body["citations"]
        )
        assert body["citation_status"] == "PASS"

        # Kiểm tra câu hỏi hoàn toàn không có căn cứ trong CSDL -> không bịa nguồn
        unrelated = client.post(
            "/api/chat",
            json={
                "question": "Thủ tục đăng ký tàu vũ trụ bay lên sao Hỏa theo quy định năm 2099 là gì?",
                "conversation_id": None,
            },
        )
        assert unrelated.status_code == 200
        u_body = unrelated.json()
        assert u_body["citation_status"] in {"UNVERIFIED", "FAIL"}
        # Nếu không truy xuất được nguồn phù hợp, không bao giờ gán PASS
        assert u_body["citation_status"] != "PASS"
    finally:
        runtime_state.app_mode = "demo"
