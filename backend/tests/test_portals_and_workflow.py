"""
Kiểm thử toàn diện luồng User Portal, Admin Portal, Question Bank (chống lọt Mục lục TOC),
7 bước tiến trình thật, cấu trúc kết quả A-E, Saved Items, Feedback, RAG/Agent APIs
và các tình huống đặc biệt của Citation Validator (Mục 8.4).
"""

from __future__ import annotations

from pathlib import Path
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import pytest

from backend.app.core.database import Base, get_db
from backend.app.main import app
from backend.app.services import legal_ingestion_service as lis_module
from backend.app.services.chat_service import runtime_state
from backend.app.services.legal_ingestion_service import LegalIngestionService
from rag.retriever import DEFAULT_FASTEMBED_VI_MODEL, QdrantLegalRetriever, close_local_qdrant_client

client = TestClient(app)


def test_dual_portal_routes_and_static_assets():
    for path in ["/", "/user", "/admin", "/login"]:
        resp = client.get(path)
        assert resp.status_code == 200
        assert "LEGAL AI" in resp.text

    for js_asset in ["/static/js/api.js", "/static/js/user-portal.js", "/static/js/admin-portal.js"]:
        resp = client.get(js_asset)
        assert resp.status_code == 200
        assert len(resp.text) > 500


def test_question_bank_clean_parsing_no_toc_and_filters():
    resp = client.get("/api/questions?page=1&page_size=20")
    assert resp.status_code == 200
    body = resp.json()
    assert body["loaded"] is True
    assert body["total_domains"] >= 4
    assert body["total_categories"] >= 15
    assert body["total_questions"] >= 250

    # Đảm bảo KHÔNG bị lọt các dòng mục lục (TOC) như "DÂN SỰ2" hoặc "1.1. Hợp đồng2"
    for item in body["items"]:
        assert not item["question"].startswith("1.1.")
        assert not item["category_name"].endswith("2")
        assert item["difficulty"] in {"Easy", "Medium", "Multi-document", "Hard", "Citation-focused"}

    # Lọc theo domain & difficulty
    filtered = client.get("/api/questions", params={"domain": "LAO ĐỘNG", "difficulty": "Citation-focused"})
    assert filtered.status_code == 200
    f_body = filtered.json()
    assert f_body["total_questions"] >= 1
    assert all(q["domain"] == "LAO ĐỘNG" and q["difficulty"] == "Citation-focused" for q in f_body["items"])


def test_chat_7_steps_structured_output_conversations_feedback_and_saved():
    runtime_state.app_mode = "demo"

    # Lượt 1
    r1 = client.post(
        "/api/chat",
        json={"question": "Hợp đồng miệng có giá trị pháp lý không?", "simulate_self_correction": True},
    )
    assert r1.status_code == 200
    b1 = r1.json()
    assert b1["is_mock"] is True
    assert b1["citation_status"] == "UNVERIFIED"
    assert b1["conclusion"]
    assert b1["explanation"]
    assert len(b1["limitations"]) >= 1
    assert b1["processing_status"]["total_steps"] == 7
    assert len(b1["processing_status"]["steps"]) == 7
    # Không giả lập toàn xanh trong chế độ DEMO
    assert any(st["status"] == "warning" for st in b1["processing_status"]["steps"])

    conv_id = b1["conversation_id"]
    req1_id = b1["request_id"]

    # Lượt 2 cùng conversation_id (hội thoại nhiều lượt)
    r2 = client.post(
        "/api/chat",
        json={"question": "Khi nào hợp đồng bắt buộc phải công chứng?", "conversation_id": conv_id},
    )
    assert r2.status_code == 200
    assert r2.json()["conversation_id"] == conv_id

    # Lấy chi tiết cuộc hội thoại -> có đúng 2 lượt
    conv_msgs = client.get(f"/api/chat/conversations/{conv_id}")
    assert conv_msgs.status_code == 200
    assert len(conv_msgs.json()) == 2

    # Gửi đánh giá feedback
    fb = client.post(
        f"/api/chat/{req1_id}/feedback",
        json={"rating": 5, "helpful": True, "comment": "Rất rõ ràng"},
    )
    assert fb.status_code == 200
    assert fb.json()["rating"] == 5

    # Lưu câu trả lời (Saved Items CRUD)
    sav = client.post(
        "/api/saved",
        json={
            "item_type": "answer",
            "target_id": req1_id,
            "title": b1["question"],
            "subtitle": "DEMO",
            "content": b1["answer"],
        },
    )
    assert sav.status_code == 201
    sav_id = sav.json()["id"]
    assert any(it["id"] == sav_id for it in client.get("/api/saved?item_type=answer").json())
    assert client.delete(f"/api/saved/{sav_id}").status_code == 200

    # Agent logs đã ghi nhận lượt chạy
    logs = client.get("/api/agent/logs?limit=10")
    assert logs.status_code == 200
    assert any(lg["request_id"] == req1_id for lg in logs.json())

    # Xóa cuộc hội thoại dọn sạch dữ liệu test
    del_conv = client.delete(f"/api/chat/conversations/{conv_id}")
    assert del_conv.status_code == 200
    assert del_conv.json()["deleted_messages"] == 2


