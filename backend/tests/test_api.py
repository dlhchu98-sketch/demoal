from __future__ import annotations

import io
import zipfile

from fastapi.testclient import TestClient

from agent.validator import CitationValidator
from backend.app.main import app
from backend.app.services.chat_service import runtime_state

client = TestClient(app)


def test_health_returns_200():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_system_status_endpoint():
    resp = client.get("/api/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["app_name"] == "LEGAL ASSISTANT"
    assert data["app_mode"] in {"demo", "live"}
    assert "database" in data
    assert "qdrant" in data


def test_chat_rejects_blank_question():
    resp = client.post("/api/chat", json={"question": "   ", "conversation_id": None})
    assert resp.status_code == 422


def test_chat_demo_mode_schema_and_history_lifecycle():
    runtime_state.app_mode = "demo"
    resp = client.post(
        "/api/chat",
        json={
            "question": "Sinh viên có được nghỉ học tạm thời không?",
            "conversation_id": None,
            "simulate_self_correction": True,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_mock"] is True
    assert body["app_mode"] == "demo"
    assert body["citation_status"] == "UNVERIFIED"
    assert body["self_correction"]["performed"] is True
    assert body["self_correction"]["attempts"] == 1
    assert isinstance(body["analysis"], list) and len(body["analysis"]) >= 1
    assert isinstance(body["citations"], list) and len(body["citations"]) >= 1

    req_id = body["request_id"]
    hist_list = client.get("/api/history")
    assert hist_list.status_code == 200
    assert any(item["id"] == req_id for item in hist_list.json())

    detail = client.get(f"/api/history/{req_id}")
    assert detail.status_code == 200
    assert detail.json()["question"] == "Sinh viên có được nghỉ học tạm thời không?"

    citations = client.get("/api/citations?status=UNVERIFIED")
    assert citations.status_code == 200
    assert any(c["request_id"] == req_id for c in citations.json())

    deleted = client.delete(f"/api/history/{req_id}")
    assert deleted.status_code == 200
    assert client.get(f"/api/history/{req_id}").status_code == 404


def test_chat_live_mode_does_not_fabricate_pass_without_qdrant_or_llm():
    runtime_state.app_mode = "live"
    try:
        resp = client.post(
            "/api/chat",
            json={"question": "Điều kiện hưởng trợ cấp thất nghiệp là gì?", "conversation_id": None},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["app_mode"] == "live"
        assert body["is_mock"] is False
        assert body["citation_status"] == "UNVERIFIED"
        assert body["citations"] == []
        client.delete(f"/api/history/{body['request_id']}")
    finally:
        runtime_state.app_mode = "demo"


def test_questions_documents_statistics_evaluation_endpoints():
    assert client.get("/api/questions").status_code == 200
    assert client.get("/api/questions/categories").status_code == 200
    assert client.get("/api/documents").status_code == 200
    assert client.get("/api/statistics").status_code == 200
    assert client.get("/api/evaluation/results").status_code == 200


def test_citation_validator_rule_based_logic():
    validator = CitationValidator()
    # Không cho PASS nếu nguồn là mock
    res_mock = validator.validate("Sinh viên được bảo lưu kết quả.", "Sinh viên được bảo lưu kết quả.", is_mock_source=True)
    assert res_mock.status == "UNVERIFIED"

    # Không cho PASS nếu thiếu bằng chứng
    res_empty = validator.validate("Sinh viên được bảo lưu kết quả.", "", is_mock_source=False)
    assert res_empty.status == "UNVERIFIED"

    # Phát hiện mâu thuẫn phủ định
    res_conflict = validator.validate(
        "Người lao động được làm việc vượt quá giới hạn an toàn.",
        "Nghiêm cấm người lao động làm việc vượt quá giới hạn an toàn.",
        is_mock_source=False,
    )
    assert res_conflict.status == "FAIL"

    # PASS khi bằng chứng thực tế hỗ trợ trực tiếp
    res_pass = validator.validate(
        "Người lao động có quyền đơn phương chấm dứt hợp đồng lao động khi báo trước.",
        "Người lao động có quyền đơn phương chấm dứt hợp đồng lao động nhưng phải báo trước cho người sử dụng lao động.",
        is_mock_source=False,
    )
    assert res_pass.status == "PASS"


def test_docx_upload_parser_rejects_non_docx():
    resp = client.post(
        "/api/questions/upload",
        files={"file": ("test.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 400
