from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone

from backend.app.schemas.legal import (
    ChatRequest,
    ChatResponse,
    CitationItem,
    LegalIssueItem,
    PipelineTraceStep,
    SelfCorrectionInfo,
    SelfCorrectionStep,
)


def _infer_demo_domain(question: str) -> str:
    q = question.lower()
    mapping = [
        (["sinh viên", "nghỉ học", "học phí", "đào tạo", "tín chỉ", "trường đại học"], "Giáo dục & Đào tạo"),
        (["lao động", "hợp đồng", "lương", "thử việc", "sa thải", "bảo hiểm xã hội", "nghỉ phép"], "Lao động & Việc làm"),
        (["hôn nhân", "ly hôn", "kết hôn", "con chung", "tài sản chung"], "Hôn nhân & Gia đình"),
        (["đất đai", "sổ đỏ", "nhà ở", "thuê nhà", "chuyển nhượng"], "Đất đai & Nhà ở"),
        (["giao thông", "nồng độ cồn", "giấy phép lái xe", "vượt đèn đỏ"], "Giao thông đường bộ"),
        (["hình sự", "tội phạm", "trộm cắp", "lừa đảo", "phạt tù"], "Hình sự"),
        (["doanh nghiệp", "thuế", "công ty", "kinh doanh", "hóa đơn"], "Doanh nghiệp & Thuế"),
        (["dân sự", "vay tiền", "thừa kế", "bồi thường", "di chúc"], "Dân sự"),
        (["cư trú", "tạm trú", "căn cước", "hộ khẩu"], "Cư trú & Hành chính"),
    ]
    for keywords, domain in mapping:
        if any(k in q for k in keywords):
            return domain
    return "Pháp luật chung (DEMO)"