def test_agent_analyze_and_citation_report_endpoints():
    an = client.post(
        "/api/agent/analyze",
        json={"question": "Gây tai nạn giao thông mà nạn nhân bị thương thì trách nhiệm dân sự và hình sự ra sao?"},
    )
    assert an.status_code == 200
    body = an.json()
    assert body["needs_multi_document"] is True
    assert len(body["issues"]) >= 2

    rep = client.get("/api/citations/report")
    assert rep.status_code == 200
    assert "total_checked" in rep.json()
    assert "valid_count" in rep.json()


@pytest.fixture()
def isolated_corpus_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    docs_dir = tmp_path / "legal_documents"
    docs_dir.mkdir(parents=True, exist_ok=True)
    qdrant_dir = tmp_path / "qdrant_storage"
    db_file = tmp_path / "test_workflow.db"

    engine = create_engine(f"sqlite:///{db_file.as_posix()}", future=True, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    retriever = QdrantLegalRetriever(
        qdrant_url="http://localhost:6333",
        collection_name="test_workflow_docs",
        embedding_model=DEFAULT_FASTEMBED_VI_MODEL,
        qdrant_mode="local",
        qdrant_local_path=str(qdrant_dir),
    )
    service = LegalIngestionService(documents_dir=docs_dir, retriever=retriever, project_root=tmp_path)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr("backend.app.api.routes.legal_ingestion_service", service)
    monkeypatch.setattr("backend.app.services.chat_service.legal_ingestion_service", service)
    monkeypatch.setattr(lis_module, "legal_ingestion_service", service)

    yield TestClient(app)

    app.dependency_overrides.pop(get_db, None)
    runtime_state.app_mode = "demo"
    close_local_qdrant_client(str(qdrant_dir))
    engine.dispose()


def test_citation_validator_edge_cases_and_document_crud(isolated_corpus_env: TestClient):
    tc = isolated_corpus_env

    # 1. Tạo văn bản pháp luật qua API POST /api/legal-documents/create
    create_resp = tc.post(
        "/api/legal-documents/create",
        json={
            "filename": "bo_luat_lao_dong_test.json",
            "title": "Bộ luật Lao động 2019",
            "document_number": "45/2019/QH14",
            "document_type": "Bộ luật",
            "issuing_authority": "QUỐC HỘI",
            "effective_date": "2021-01-01",
            "status": "Đang áp dụng (dữ liệu kiểm thử)",
            "content": (
                "Điều 35. Quyền đơn phương chấm dứt hợp đồng lao động của người lao động\n"
                "1. Người lao động có quyền đơn phương chấm dứt hợp đồng lao động nhưng phải báo trước cho người sử dụng lao động ít nhất 45 ngày nếu làm việc theo hợp đồng lao động không xác định thời hạn.\n"
                "Điều 8. Các hành vi bị nghiêm cấm trong lĩnh vực lao động\n"
                "1. Nghiêm cấm phân biệt đối xử trong lao động và cưỡng bức lao động."
            ),
        },
    )
    assert create_resp.status_code == 200
    doc_id = create_resp.json()["document_id"]
    assert create_resp.json()["qdrant_sync_status"] == "synced"

    # 2. Chỉnh sửa metadata qua PUT /api/legal-documents/{id}
    upd = tc.put(f"/api/legal-documents/{doc_id}", json={"source": "Cổng TTĐT Quốc hội"})
    assert upd.status_code == 200
    assert upd.json()["source"] == "Cổng TTĐT Quốc hội"

    # 3. RAG Search API trả về đúng chunk Điều 35
    rag_res = tc.post("/api/rag/search", json={"query": "đơn phương chấm dứt hợp đồng lao động báo trước 45 ngày", "top_k": 3})
    assert rag_res.status_code == 200
    assert rag_res.json()["qdrant_available"] is True
    assert rag_res.json()["total_hits"] >= 1
    assert any(h["article"] == "Điều 35" for h in rag_res.json()["hits"])

    # 4. Citation Validator — Trích dẫn ĐÚNG hoàn toàn -> PASS
    cv_pass = tc.post(
        "/api/citations/validate",
        json={
            "claim": "Người lao động có quyền đơn phương chấm dứt hợp đồng lao động và báo trước ít nhất 45 ngày.",
            "document_number": "45/2019/QH14",
            "article": "Điều 35",
            "clause": "Khoản 1",
        },
    )
    assert cv_pass.status_code == 200
    assert cv_pass.json()["validation_status"] == "PASS"
    assert cv_pass.json()["checks"]["document_exists"] is True
    assert cv_pass.json()["checks"]["number_valid"] is True
    assert cv_pass.json()["checks"]["structure_exists"] is True

    # 5. Citation Validator — Sai số hiệu văn bản -> FAIL
    cv_wrong_num = tc.post(
        "/api/citations/validate",
        json={
            "claim": "Người lao động được nghỉ phép.",
            "document_number": "999/2099/QH99",
            "article": "Điều 35",
        },
    )
    assert cv_wrong_num.status_code == 200
    assert cv_wrong_num.json()["validation_status"] == "FAIL"
    assert cv_wrong_num.json()["checks"]["document_exists"] is False

    # 6. Citation Validator — Sai Điều luật không tồn tại -> FAIL
    cv_wrong_art = tc.post(
        "/api/citations/validate",
        json={
            "claim": "Quy định tại Điều 999.",
            "document_number": "45/2019/QH14",
            "article": "Điều 999",
        },
    )
    assert cv_wrong_art.status_code == 200
    assert cv_wrong_art.json()["validation_status"] == "FAIL"
    assert cv_wrong_art.json()["checks"]["structure_exists"] is False

    # 7. Citation Validator — Trích dẫn có thật nhưng MÂU THUẪN với kết luận -> FAIL
    cv_contra = tc.post(
        "/api/citations/validate",
        json={
            "claim": "Người sử dụng lao động được phép phân biệt đối xử trong lao động và cưỡng bức lao động.",
            "document_number": "45/2019/QH14",
            "article": "Điều 8",
            "clause": "Khoản 1",
        },
    )
    assert cv_contra.status_code == 200
    assert cv_contra.json()["validation_status"] == "FAIL"
    assert cv_contra.json()["support_status"] == "CONTRADICTED"

    # 8. Re-ingest văn bản thành công
    reing = tc.post(f"/api/legal-documents/{doc_id}/reingest")
    assert reing.status_code == 200
    assert reing.json()["qdrant_sync_status"] == "synced"


def _make_minimal_docx_bytes(paragraphs: list[str]) -> bytes:
    import io, zipfile
    p_xml = "".join(
        f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs
    )
    doc_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{p_xml}</w:body></w:document>"
    ).encode("utf-8")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("word/document.xml", doc_xml)
    return buf.getvalue()


