"""
Module RAG (Nguyễn Thanh Hiền phụ trách)
Luồng xử lý dữ liệu:
File đầu vào (.txt / .json) -> Parse -> Clean & Normalize -> Structural Chunking
-> Chunk Validation -> Embedding -> Qdrant

Nguyên tắc bắt buộc:
- Không tự tạo văn bản pháp luật giả.
- Không tự bịa số hiệu, cơ quan ban hành, ngày hiệu lực, trạng thái hiệu lực hay cấu trúc Điều/Khoản/Điểm.
- Bảo toàn 100% nội dung pháp luật gốc khi chia chunk.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

SUPPORTED_EXTENSIONS = {".txt", ".json"}


class LegalDocumentParseError(ValueError):
    """Lỗi khi đọc, kiểm tra định dạng hoặc phân tích tệp văn bản pháp luật."""


class ChunkValidationError(ValueError):
    """Lỗi khi kiểm tra tính toàn vẹn của danh sách chunk trước khi lưu."""


@dataclass
class LegalDocumentChunk:
    chunk_id: str
    document_id: str = ""
    document_name: str = ""
    document_number: str | None = None
    document_type: str | None = None
    issuing_authority: str | None = None
    issue_date: str | None = None
    effective_date: str | None = None
    expiry_date: str | None = None
    document_status: str | None = None
    part: str | None = None
    chapter: str | None = None
    section: str | None = None
    article: str | None = None
    clause: str | None = None
    point: str | None = None
    content: str = ""
    embedding_text: str = ""
    source: str | None = None
    source_file: str = ""
    page_number: int | None = None
    chunk_index: int = 0
    needs_review: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def document_title(self) -> str:
        return self.document_name

    @property
    def issued_date(self) -> str | None:
        return self.issue_date


@dataclass
class ParsedLegalDocument:
    title: str
    document_number: str | None
    document_type: str | None
    issuing_authority: str | None
    issue_date: str | None
    effective_date: str | None
    expiry_date: str | None
    status: str | None
    source: str | None
    file_path: str
    checksum: str
    content: str
    version: str | None = None
    pre_structured_chunks: list[dict[str, Any]] | None = None


# ---------------------------------------------------------------------------
# Regex nhận diện cấu trúc văn bản quy phạm pháp luật Việt Nam
# ---------------------------------------------------------------------------
RE_PART = re.compile(
    r"^(PHẦN\s+(?:THỨ\s+[A-ZÀ-Ỹ]+|[IVXLCDM]+|\d+))(?:\s*[:.\-]?\s*(.*))?$",
    flags=re.IGNORECASE,
)
RE_CHAPTER = re.compile(
    r"^(CHƯƠNG\s+(?:[IVXLCDM]+|\d+))(?:\s*[:.\-]?\s*(.*))?$",
    flags=re.IGNORECASE,
)
RE_SECTION = re.compile(
    r"^(MỤC\s+(?:[IVXLCDM]+|\d+))(?:\s*[:.\-]?\s*(.*))?$",
    flags=re.IGNORECASE,
)
RE_ARTICLE = re.compile(
    r"^(Điều\s+\d+[a-zA-Z]?)(?:\s*([.\-:])\s*(.*)|\s+(.*)|$)",
    flags=re.IGNORECASE,
)
RE_CLAUSE = re.compile(r"^(\d+)\.\s+(.+)$")
RE_POINT = re.compile(r"^([a-zđ])\)\s+(.+)$")
RE_PAGE_MARKER = re.compile(r"^(?:\[(?:Trang|Page)\s*(\d+)\]|---\s*(?:Trang|Page)\s*(\d+)\s*---)$", flags=re.IGNORECASE)

LEGAL_DOC_TYPES = [
    "Hiến pháp",
    "Bộ luật",
    "Luật",
    "Pháp lệnh",
    "Nghị quyết",
    "Nghị định",
    "Quyết định",
    "Thông tư liên tịch",
    "Thông tư",
    "Chỉ thị",
    "Quy chế",
    "Quy định",
]

KNOWN_AUTHORITY_PATTERNS = [
    r"^(QUỐC HỘI)\b",
    r"^(ỦY BAN THƯỜNG VỤ QUỐC HỘI)\b",
    r"^(CHỦ TỊCH NƯỚC)\b",
    r"^(CHÍNH PHỦ)\b",
    r"^(THỦ TƯỚNG CHÍNH PHỦ)\b",
    r"^(TÒA ÁN NHÂN DÂN TỐI CAO)\b",
    r"^(VIỆN KIỂM SÁT NHÂN DÂN TỐI CAO)\b",
    r"^(HỘI ĐỒNG THẨM PHÁN TÒA ÁN NHÂN DÂN TỐI CAO)\b",
    r"^(BỘ\s+[A-ZÀ-Ỹ\s,\-]{3,80})$",
    r"^(ỦY BAN NHÂN DÂN\s+[A-ZÀ-Ỹ\s,\-]{2,80})$",
    r"^(HỘI ĐỒNG NHÂN DÂN\s+[A-ZÀ-Ỹ\s,\-]{2,80})$",
    r"^(NGÂN HÀNG NHÀ NƯỚC VIỆT NAM)\b",
    r"^(KIỂM TOÁN NHÀ NƯỚC)\b",
]


def compute_checksum(raw_bytes: bytes) -> str:
    """Tính mã SHA-256 kiểm tra tính toàn vẹn và chống nạp trùng."""
    return hashlib.sha256(raw_bytes).hexdigest()


def clean_legal_text(raw_text: str) -> str:
    """Làm sạch ký tự thừa, chuẩn hóa Unicode NFC nhưng bảo toàn nguyên văn cấu trúc Điều/Khoản/Điểm."""
    if not raw_text:
        return ""
    cleaned = raw_text.lstrip("\ufeff")
    normalized = unicodedata.normalize("NFC", cleaned)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in normalized.split("\n")]
    return "\n".join(line for line in lines if line)


def normalize_date_str(raw: Any) -> str | None:
    """Chuẩn hóa ngày hợp lệ sang ISO YYYY-MM-DD nếu có căn cứ rõ ràng; trả None nếu rỗng/không hợp lệ."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or s.lower() in {"null", "none", "chưa xác định", "n/a", "-"}:
        return None

    # ISO YYYY-MM-DD
    m_iso = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", s)
    if m_iso:
        y, mo, d = int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3))
        try:
            return date(y, mo, d).isoformat()
        except ValueError:
            return None

    # DD/MM/YYYY hoặc DD-MM-YYYY
    m_dmy = re.match(r"^(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})$", s)
    if m_dmy:
        d, mo, y = int(m_dmy.group(1)), int(m_dmy.group(2)), int(m_dmy.group(3))
        try:
            return date(y, mo, d).isoformat()
        except ValueError:
            return None

    # ngày DD tháng MM năm YYYY
    m_vi = re.search(r"ngày\s+(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})", s, flags=re.IGNORECASE)
    if m_vi:
        d, mo, y = int(m_vi.group(1)), int(m_vi.group(2)), int(m_vi.group(3))
        try:
            return date(y, mo, d).isoformat()
        except ValueError:
            return None

    return None