def build_demo_chat_response(request: ChatRequest, max_attempts: int = 2) -> ChatResponse:
    """
    Tạo phản hồi mô phỏng chuẩn API contract cho DEMO MODE.
    TUYỆT ĐỐI KHÔNG tự tạo số hiệu văn bản, Điều/Khoản/Điểm giả rồi tuyên bố đã xác minh thật.
    """
    started = time.perf_counter()
    domain = _infer_demo_domain(request.question)
    req_id = str(uuid.uuid4())
    conv_id = request.conversation_id or str(uuid.uuid4())

    analysis = [
        LegalIssueItem(
            issue=f"Xác định chủ thể, quyền và nghĩa vụ liên quan đến câu hỏi trong lĩnh vực {domain}.",
            legal_domain=domain,
            sub_query=f"Quy định pháp luật hiện hành về: {request.question}",
        ),
        LegalIssueItem(
            issue="Kiểm tra điều kiện áp dụng, ngoại lệ và văn bản hướng dẫn thi hành liên quan.",
            legal_domain=domain,
            sub_query=f"Điều kiện và trình tự thủ tục liên quan đến {domain}",
        ),
    ]

    pipeline_trace = [
        PipelineTraceStep(
            stage="question_analysis",
            label="Phân tích câu hỏi",
            status="done",
            detail=f"[DEMO] Nhận diện câu hỏi tiếng Việt thuộc lĩnh vực: {domain}.",
            duration_ms=18,
        ),
        PipelineTraceStep(
            stage="issue_decomposition",
            label="Phân rã vấn đề pháp lý",
            status="done",
            detail="[DEMO] Tách thành 2 vấn đề pháp lý cần đối chiếu đa văn bản.",
            duration_ms=22,
        ),
        PipelineTraceStep(
            stage="retrieval_planning",
            label="Truy xuất kho văn bản (RAG / Qdrant)",
            status="warning",
            detail="[DEMO] Kho văn bản pháp luật thực tế chưa được nạp vào Qdrant; dùng mẫu cấu trúc DEMO.",
            duration_ms=26,
        ),
    ]

    self_correction_steps: list[SelfCorrectionStep] = []
    if request.simulate_self_correction:
        self_correction_steps = [
            SelfCorrectionStep(
                attempt=1,
                initial_status="FAIL",
                action="Mở rộng truy vấn truy xuất lại đa văn bản và loại bỏ nhận định thiếu căn cứ.",
                resulting_status="UNVERIFIED",
                detail=(
                    "[DEMO] Lần kiểm tra đầu phát hiện bằng chứng chưa đủ để hỗ trợ phát biểu (FAIL). "
                    "Agent đã truy xuất lại và chuyển câu trả lời về trạng thái thận trọng (UNVERIFIED) do kho dữ liệu thực tế chưa nạp."
                ),
            )
        ]
        pipeline_trace.append(
            PipelineTraceStep(
                stage="citation_validator",
                label="Kiểm tra trích dẫn & Tự điều chỉnh",
                status="warning",
                detail="[DEMO] Mô phỏng luồng FAIL -> Truy xuất lại -> Điều chỉnh -> UNVERIFIED (1 lần tự điều chỉnh).",
                duration_ms=34,
            )
        )
        citations = [
            CitationItem(
                claim="Cần đối chiếu trực tiếp văn bản quy phạm pháp luật đang có hiệu lực cho tình huống này.",
                document_name=f"[DEMO - Chưa nạp kho dữ liệu thật] Nhóm văn bản lĩnh vực {domain}",
                document_number=None,
                article=None,
                clause=None,
                point=None,
                evidence=(
                    "[DỮ LIỆU MÔ PHỎNG DEMO] Hệ thống đang chạy ở chế độ DEMO và chưa có đoạn trích văn bản "
                    "pháp luật thực tế trong Qdrant. Khi chuyển sang LIVE MODE và nạp dữ liệu, đoạn trích nguyên văn "
                    "Điều, Khoản, Điểm sẽ hiển thị tại đây."
                ),
                relevance_score=None,
                validation_status="UNVERIFIED",
                validation_reason=(
                    "Ở chế độ DEMO, hệ thống không gán PASS cho nguồn giả lập để tránh khẳng định sai căn cứ pháp lý."
                ),
            )
        ]
        answer = (
            f"[CHẾ ĐỘ DEMO — MÔ PHỎNG TỰ ĐIỀU CHỈNH]\n\n"
            f"Hệ thống đã tiếp nhận câu hỏi của bạn: \"{request.question}\" (lĩnh vực dự kiến: {domain}).\n\n"
            f"1. Tóm tắt quy trình xử lý: Agent đã phân rã câu hỏi thành 2 vấn đề pháp lý, mô phỏng tình huống "
            f"Citation Validator trả về FAIL ở lượt kiểm tra đầu tiên, sau đó thực hiện 1 lượt truy xuất lại và điều chỉnh câu trả lời.\n\n"
            f"2. Giới hạn dữ liệu hiện tại: Kho văn bản pháp luật Việt Nam thực tế chưa được nạp vào Qdrant và hệ thống "
            f"đang vận hành ở APP_MODE=demo, nên chưa đủ căn cứ để khẳng định Điều, Khoản, Điểm cụ thể. "
            f"Hệ thống giữ nguyên tắc không tự tạo số hiệu văn bản hoặc nội dung điều luật không có bằng chứng.\n\n"
            f"3. Hướng dẫn tiếp theo: Nạp dữ liệu văn bản pháp luật vào kho và cấu hình LLM + Qdrant ở chế độ LIVE "
            f"để nhận câu trả lời có trích dẫn được xác minh thực tế."
        )
        self_correction = SelfCorrectionInfo(
            attempts=1,
            performed=True,
            max_attempts=max_attempts,
            steps=self_correction_steps,
        )
    else:
        pipeline_trace.append(
            PipelineTraceStep(
                stage="citation_validator",
                label="Kiểm tra trích dẫn (Citation Validator)",
                status="warning",
                detail="[DEMO] Đánh dấu UNVERIFIED vì đang dùng phản hồi mô phỏng, chưa xác minh trên văn bản thật.",
                duration_ms=20,
            )
        )
        citations = [
            CitationItem(
                claim=f"Tình huống thuộc phạm vi tra cứu lĩnh vực {domain} cần căn cứ văn bản pháp luật gốc.",
                document_name=f"[DEMO] Chưa có văn bản pháp luật thực tế được nạp ({domain})",
                document_number=None,
                article=None,
                clause=None,
                point=None,
                evidence=(
                    "[DỮ LIỆU MÔ PHỎNG DEMO] Không có văn bản thực tế trong kho vector Qdrant. "
                    "Hệ thống tuân thủ nguyên tắc không bịa đặt số hiệu văn bản hay Điều/Khoản/Điểm."
                ),
                relevance_score=None,
                validation_status="UNVERIFIED",
                validation_reason=(
                    "Chưa đủ dữ liệu pháp luật thực tế để xác minh trích dẫn (APP_MODE=demo)."
                ),
            )
        ]
        answer = (
            f"[CHẾ ĐỘ DEMO — CHƯA KẾT NỐI DỮ LIỆU PHÁP LUẬT THỰC TẾ]\n\n"
            f"Câu hỏi của bạn đã đi qua đầy đủ luồng kiến trúc LEGAL ASSISTANT (FastAPI → LangGraph Agent → RAG Interface → Citation Validator).\n\n"
            f"- Lĩnh vực pháp lý nhận diện sơ bộ: {domain}.\n"
            f"- Trạng thái nguồn căn cứ: Chưa có đủ dữ liệu văn bản pháp luật thực tế được nạp trong kho Qdrant, "
            f"vì vậy hệ thống không tự suy diễn kết luận pháp lý hay tự tạo số hiệu văn bản, Điều, Khoản, Điểm.\n"
            f"- Bạn có thể bật tùy chọn \"Mô phỏng tự điều chỉnh (Self-correction)\" để xem đầy đủ quy trình "
            f"FAIL → Truy xuất lại → Điều chỉnh câu trả lời, hoặc cấu hình LIVE MODE trong trang Cài đặt."
        )
        self_correction = SelfCorrectionInfo(
            attempts=0,
            performed=False,
            max_attempts=max_attempts,
            steps=[],
        )

    elapsed_ms = max(int((time.perf_counter() - started) * 1000), 12)
    return ChatResponse(
        request_id=req_id,
        conversation_id=conv_id,
        question=request.question,
        answer=answer,
        analysis=analysis,
        citations=citations,
        citation_status="UNVERIFIED",
        self_correction=self_correction,
        pipeline_trace=pipeline_trace,
        is_mock=True,
        app_mode="demo",
        processing_time_ms=elapsed_ms,
        created_at=datetime.now(timezone.utc),
    )