def _make_minimal_pdf_bytes(text_line: str) -> bytes:
    # Minimal valid PDF 1.4 with one text stream readable by pypdf
    stream = f"BT /F1 12 Tf 50 750 Td ({text_line}) Tj ET".encode("latin-1")
    objs = [
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n",
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n",
        f"4 0 obj << /Length {len(stream)} >> stream\n".encode("ascii") + stream + b"\nendstream endobj\n",
        b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objs:
        offsets.append(len(out))
        out.extend(obj)
    xref_pos = len(out)
    out.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode("ascii"))
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode("ascii"))
    out.extend(f"trailer << /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode("ascii"))
    return bytes(out)


def test_folder_upload_auto_filters_and_converts_doc_docx_pdf(isolated_corpus_env: TestClient):
    tc = isolated_corpus_env

    docx_bytes = _make_minimal_docx_bytes([
        "QUỐC HỘI",
        "Số: 43/2019/QH14",
        "LUẬT GIÁO DỤC",
        "Điều 1. Phạm vi điều chỉnh",
        "Luật này quy định về hệ thống giáo dục quốc dân; cơ sở giáo dục, nhà giáo, người học.",
    ])
    html_doc_bytes = (
        "<html><body><p>CHÍNH PHỦ</p><p>Số: 100/2019/NĐ-CP</p><p>NGHỊ ĐỊNH</p>"
        "<p>Điều 1. Phạm vi điều chỉnh</p><p>Quy định xử phạt vi phạm hành chính trong lĩnh vực giao thông.</p>"
        "</body></html>"
    ).encode("utf-8")
    pdf_bytes = _make_minimal_pdf_bytes("Dieu 1. Pham vi dieu chinh ve hop dong dan su.")
    txt_bytes = "QUỐC HỘI\nSố: 91/2015/QH13\nBỘ LUẬT DÂN SỰ\nĐiều 1. Phạm vi điều chỉnh\nBộ luật này quy định địa vị pháp lý.".encode("utf-8")

    files = [
        ("files", ("kho_phap_luat/luat_giao_duc.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")),
        ("files", ("kho_phap_luat/nghi_dinh_100.doc", html_doc_bytes, "application/msword")),
        ("files", ("kho_phap_luat/hop_dong.pdf", pdf_bytes, "application/pdf")),
        ("files", ("kho_phap_luat/bo_luat_dan_su.txt", txt_bytes, "text/plain")),
        # Các tệp rác/không hỗ trợ phải được tự động lọc bỏ sạch
        ("files", ("kho_phap_luat/~$temp_lock.docx", b"lock", "application/octet-stream")),
        ("files", ("kho_phap_luat/Thumbs.db", b"junk", "application/octet-stream")),
        ("files", ("kho_phap_luat/anh_minh_hoa.png", b"\x89PNG", "image/png")),
        ("files", ("kho_phap_luat/bang_tinh.xlsx", b"PK", "application/octet-stream")),
    ]

    resp = tc.post("/api/legal-documents/upload-folder", files=files)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total_received"] == 8
    assert body["supported_count"] == 4
    assert body["filtered_out_count"] == 4
    assert body["converted_count"] == 3  # .docx + .doc + .pdf
    assert body["ingested_count"] == 4
    assert body["error_count"] == 0

    # Kiểm tra cả 4 văn bản đã được đồng bộ sạch vào DB và Qdrant
    listing = tc.get("/api/legal-documents").json()
    assert listing["total_documents"] == 4
    assert listing["synced_documents"] == 4

