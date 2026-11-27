from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from backend.app.schemas.legal import QuestionCategory, QuestionItem

WORD_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def extract_docx_paragraphs(docx_path: Path) -> list[tuple[str, str]]:
    """
    Đọc toàn bộ đoạn văn từ tệp .docx bằng thư viện chuẩn Python (zipfile + xml),
    trả về danh sách (style_name, text) giữ nguyên nội dung gốc (có tách tab/khoảng trắng sạch).
    """
    paragraphs: list[tuple[str, str]] = []
    with zipfile.ZipFile(docx_path, "r") as zf:
        if "word/document.xml" not in zf.namelist():
            raise ValueError("Tệp .docx không hợp lệ (thiếu word/document.xml).")
        xml_bytes = zf.read("word/document.xml")

    root = ET.fromstring(xml_bytes)
    body = root.find("w:body", WORD_NS)
    if body is None:
        return paragraphs

    w_t = f"{{{WORD_NS['w']}}}t"
    w_tab = f"{{{WORD_NS['w']}}}tab"
    w_br = f"{{{WORD_NS['w']}}}br"

    for p in body.findall(".//w:p", WORD_NS):
        p_style = ""
        p_pr = p.find("w:pPr", WORD_NS)
        if p_pr is not None:
            style_el = p_pr.find("w:pStyle", WORD_NS)
            if style_el is not None:
                p_style = style_el.attrib.get(f"{{{WORD_NS['w']}}}val", "")

        parts: list[str] = []
        for elem in p.iter():
            if elem.tag == w_t and elem.text:
                parts.append(elem.text)
            elif elem.tag == w_tab:
                parts.append(" ")
            elif elem.tag == w_br:
                parts.append(" ")

        line = re.sub(r"\s+", " ", "".join(parts)).strip()
        if line:
            paragraphs.append((p_style, line))

    return paragraphs


def _is_toc_paragraph(style: str, text: str) -> bool:
    st = style.lower()
    if st.startswith("toc"):
        return True
    if text.strip().upper() == "MỤC LỤC":
        return True
    return False


def _is_major_domain_heading(style: str, text: str) -> bool:
    st = style.lower()
    if st in {"heading1", "heading 1"}:
        return True
    if re.match(r"^[IVXLCDM]+\.\s+[A-ZÀ-Ỹ\s&,\-]+$", text):
        return True
    return False


def _is_category_heading(style: str, text: str) -> bool:
    st = style.lower()
    if st.startswith("heading"):
        return True
    if re.match(r"^(chủ đề|nhóm|phần|mục|lĩnh vực)\s*\d+", text, flags=re.IGNORECASE):
        return True
    if re.match(r"^[IVXLCDM]+\.\s+\S+", text):
        return True
    if re.match(r"^\d+(\.\d+)?\.\s+[^?]+$", text) and len(text) <= 120 and "?" not in text:
        return True
    return False


def _clean_heading_label(text: str) -> str:
    return re.sub(r"^\s*(\d+(?:\.\d+)*\.?|[IVXLCDM]+\.)\s*", "", text).strip() or text.strip()


def _split_question_prefix(text: str) -> tuple[str | None, str]:
    """
    Tách mã đánh số đầu câu hỏi (ví dụ: '1.1.1Hợp đồng...' hoặc '1.1.1 Hợp đồng...' hoặc 'Câu 1: ...')
    nhưng GIỮ NGUYÊN 100% nội dung câu hỏi gốc.
    """
    m = re.match(r"^(\d+\.\d+\.\d+)\s*(.+)$", text)
    if m:
        return m.group(1), m.group(2).strip()
    m2 = re.match(r"^(?:Câu\s*(\d+)\s*[:.\-]?|(\d+)\))\s*(.+)$", text, flags=re.IGNORECASE)
    if m2:
        code = m2.group(1) or m2.group(2)
        return f"C{code}", m2.group(3).strip()
    return None, text.strip()


def _infer_difficulty(question: str, domain: str, category: str) -> str:
    """
    Phân loại mức độ khó phục vụ lọc gợi ý và kiểm thử:
    Easy | Medium | Multi-document | Hard | Citation-focused
    """
    q = question.lower()
    if any(k in q for k in ["bao nhiêu", "tối đa", "tối thiểu", "thời hiệu", "thời hạn", "mức phạt", "mức hưởng", "tuổi tối thiểu", "bao lâu"]):
        return "Citation-focused"
    if any(k in q for k in ["dân sự và hình sự", "nước ngoài", "phá sản", "đồng thời", "hai công ty", "cả khoản nợ", "vừa", "khác gì", "khác nhau thế nào"]):
        return "Multi-document"
    if any(k in q for k in ["tranh chấp", "khởi kiện", "vô hiệu", "bồi thường", "khiếu nại", "tố cáo", "sa thải", "thừa kế thế vị", "bạo lực", "tín dụng đen"]):
        return "Hard"
    if any(k in q for k in ["thủ tục", "điều kiện", "trình tự", "hồ sơ", "xử lý thế nào", "làm gì", "làm sao"]):
        return "Medium"
    return "Easy"


def _is_question_line(text: str) -> bool:
    if "?" in text:
        return True
    if re.match(r"^(\d+\.\d+\.\d+|câu\s*\d+|-\s+|\•\s+|\d+\)\s+)", text, flags=re.IGNORECASE):
        return True
    return False