def _clean_optional_str(val: Any) -> str | None:
    if val is None:
        return None
    s = str(val).strip()
    if not s or s.lower() in {"null", "none"}:
        return None
    return s


def _extract_date_from_phrase(text: str, patterns: list[str]) -> str | None:
    for pat in patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            found = normalize_date_str(m.group(1))
            if found:
                return found
    return None


def extract_metadata_from_header(text: str, filename: str) -> dict[str, Any]:
    """
    Trích xuất metadata CÓ CĂN CỨ từ nội dung văn bản.
    - Không tự bịa số hiệu, cơ quan ban hành, ngày hiệu lực hay trạng thái hiệu lực.
    - Nếu không tìm thấy thông tin đáng tin cậy thì để None.
    """
    cleaned = clean_legal_text(text)
    lines = cleaned.split("\n")
    header_window = "\n".join(lines[:40])
    header_short = "\n".join(lines[:20])

    # 1. Số hiệu văn bản (chỉ lấy khi có tiền tố "Số:" hoặc "Số ")
    doc_num = None
    doc_num_match = re.search(
        r"(?:^|\s)Số\s*[:]\s*([0-9A-Za-zÀ-ỹ/\-\.]+)",
        header_window,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    if doc_num_match:
        doc_num = doc_num_match.group(1).strip(".,; ")

    # 2. Loại văn bản (chỉ lấy khi xuất hiện rõ ở phần tiêu đề/đầu văn bản)
    doc_type: str | None = None
    type_line_idx: int | None = None
    for idx, line in enumerate(lines[:25]):
        for candidate in LEGAL_DOC_TYPES:
            if re.match(rf"^{re.escape(candidate)}(?:\b|\s|$)", line, flags=re.IGNORECASE):
                doc_type = candidate
                type_line_idx = idx
                break
        if doc_type:
            break

    # 3. Tên văn bản (tìm tiêu đề thực sự ở phần đầu văn bản; fallback tên file)
    title: str | None = None
    if type_line_idx is not None:
        first_line = lines[type_line_idx].strip()
        # Nếu dòng chỉ chứa đúng loại văn bản (vd "LUẬT", "NGHỊ ĐỊNH") thì ghép dòng tiếp theo nếu không phải "Số:" / "Căn cứ" / "Chương" / "Điều"
        if first_line.lower() == (doc_type or "").lower() and type_line_idx + 1 < len(lines):
            next_line = lines[type_line_idx + 1].strip()
            if not re.match(r"^(Số\s*:|Căn cứ|Chương|Phần|Mục|Điều\s+\d+|CỘNG HÒA|Độc lập)", next_line, flags=re.IGNORECASE):
                title = f"{first_line} {next_line}".strip()
            else:
                title = first_line
        else:
            title = first_line
            if (
                len(title) < 60
                and type_line_idx + 1 < len(lines)
                and not re.match(
                    r"^(Số\s*:|Căn cứ|Chương|Phần|Mục|Điều\s+\d+|CỘNG HÒA|Độc lập|Hà Nội|TP\.|Ngày)",
                    lines[type_line_idx + 1],
                    flags=re.IGNORECASE,
                )
                and not lines[type_line_idx + 1].endswith(".")
            ):
                # Ví dụ: "NGHỊ ĐỊNH" / "Quy định xử phạt vi phạm hành chính..."
                cand_next = lines[type_line_idx + 1].strip()
                if len(cand_next) <= 220:
                    title = f"{title} {cand_next}".strip()

    if not title:
        title = Path(filename).stem

    # 4. Cơ quan ban hành (chỉ trích xuất nếu khớp dòng cơ quan có căn cứ rõ ràng)
    issuing_authority: str | None = None
    auth_label = re.search(r"^Cơ quan ban hành\s*:\s*(.+)$", header_window, flags=re.IGNORECASE | re.MULTILINE)
    if auth_label:
        issuing_authority = auth_label.group(1).strip()
    else:
        for line in lines[:12]:
            stripped = line.strip(" _-–—")
            if re.search(r"CỘNG HÒA XÃ HỘI CHỦ NGHĨA|Độc lập\s*-\s*Tự do", stripped, flags=re.IGNORECASE):
                continue
            for pat in KNOWN_AUTHORITY_PATTERNS:
                m = re.match(pat, stripped)
                if m:
                    issuing_authority = m.group(1).strip()
                    break
            if issuing_authority:
                break

    # 5. Ngày ban hành (từ nhãn rõ ràng hoặc dòng địa danh ngày tháng ở đầu văn bản)
    issue_date = _extract_date_from_phrase(
        header_window,
        [
            r"Ngày ban hành\s*:\s*([^\n]+)",
            r"(?:Hà Nội|TP\.?\s*Hồ Chí Minh|Đà Nẵng|Hải Phòng|Cần Thơ)?[,\s]*(ngày\s+\d{1,2}\s+tháng\s+\d{1,2}\s+năm\s+\d{4})",
        ],
    )
    if not issue_date:
        # Không lấy nhầm ngày hiệu lực làm ngày ban hành: chỉ tìm ở 15 dòng đầu nếu không có cụm "có hiệu lực"
        for line in lines[:15]:
            if re.search(r"hiệu lực", line, flags=re.IGNORECASE):
                continue
            d = normalize_date_str(line)
            if d:
                issue_date = d
                break

    # 6. Ngày có hiệu lực (CHỈ khi văn bản nêu rõ điều khoản hiệu lực — TUYỆT ĐỐI KHÔNG suy đoán!)
    effective_date = _extract_date_from_phrase(
        cleaned,
        [
            r"Ngày\s*(?:có\s*)?hiệu lực\s*:\s*([^\n]+)",
            r"có hiệu lực(?:\s+thi hành)?\s+(?:kể\s+)?từ\s+(ngày\s+\d{1,2}\s+tháng\s+\d{1,2}\s+năm\s+\d{4})",
            r"có hiệu lực(?:\s+thi hành)?\s+(?:kể\s+)?từ\s+ngày\s+(\d{1,2}[/\-]\d{1,2}[/\-]\d{4})",
        ],
    )

    # 7. Ngày hết hiệu lực (CHỈ khi văn bản nêu rõ)
    expiry_date = _extract_date_from_phrase(
        cleaned,
        [
            r"Ngày hết hiệu lực\s*:\s*([^\n]+)",
            r"hết hiệu lực(?:\s+thi hành)?\s+(?:kể\s+)?từ\s+(ngày\s+\d{1,2}\s+tháng\s+\d{1,2}\s+năm\s+\d{4})",
            r"hết hiệu lực(?:\s+thi hành)?\s+(?:kể\s+)?từ\s+ngày\s+(\d{1,2}[/\-]\d{1,2}[/\-]\d{4})",
            r"có hiệu lực\s+đến\s+hết\s+(ngày\s+\d{1,2}\s+tháng\s+\d{1,2}\s+năm\s+\d{4})",
        ],
    )

    # 8. Trạng thái hiệu lực (CHỈ lấy nếu có khai báo rõ trong metadata/header — KHÔNG mặc định còn hiệu lực!)
    status: str | None = None
    status_match = re.search(r"^Trạng thái(?:\s+hiệu lực)?\s*:\s*(.+)$", header_short, flags=re.IGNORECASE | re.MULTILINE)
    if status_match:
        status = _clean_optional_str(status_match.group(1))

    # 9. Nguồn văn bản (CHỈ lấy nếu có dòng "Nguồn:" rõ ràng)
    source: str | None = None
    source_match = re.search(r"^Nguồn(?:\s+văn bản)?\s*:\s*(.+)$", header_window, flags=re.IGNORECASE | re.MULTILINE)
    if source_match:
        source = _clean_optional_str(source_match.group(1))

    return {
        "title": title,
        "document_number": doc_num,
        "document_type": doc_type,
        "issuing_authority": issuing_authority,
        "issue_date": issue_date,
        "issued_date": issue_date,  # tương thích ngược
        "effective_date": effective_date,
        "expiry_date": expiry_date,
        "status": status,
        "source": source,
    }


def evaluate_document_validity(
    effective_date: str | None,
    expiry_date: str | None,
    declared_status: str | None,
    as_of: date | None = None,
) -> tuple[str, str]:
    """
    Kiểm tra tình trạng hiệu lực dựa trên dữ liệu đáng tin cậy tại thời điểm truy vấn.
    Nguyên tắc: Không mặc định còn hiệu lực chỉ vì không có ngày hết hiệu lực.
    Trả về (status_label, explanation).
    """
    today = as_of or date.today()
    eff = normalize_date_str(effective_date)
    exp = normalize_date_str(expiry_date)
    status_clean = _clean_optional_str(declared_status)

    if status_clean:
        low = status_clean.lower()
        if "hết hiệu lực" in low or "bãi bỏ" in low:
            return "Hết hiệu lực", f"Trạng thái văn bản được ghi nhận là '{status_clean}'."

    if exp:
        exp_dt = date.fromisoformat(exp)
        if today > exp_dt:
            return "Hết hiệu lực", f"Văn bản đã hết hiệu lực từ ngày {exp} (kiểm tra ngày {today.isoformat()})."

    if eff:
        eff_dt = date.fromisoformat(eff)
        if today < eff_dt:
            return "Chưa có hiệu lực", f"Văn bản có hiệu lực từ ngày {eff} (chưa đến ngày hiệu lực tại {today.isoformat()})."

    if status_clean:
        return status_clean, f"Trạng thái hiệu lực theo metadata đáng tin cậy: {status_clean}."

    if eff and not exp:
        return (
            "Chưa xác định",
            f"Văn bản có ngày hiệu lực {eff}, chưa có thông tin xác nhận về văn bản sửa đổi/bãi bỏ hoặc ngày hết hiệu lực nên không mặc định còn hiệu lực.",
        )

    return "Chưa xác định", "Chưa có dữ liệu đáng tin cậy về ngày hiệu lực hoặc trạng thái hiệu lực của văn bản."


def parse_legal_document_file(file_path: Path, project_root: Path | None = None) -> ParsedLegalDocument:
    """
    Đọc, kiểm tra định dạng (.txt / .json), kiểm tra rỗng/lỗi và chuẩn hóa metadata văn bản pháp luật.
    """
    if not file_path.exists() or not file_path.is_file():
        raise LegalDocumentParseError(f"Không tìm thấy tệp văn bản: {file_path}")

    suffix = file_path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise LegalDocumentParseError(
            f"Định dạng tệp '{suffix or '(không có đuôi)'}' không được hỗ trợ. Chỉ chấp nhận .txt và .json."
        )

    raw_bytes = file_path.read_bytes()
    if not raw_bytes or not raw_bytes.strip():
        raise LegalDocumentParseError(f"Tệp '{file_path.name}' rỗng, không có nội dung để nạp.")

    checksum = compute_checksum(raw_bytes)
    try:
        raw_text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise LegalDocumentParseError(
            f"Tệp '{file_path.name}' không đúng mã hóa UTF-8: {exc}"
        ) from exc

    rel_path = file_path.as_posix()
    if project_root is not None:
        try:
            rel_path = file_path.resolve().relative_to(project_root.resolve()).as_posix()
        except ValueError:
            rel_path = file_path.resolve().as_posix()

    if suffix == ".json":
        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise LegalDocumentParseError(
                f"Tệp JSON '{file_path.name}' bị lỗi cú pháp: {exc}"
            ) from exc

        if not isinstance(payload, dict):
            raise LegalDocumentParseError(
                f"Tệp JSON '{file_path.name}' phải có cấu trúc đối tượng JSON (object)."
            )

        content_raw = payload.get("content")
        pre_chunks: list[dict[str, Any]] | None = None

        if isinstance(content_raw, str) and content_raw.strip():
            cleaned_content = clean_legal_text(content_raw)
        elif isinstance(payload.get("articles"), list) and payload["articles"]:
            parts: list[str] = []
            for item in payload["articles"]:
                if isinstance(item, dict):
                    txt = str(item.get("content", "")).strip()
                    art_name = str(item.get("article", "")).strip()
                    if art_name and txt and not txt.lower().startswith(art_name.lower()):
                        parts.append(f"{art_name}. {txt}")
                    elif txt:
                        parts.append(txt)
                elif isinstance(item, str) and item.strip():
                    parts.append(item.strip())
            cleaned_content = clean_legal_text("\n".join(parts))
        elif isinstance(payload.get("chunks"), list) and payload["chunks"]:
            valid_chunks = [c for c in payload["chunks"] if isinstance(c, dict) and str(c.get("content", "")).strip()]
            if not valid_chunks:
                raise LegalDocumentParseError(
                    f"Tệp JSON '{file_path.name}' không có nội dung hợp lệ trong 'chunks'."
                )
            pre_chunks = valid_chunks
            cleaned_content = clean_legal_text("\n".join(str(c["content"]) for c in valid_chunks))
        else:
            raise LegalDocumentParseError(
                f"Tệp JSON '{file_path.name}' rỗng hoặc thiếu trường 'content' hợp lệ."
            )

        if not cleaned_content:
            raise LegalDocumentParseError(f"Nội dung văn bản trong '{file_path.name}' bị rỗng sau khi chuẩn hóa.")

        # Bổ sung metadata từ nội dung chỉ cho những trường có căn cứ nếu JSON chưa khai báo
        inferred = extract_metadata_from_header(cleaned_content, file_path.name)

        title = _clean_optional_str(payload.get("title")) or inferred["title"] or file_path.stem
        doc_number = _clean_optional_str(payload.get("document_number")) or inferred["document_number"]
        doc_type = _clean_optional_str(payload.get("document_type")) or inferred["document_type"]
        issuing_authority = _clean_optional_str(payload.get("issuing_authority")) or inferred["issuing_authority"]
        issue_date = normalize_date_str(payload.get("issue_date") or payload.get("issued_date")) or inferred["issue_date"]
        effective_date = normalize_date_str(payload.get("effective_date")) or inferred["effective_date"]
        expiry_date = normalize_date_str(payload.get("expiry_date")) or inferred["expiry_date"]
        status = _clean_optional_str(payload.get("status")) or inferred["status"]
        source = _clean_optional_str(payload.get("source")) or inferred["source"]
        version = _clean_optional_str(payload.get("version"))

        return ParsedLegalDocument(
            title=title,
            document_number=doc_number,
            document_type=doc_type,
            issuing_authority=issuing_authority,
            issue_date=issue_date,
            effective_date=effective_date,
            expiry_date=expiry_date,
            status=status,
            source=source,
            file_path=rel_path,
            checksum=checksum,
            content=cleaned_content,
            version=version,
            pre_structured_chunks=pre_chunks,
        )

    # Định dạng .txt
    cleaned_content = clean_legal_text(raw_text)
    if not cleaned_content:
        raise LegalDocumentParseError(f"Tệp '{file_path.name}' chỉ chứa khoảng trắng, không có nội dung pháp luật.")

    meta = extract_metadata_from_header(cleaned_content, file_path.name)
    return ParsedLegalDocument(
        title=meta["title"] or file_path.stem,
        document_number=meta["document_number"],
        document_type=meta["document_type"],
        issuing_authority=meta["issuing_authority"],
        issue_date=meta["issue_date"],
        effective_date=meta["effective_date"],
        expiry_date=meta["expiry_date"],
        status=meta["status"],
        source=meta["source"],
        file_path=rel_path,
        checksum=checksum,
        content=cleaned_content,
        version=None,
        pre_structured_chunks=None,
    )


def _is_heading_subtitle(line: str) -> bool:
    """Nhận diện dòng tiêu đề nối tiếp ngay dưới dòng PHẦN/CHƯƠNG/MỤC (vd: 'NHỮNG QUY ĐỊNH CHUNG')."""
    if not line or len(line) > 180:
        return False
    if (
        RE_PART.match(line)
        or RE_CHAPTER.match(line)
        or RE_SECTION.match(line)
        or RE_ARTICLE.match(line)
        or RE_CLAUSE.match(line)
        or RE_POINT.match(line)
        or RE_PAGE_MARKER.match(line)
    ):
        return False
    if line.endswith(".") or line.endswith(";") or line.endswith(":"):
        return False
    # Dòng tiêu đề chương thường viết HOA hoặc ngắn gọn không có dấu chấm kết thúc câu
    letters = [ch for ch in line if ch.isalpha()]
    if not letters:
        return False
    upper_ratio = sum(1 for ch in letters if ch.isupper()) / len(letters)
    return upper_ratio >= 0.7 or len(line) <= 90


def _build_embedding_text(
    doc_title: str,
    doc_number: str | None,
    part: str | None,
    chapter: str | None,
    section: str | None,
    article_heading: str | None,
    clause_lead: str | None,
    content: str,
) -> str:
    """
    Tạo chuỗi ngữ cảnh phục vụ embedding mà KHÔNG sửa đổi nội dung gốc `content`.
    """
    header_parts = [p for p in [doc_title, doc_number, part, chapter, section] if p]
    if article_heading and article_heading not in content:
        header_parts.append(article_heading)
    if clause_lead and clause_lead not in content:
        header_parts.append(clause_lead)
    prefix = " | ".join(header_parts)
    return f"{prefix}\n{content}".strip() if prefix else content


def chunk_legal_document(
    text: str,
    filename: str,
    metadata: dict[str, Any] | None = None,
    document_id: str | None = None,
) -> list[LegalDocumentChunk]:
    """
    Chia chunk theo cấu trúc pháp luật Việt Nam: Phần -> Chương -> Mục -> Điều -> Khoản -> Điểm.

    Đảm bảo:
    - Không chia tùy tiện theo số ký tự.
    - Bảo toàn 100% nội dung gốc (mọi dòng văn bản đã chuẩn hóa đều nằm trong các chunk theo đúng thứ tự).
    - Không gộp các Điều không liên quan.
    - Nếu không nhận diện được cấu trúc pháp luật thì đánh dấu `needs_review=True`, không tạo cấu trúc giả.
    """
    cleaned = clean_legal_text(text)
    if not cleaned:
        return []

    meta = metadata or extract_metadata_from_header(cleaned, filename)
    doc_id = document_id or meta.get("document_id") or Path(filename).stem
    doc_title = meta.get("title") or Path(filename).stem
    doc_number = meta.get("document_number")
    doc_type = meta.get("document_type")
    issuing_authority = meta.get("issuing_authority")
    issue_date = meta.get("issue_date") or meta.get("issued_date")
    effective_date = meta.get("effective_date")
    expiry_date = meta.get("expiry_date")
    doc_status = meta.get("status")
    source = meta.get("source")

    lines = cleaned.split("\n")

    # Kiểm tra có nhận diện được cấu trúc pháp luật tối thiểu hay không
    has_structure = any(
        RE_ARTICLE.match(line) or RE_CHAPTER.match(line) or RE_PART.match(line) or RE_SECTION.match(line)
        for line in lines
    )

    if not has_structure:
        # Không nhận diện được cấu trúc pháp luật -> giữ nguyên nội dung, đánh dấu cần kiểm tra, KHÔNG tạo cấu trúc giả
        chunk_id = f"{doc_id}-chunk-0001"
        return [
            LegalDocumentChunk(
                chunk_id=chunk_id,
                document_id=doc_id,
                document_name=doc_title,
                document_number=doc_number,
                document_type=doc_type,
                issuing_authority=issuing_authority,
                issue_date=issue_date,
                effective_date=effective_date,
                expiry_date=expiry_date,
                document_status=doc_status,
                part=None,
                chapter=None,
                section=None,
                article=None,
                clause=None,
                point=None,
                content=cleaned,
                embedding_text=_build_embedding_text(doc_title, doc_number, None, None, None, None, None, cleaned),
                source=source,
                source_file=filename,
                page_number=None,
                chunk_index=1,
                needs_review=True,
                metadata={
                    "review_reason": "Không nhận diện được cấu trúc Phần/Chương/Mục/Điều/Khoản/Điểm; cần kiểm tra thủ công."
                },
            )
        ]

    # Phân tích theo cấu trúc phân cấp bảo toàn 100% dòng
    chunks: list[LegalDocumentChunk] = []
    chunk_seq = 0

    current_part: str | None = None
    current_chapter: str | None = None
    current_section: str | None = None
    current_page: int | None = None

    # Các dòng tiêu đề chờ gắn vào Điều tiếp theo (để không tạo chunk mồ côi nhưng vẫn không mất dòng nào)
    pending_heading_lines: list[str] = []
    preamble_lines: list[str] = []

    def emit_chunk(
        content_lines: list[str],
        *,
        part: str | None,
        chapter: str | None,
        section: str | None,
        article: str | None,
        article_heading: str | None,
        clause: str | None,
        clause_lead: str | None,
        point: str | None,
        page_number: int | None,
        needs_review: bool = False,
    ) -> None:
        nonlocal chunk_seq
        non_empty = [ln for ln in content_lines if ln]
        if not non_empty:
            return
        chunk_seq += 1
        body = "\n".join(non_empty)
        chunk_id = f"{doc_id}-chunk-{chunk_seq:04d}"
        chunks.append(
            LegalDocumentChunk(
                chunk_id=chunk_id,
                document_id=doc_id,
                document_name=doc_title,
                document_number=doc_number,
                document_type=doc_type,
                issuing_authority=issuing_authority,
                issue_date=issue_date,
                effective_date=effective_date,
                expiry_date=expiry_date,
                document_status=doc_status,
                part=part,
                chapter=chapter,
                section=section,
                article=article,
                clause=clause,
                point=point,
                content=body,
                embedding_text=_build_embedding_text(
                    doc_title, doc_number, part, chapter, section, article_heading, clause_lead, body
                ),
                source=source,
                source_file=filename,
                page_number=page_number,
                chunk_index=chunk_seq,
                needs_review=needs_review,
                metadata={
                    "part": part,
                    "chapter": chapter,
                    "section": section,
                    "article": article,
                    "clause": clause,
                    "point": point,
                    "article_heading": article_heading,
                },
            )
        )

    def flush_article(
        art_label: str,
        art_heading: str,
        art_lines: list[str],
        art_part: str | None,
        art_chapter: str | None,
        art_section: str | None,
        art_page: int | None,
    ) -> None:
        """
        Tách một Điều thành các chunk theo Khoản và Điểm (nếu có) nhưng KHÔNG bao giờ mất dòng nào
        và KHÔNG gộp với Điều khác.
        """
        # Kiểm tra sự hiện diện của Khoản (1., 2., ...) và Điểm (a), b), ...)
        clause_indices = [idx for idx, ln in enumerate(art_lines) if RE_CLAUSE.match(ln)]
        point_indices = [idx for idx, ln in enumerate(art_lines) if RE_POINT.match(ln)]

        if not clause_indices and not point_indices:
            emit_chunk(
                art_lines,
                part=art_part,
                chapter=art_chapter,
                section=art_section,
                article=art_label,
                article_heading=art_heading,
                clause=None,
                clause_lead=None,
                point=None,
                page_number=art_page,
            )
            return

        if not clause_indices and point_indices:
            # Điều không có Khoản số nhưng có trực tiếp các Điểm a), b), ...
            first_pt = point_indices[0]
            lead_lines = art_lines[:first_pt]
            lead_text = lead_lines[-1] if lead_lines else art_heading
            if lead_lines:
                emit_chunk(
                    lead_lines,
                    part=art_part,
                    chapter=art_chapter,
                    section=art_section,
                    article=art_label,
                    article_heading=art_heading,
                    clause=None,
                    clause_lead=None,
                    point=None,
                    page_number=art_page,
                )
            for p_pos, start_idx in enumerate(point_indices):
                end_idx = point_indices[p_pos + 1] if p_pos + 1 < len(point_indices) else len(art_lines)
                pt_block = art_lines[start_idx:end_idx]
                pt_match = RE_POINT.match(pt_block[0])
                pt_label = f"Điểm {pt_match.group(1)}" if pt_match else None
                emit_chunk(
                    pt_block,
                    part=art_part,
                    chapter=art_chapter,
                    section=art_section,
                    article=art_label,
                    article_heading=art_heading,
                    clause=None,
                    clause_lead=lead_text,
                    point=pt_label,
                    page_number=art_page,
                )
            return

        # Điều có các Khoản (1., 2., ...)
        first_clause_idx = clause_indices[0]
        header_before_first_clause = art_lines[:first_clause_idx]

        for c_pos, start_idx in enumerate(clause_indices):
            end_idx = clause_indices[c_pos + 1] if c_pos + 1 < len(clause_indices) else len(art_lines)
            clause_block = art_lines[start_idx:end_idx]
            c_match = RE_CLAUSE.match(clause_block[0])
            clause_label = f"Khoản {c_match.group(1)}" if c_match else None
            clause_lead_line = clause_block[0]

            # Gắn dòng tiêu đề Điều (và tiêu đề Chương chờ nếu có) vào đầu Khoản 1 để giữ trọn vẹn không mất dòng nào
            prefix_lines = header_before_first_clause if c_pos == 0 else []

            sub_point_indices = [idx for idx, ln in enumerate(clause_block) if RE_POINT.match(ln)]
            if sub_point_indices:
                first_sub_pt = sub_point_indices[0]
                clause_intro_lines = prefix_lines + clause_block[:first_sub_pt]
                if clause_intro_lines:
                    emit_chunk(
                        clause_intro_lines,
                        part=art_part,
                        chapter=art_chapter,
                        section=art_section,
                        article=art_label,
                        article_heading=art_heading,
                        clause=clause_label,
                        clause_lead=None,
                        point=None,
                        page_number=art_page,
                    )
                for p_pos, pt_start in enumerate(sub_point_indices):
                    pt_end = sub_point_indices[p_pos + 1] if p_pos + 1 < len(sub_point_indices) else len(clause_block)
                    pt_block = clause_block[pt_start:pt_end]
                    pt_match = RE_POINT.match(pt_block[0])
                    pt_label = f"Điểm {pt_match.group(1)}" if pt_match else None
                    emit_chunk(
                        pt_block,
                        part=art_part,
                        chapter=art_chapter,
                        section=art_section,
                        article=art_label,
                        article_heading=art_heading,
                        clause=clause_label,
                        clause_lead=clause_lead_line,
                        point=pt_label,
                        page_number=art_page,
                    )
            else:
                emit_chunk(
                    prefix_lines + clause_block,
                    part=art_part,
                    chapter=art_chapter,
                    section=art_section,
                    article=art_label,
                    article_heading=art_heading,
                    clause=clause_label,
                    clause_lead=None,
                    point=None,
                    page_number=art_page,
                )

    # Duyệt tuần tự tất cả các dòng
    in_article = False
    cur_article_label: str | None = None
    cur_article_heading: str = ""
    cur_article_lines: list[str] = []
    cur_article_part: str | None = None
    cur_article_chapter: str | None = None
    cur_article_section: str | None = None
    cur_article_page: int | None = None

    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]

        # Marker số trang (nếu có) — vẫn giữ nguyên dòng trong nội dung để không làm mất text
        page_match = RE_PAGE_MARKER.match(line)
        if page_match:
            page_str = page_match.group(1) or page_match.group(2)
            if page_str:
                current_page = int(page_str)
            if in_article:
                cur_article_lines.append(line)
            elif current_part or current_chapter or current_section:
                pending_heading_lines.append(line)
            else:
                preamble_lines.append(line)
            i += 1
            continue

        part_match = RE_PART.match(line)
        chap_match = RE_CHAPTER.match(line)
        sec_match = RE_SECTION.match(line)
        art_match = RE_ARTICLE.match(line)

        if part_match or chap_match or sec_match:
            if in_article and cur_article_label:
                flush_article(
                    cur_article_label,
                    cur_article_heading,
                    cur_article_lines,
                    cur_article_part,
                    cur_article_chapter,
                    cur_article_section,
                    cur_article_page,
                )
                in_article = False
                cur_article_label = None
                cur_article_lines = []
            elif preamble_lines:
                emit_chunk(
                    preamble_lines,
                    part=None,
                    chapter=None,
                    section=None,
                    article=None,
                    article_heading=None,
                    clause=None,
                    clause_lead=None,
                    point=None,
                    page_number=current_page,
                )
                preamble_lines = []

            heading_text = line
            pending_heading_lines.append(line)
            if i + 1 < n and _is_heading_subtitle(lines[i + 1]):
                subtitle = lines[i + 1]
                heading_text = f"{line}: {subtitle}"
                pending_heading_lines.append(subtitle)
                i += 1

            if part_match:
                current_part = heading_text
                current_chapter = None
                current_section = None
            elif chap_match:
                current_chapter = heading_text
                current_section = None
            elif sec_match:
                current_section = heading_text

            i += 1
            continue

        if art_match:
            if in_article and cur_article_label:
                flush_article(
                    cur_article_label,
                    cur_article_heading,
                    cur_article_lines,
                    cur_article_part,
                    cur_article_chapter,
                    cur_article_section,
                    cur_article_page,
                )
            elif preamble_lines:
                emit_chunk(
                    preamble_lines,
                    part=None,
                    chapter=None,
                    section=None,
                    article=None,
                    article_heading=None,
                    clause=None,
                    clause_lead=None,
                    point=None,
                    page_number=current_page,
                )
                preamble_lines = []

            raw_art = art_match.group(1)
            # Chuẩn hóa chữ "Điều" viết hoa chữ cái đầu
            cur_article_label = re.sub(r"^điều", "Điều", raw_art, flags=re.IGNORECASE)
            cur_article_heading = line
            cur_article_lines = pending_heading_lines + [line]
            pending_heading_lines = []
            cur_article_part = current_part
            cur_article_chapter = current_chapter
            cur_article_section = current_section
            cur_article_page = current_page
            in_article = True
            i += 1
            continue

        # Dòng nội dung bình thường
        if in_article:
            cur_article_lines.append(line)
        elif current_part or current_chapter or current_section:
            pending_heading_lines.append(line)
        else:
            preamble_lines.append(line)
        i += 1

    # Flush phần cuối cùng
    if in_article and cur_article_label:
        flush_article(
            cur_article_label,
            cur_article_heading,
            cur_article_lines,
            cur_article_part,
            cur_article_chapter,
            cur_article_section,
            cur_article_page,
        )
    if pending_heading_lines:
        # Trường hợp văn bản có Chương/Mục nhưng không có Điều nào bên dưới
        emit_chunk(
            pending_heading_lines,
            part=current_part,
            chapter=current_chapter,
            section=current_section,
            article=None,
            article_heading=None,
            clause=None,
            clause_lead=None,
            point=None,
            page_number=current_page,
            needs_review=True,
        )
    if preamble_lines:
        emit_chunk(
            preamble_lines,
            part=None,
            chapter=None,
            section=None,
            article=None,
            article_heading=None,
            clause=None,
            clause_lead=None,
            point=None,
            page_number=current_page,
            needs_review=True,
        )

    return chunks


