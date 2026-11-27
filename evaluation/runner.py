"""
Module đánh giá hệ thống theo 4 phiên bản so sánh (Nguyễn Thị Nhi phụ trách):
- Model A: LLM
- Model B: LLM + RAG
- Model C: LLM + RAG + Agent
- Model D: LLM + RAG + Agent + Citation Validator

Các chỉ số đánh giá chuẩn hóa:
- Recall@K
- Answer Accuracy
- Citation Accuracy
- Citation Completeness
- Citation Support Rate
- Hallucination Rate
- Latency (ms)
- Self-correction Rate

Nguyên tắc khoa học:
- Tuyệt đối không tự sinh đáp án AI rồi coi là Ground Truth.
- Tuyệt đối không khẳng định Model D tốt nhất nếu chưa có số liệu thực nghiệm thật.
- Xuất kết quả thực nghiệm ra CSV và JSON phục vụ báo cáo và vẽ biểu đồ.
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EVALUATION_VARIANTS = [
    "LLM",
    "LLM + RAG",
    "LLM + RAG + Agent",
    "LLM + RAG + Agent + Citation Validator",
]

DIFFICULTY_SPLITS = [
    "Easy",
    "Medium",
    "Multi-document",
    "Hard",
    "Citation-focused",
]


@dataclass
class EvaluationConfig:
    sample_size: int = 60
    top_k: int = 5
    splits: tuple[str, ...] = tuple(DIFFICULTY_SPLITS)


@dataclass
class VariantMetricsRecord:
    variant: str
    recall_at_k: float | None = None
    answer_accuracy: float | None = None
    citation_accuracy: float | None = None
    citation_completeness: float | None = None
    citation_support_rate: float | None = None
    hallucination_rate: float | None = None
    latency_ms: float | None = None
    self_correction_rate: float | None = None


def compute_recall_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int = 5) -> float | None:
    if not relevant_ids:
        return None
    top = set(retrieved_ids[:k])
    return round(len(top & relevant_ids) / len(relevant_ids), 4)


def export_evaluation_artifacts(
    records: list[VariantMetricsRecord],
    output_dir: Path,
    metadata: dict[str, Any] | None = None,
) -> tuple[Path, Path]:
    """Xuất kết quả đánh giá ra cả JSON và CSV để phục vụ báo cáo và vẽ biểu đồ."""
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"evaluation_report_{ts}.json"
    csv_path = output_dir / f"evaluation_report_{ts}.csv"

    rows = [asdict(r) for r in records]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "metadata": metadata or {},
        "variants": rows,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    fieldnames = list(rows[0].keys()) if rows else [
        "variant",
        "recall_at_k",
        "answer_accuracy",
        "citation_accuracy",
        "citation_completeness",
        "citation_support_rate",
        "hallucination_rate",
        "latency_ms",
        "self_correction_rate",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    return json_path, csv_path