def parse_legal_questions_docx(docx_path: Path) -> tuple[list[QuestionCategory], list[QuestionItem]]:
    """
    Phân tích đầy đủ toàn bộ file Bộ câu hỏi pháp luật.docx:
    - Bỏ qua Mục lục (TOC1/TOC2).
    - Giữ nguyên nội dung câu hỏi gốc.
    - Ghi nhận cả lĩnh vực lớn (domain: Dân sự, Giáo dục, Giao thông, Lao động...) và nhóm chủ đề chi tiết.
    - Gắn mức độ khó (Easy / Medium / Multi-document / Hard / Citation-focused).
    """
    paragraphs = extract_docx_paragraphs(docx_path)
    categories: list[QuestionCategory] = []
    questions: list[QuestionItem] = []

    current_domain = "Pháp luật Việt Nam"
    current_cat_id = 0
    current_cat_name = ""
    counts: dict[int, int] = {}
    q_counter = 0

    for style, text in paragraphs:
        if _is_toc_paragraph(style, text):
            continue

        # Bỏ qua dòng tiêu đề tài liệu trước khi vào mục nội dung đầu tiên
        if current_cat_id == 0 and re.match(
            r"^(tổng hợp tình huống|phân loại theo nhóm|bộ câu hỏi|danh sách câu hỏi)",
            text,
            flags=re.IGNORECASE,
        ):
            continue

        if _is_major_domain_heading(style, text) and not text.endswith("?"):
            current_domain = _clean_heading_label(text)
            continue

        if _is_category_heading(style, text) and not text.endswith("?"):
            clean_heading = _clean_heading_label(text)
            current_cat_id += 1
            current_cat_name = clean_heading
            counts[current_cat_id] = 0
            categories.append(
                QuestionCategory(
                    id=current_cat_id,
                    name=current_cat_name,
                    domain=current_domain,
                    question_count=0,
                )
            )
            continue

        if _is_question_line(text) or current_cat_id > 0:
            if current_cat_id == 0:
                current_cat_id = 1
                current_cat_name = current_domain
                counts[current_cat_id] = 0
                categories.append(
                    QuestionCategory(
                        id=current_cat_id,
                        name=current_cat_name,
                        domain=current_domain,
                        question_count=0,
                    )
                )
            q_code, clean_q = _split_question_prefix(text)
            if not clean_q:
                continue
            q_counter += 1
            counts[current_cat_id] = counts.get(current_cat_id, 0) + 1
            questions.append(
                QuestionItem(
                    id=f"Q-{q_counter:04d}",
                    question_code=q_code,
                    domain=current_domain,
                    category_id=current_cat_id,
                    category_name=current_cat_name,
                    difficulty=_infer_difficulty(clean_q, current_domain, current_cat_name),
                    question=clean_q,
                    source_file=docx_path.name,
                )
            )

    for cat in categories:
        cat.question_count = counts.get(cat.id, 0)

    non_empty_cats = [c for c in categories if c.question_count > 0]
    if non_empty_cats:
        categories = non_empty_cats

    return categories, questions


def export_questions_json(
    docx_path: Path,
    output_dir: Path,
) -> tuple[Path, Path, int, int]:
    """
    Xuất bộ câu hỏi đã phân loại sang JSON (QUESTION DATASET — tuyệt đối không nạp vào Qdrant)
    và tạo tệp benchmark 60 câu phân tầng theo mức độ khó (ground_truth để pending_expert_review).
    """
    categories, questions = parse_legal_questions_docx(docx_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    full_path = output_dir / "questions_dataset.json"
    full_payload = {
        "dataset_type": "QUESTION_DATASET_ONLY_DO_NOT_INDEX_IN_QDRANT",
        "source_file": docx_path.name,
        "total_domains": len({c.domain for c in categories}),
        "total_categories": len(categories),
        "total_questions": len(questions),
        "domains": sorted({c.domain for c in categories}),
        "categories": [c.model_dump() for c in categories],
        "questions": [q.model_dump() for q in questions],
    }
    full_path.write_text(json.dumps(full_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    # Chọn 60 câu phân tầng đều theo 5 nhóm độ khó để làm bộ khung đánh giá
    buckets: dict[str, list[QuestionItem]] = {
        "Easy": [],
        "Medium": [],
        "Multi-document": [],
        "Hard": [],
        "Citation-focused": [],
    }
    for q in questions:
        buckets.setdefault(q.difficulty, []).append(q)

    selected: list[dict] = []
    target_per_bucket = 12
    for diff, items in buckets.items():
        for q in items[:target_per_bucket]:
            selected.append(
                {
                    "id": q.id,
                    "question_code": q.question_code,
                    "domain": q.domain,
                    "category_name": q.category_name,
                    "difficulty": q.difficulty,
                    "question": q.question,
                    "reference_answer": None,
                    "reference_citations": [],
                    "ground_truth_status": "pending_expert_review",
                    "note": "Chưa có đáp án tham chiếu được chuyên gia/thành viên dữ liệu xác nhận; không tự sinh Ground Truth.",
                }
            )

    bench_path = output_dir / "benchmark_questions.json"
    bench_payload = {
        "dataset_type": "EVALUATION_BENCHMARK_QUESTIONS",
        "source_file": docx_path.name,
        "total_benchmark_questions": len(selected),
        "ground_truth_policy": "Không tự sinh đáp án AI rồi coi là Ground Truth; yêu cầu xác nhận bởi thành viên phụ trách dữ liệu hoặc chuyên môn pháp lý.",
        "difficulty_distribution": {
            diff: sum(1 for item in selected if item["difficulty"] == diff) for diff in buckets
        },
        "items": selected,
    }
    bench_path.write_text(json.dumps(bench_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return full_path, bench_path, len(categories), len(questions)