def validate_chunks(original_cleaned_text: str, chunks: list[LegalDocumentChunk]) -> tuple[bool, list[str]]:
    """
    Cơ chế kiểm tra chunk trước khi lưu:
    1. Không rỗng.
    2. Không trùng chunk_id.
    3. Không mất nội dung khi chia chunk (so sánh khớp 100% nội dung sau chuẩn hóa).
    4. Không gộp nhiều Điều khác nhau trong cùng một chunk.
    """
    errors: list[str] = []
    if not chunks:
        errors.append("Danh sách chunk rỗng.")
        return False, errors

    seen_ids: set[str] = set()
    for c in chunks:
        if not c.chunk_id or not c.chunk_id.strip():
            errors.append("Tồn tại chunk thiếu chunk_id.")
        elif c.chunk_id in seen_ids:
            errors.append(f"Trùng lặp chunk_id: {c.chunk_id}.")
        seen_ids.add(c.chunk_id)

        if not c.content or not c.content.strip():
            errors.append(f"Chunk {c.chunk_id} có nội dung rỗng.")

        # Kiểm tra không gộp nhiều Điều trong 1 chunk
        article_headers = re.findall(r"^Điều\s+\d+[a-zA-Z]?(?:[\.\:\-\s]|$)", c.content, flags=re.MULTILINE | re.IGNORECASE)
        if len(article_headers) > 1:
            errors.append(
                f"Chunk {c.chunk_id} gộp nhiều Điều khác nhau ({len(article_headers)} tiêu đề Điều)."
            )

    reconstructed = "\n".join(c.content for c in chunks)
    expected = clean_legal_text(original_cleaned_text)
    if reconstructed != expected:
        orig_lines = expected.split("\n")
        rec_lines = reconstructed.split("\n")
        errors.append(
            f"Phát hiện sai lệch nội dung sau khi chia chunk (gốc: {len(orig_lines)} dòng / {len(expected)} ký tự; "
            f"chunks: {len(rec_lines)} dòng / {len(reconstructed)} ký tự)."
        )

    return len(errors) == 0, errors
