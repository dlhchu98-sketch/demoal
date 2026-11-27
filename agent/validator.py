"""
Module Citation Validator (Đặng Thị Ngọc Ánh phụ trách)
Kết hợp rule-based validation và LLM-based semantic verification.
Nguyên tắc:
- Không đánh dấu PASS chỉ vì câu trả lời có gắn tên văn bản hay đường dẫn.
- Chỉ PASS khi claim được hỗ trợ trực tiếp bởi bằng chứng pháp lý đã truy xuất.
- Trả UNVERIFIED nếu không có bằng chứng.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

ValidationStatus = Literal["PASS", "FAIL", "UNVERIFIED"]


@dataclass
class ClaimValidationResult:
    claim: str
    status: ValidationStatus
    reason: str
    overlap_ratio: float


def _tokenize_vi(text: str) -> set[str]:
    tokens = re.findall(r"[0-9A-Za-zÀ-ỹ]{2,}", text.lower())
    stopwords = {
        "của", "và", "các", "những", "được", "trong", "theo", "tại", "về",
        "cho", "với", "khi", "nếu", "thì", "một", "như", "này", "đó", "là",
    }
    return {t for t in tokens if t not in stopwords}


class CitationValidator:
    """
    Bộ kiểm tra trích dẫn kết hợp Rule-based + LLM hook.
    """

    def __init__(self, llm_verifier=None, min_overlap: float = 0.25):
        self.llm_verifier = llm_verifier
        self.min_overlap = min_overlap

    def validate(self, claim: str, evidence: str, is_mock_source: bool = False) -> ClaimValidationResult:
        if is_mock_source:
            return ClaimValidationResult(
                claim=claim,
                status="UNVERIFIED",
                reason="Nguồn trích dẫn là dữ liệu mô phỏng DEMO, không thể xác nhận PASS thực tế.",
                overlap_ratio=0.0,
            )

        if not evidence or not evidence.strip():
            return ClaimValidationResult(
                claim=claim,
                status="UNVERIFIED",
                reason="Không có nội dung bằng chứng pháp lý để đối chiếu.",
                overlap_ratio=0.0,
            )

        claim_tokens = _tokenize_vi(claim)
        evidence_tokens = _tokenize_vi(evidence)
        if not claim_tokens or not evidence_tokens:
            return ClaimValidationResult(
                claim=claim,
                status="UNVERIFIED",
                reason="Không đủ nội dung ngữ nghĩa để đối chiếu claim và bằng chứng.",
                overlap_ratio=0.0,
            )

        overlap = len(claim_tokens & evidence_tokens) / max(len(claim_tokens), 1)

        # Kiểm tra mâu thuẫn phủ định cơ bản (rule-based)
        negation_claim = bool(re.search(r"\b(không được|nghiêm cấm|bị cấm)\b", claim.lower()))
        negation_evidence = bool(re.search(r"\b(không được|nghiêm cấm|bị cấm)\b", evidence.lower()))
        if negation_claim != negation_evidence and overlap >= self.min_overlap:
            return ClaimValidationResult(
                claim=claim,
                status="FAIL",
                reason="Phát hiện dấu hiệu mâu thuẫn về tính cho phép/nghiêm cấm giữa claim và bằng chứng.",
                overlap_ratio=round(overlap, 3),
            )

        if overlap < self.min_overlap:
            return ClaimValidationResult(
                claim=claim,
                status="FAIL",
                reason=(
                    f"Bằng chứng được dẫn không đủ liên quan trực tiếp để chứng minh nhận định "
                    f"(độ khớp từ khóa pháp lý: {overlap:.0%} < {self.min_overlap:.0%})."
                ),
                overlap_ratio=round(overlap, 3),
            )

        # Hook LLM verifier nếu đã cấu hình trong LIVE MODE
        if self.llm_verifier is not None:
            llm_ok, llm_reason = self.llm_verifier(claim, evidence)
            return ClaimValidationResult(
                claim=claim,
                status="PASS" if llm_ok else "FAIL",
                reason=llm_reason,
                overlap_ratio=round(overlap, 3),
            )

        return ClaimValidationResult(
            claim=claim,
            status="PASS",
            reason=f"Bằng chứng hỗ trợ nội dung claim qua đối chiếu rule-based (độ khớp: {overlap:.0%}).",
            overlap_ratio=round(overlap, 3),
        )
