"""
Bộ lọc và chuyển đổi tự động thư mục văn bản pháp luật gốc (.doc, .docx, .pdf, .txt, .json)
sang định dạng chuẩn UTF-8 (.txt / .json) để đưa vào pipeline RAG (rag/pipeline.py).

Hỗ trợ đầy đủ các tình huống thực tế của văn bản pháp luật Việt Nam:
- .txt / .json: giữ nguyên nội dung, tự động chuẩn hóa mã hóa UTF-8.
- .docx: đọc toàn bộ đoạn văn + bảng biểu từ OOXML (zipfile + ElementTree), giữ nguyên cấu trúc Điều/Khoản/Điểm.
- .doc: tự nhận diện cả 4 dạng phổ biến trên Cổng thông tin / Thư viện pháp luật:
  (1) HTML lưu đuôi .doc, (2) RTF lưu đuôi .doc, (3) OOXML/ZIP lưu đuôi .doc,
  (4) Binary OLE2 Word 97-2003 (chuyển đổi sạch qua Microsoft Word COM trên Windows hoặc LibreOffice headless).
- .pdf: trích xuất từng trang bằng pypdf kèm đánh dấu [Trang N] tương thích trực tiếp với RE_PAGE_MARKER của RAG.
- Tự động lọc bỏ tệp tạm (~$*, .DS_Store, Thumbs.db) và các định dạng không phải văn bản pháp luật.
"""

from __future__ import annotations

import io
import logging
import re
import shutil
import subprocess
import tempfile
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path

from bs4 import BeautifulSoup
from charset_normalizer import from_bytes

logger = logging.getLogger(__name__)

CONVERTIBLE_EXTENSIONS = {".txt", ".json", ".docx", ".doc", ".pdf"}
IGNORED_FILENAMES = {"thumbs.db", "desktop.ini", ".ds_store"}
WORD_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


class DocumentConversionError(ValueError):
    """Lỗi khi trích xuất văn bản từ tệp gốc (.doc, .docx, .pdf, .txt, .json)."""


@dataclass
class ConvertedDocumentResult:
    original_filename: str
    original_ext: str
    target_filename: str
    target_bytes: bytes
    converter_used: str
    converted: bool


def should_ignore_folder_file(filename: str) -> tuple[bool, str]:
    """Kiểm tra tệp trong thư mục tải lên có nên tự động lọc bỏ hay không."""
    base = Path(filename.replace("\\", "/")).name
    low = base.lower()
    if not base or base.startswith(".") or base.startswith("~$") or low in IGNORED_FILENAMES:
        return True, "Tệp hệ thống / tệp tạm"
    ext = Path(base).suffix.lower()
    if ext not in CONVERTIBLE_EXTENSIONS:
        return True, f"Tự động bỏ qua định dạng '{ext or '(không có đuôi)'}' (chỉ lọc .doc, .docx, .pdf, .txt, .json)"
    return False, ""


def _safe_target_stem(raw_name: str) -> str:
    """Tạo tên tệp an toàn giữ đường dẫn con nếu có để tránh trùng tên khi upload nhiều thư mục con."""
    norm = raw_name.replace("\\", "/").strip("/")
    parts = [p for p in norm.split("/") if p and p not in {".", ".."}]
    if not parts:
        return "van_ban"
    # Bỏ thư mục gốc ngoài cùng nếu có nhiều cấp để tên gọn hơn nhưng vẫn phân biệt thư mục con
    if len(parts) >= 2:
        rel_parts = parts[1:]
    else:
        rel_parts = parts
    joined = "__".join(rel_parts)
    stem = Path(joined).stem
    stem = unicodedata.normalize("NFC", stem)
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", stem).strip(" ._")
    return stem[:140] or "van_ban"


def _decode_text_bytes(raw: bytes) -> str:
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    match = from_bytes(raw).best()
    if match is not None:
        return str(match)
    return raw.decode("utf-8", errors="replace")


def _extract_docx_bytes(raw: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(raw), "r") as zf:
            if "word/document.xml" not in zf.namelist():
                raise DocumentConversionError("Tệp .docx không hợp lệ (thiếu word/document.xml).")
            xml_bytes = zf.read("word/document.xml")
    except zipfile.BadZipFile as exc:
        raise DocumentConversionError("Tệp .docx bị hỏng hoặc không đúng chuẩn ZIP/OOXML.") from exc

    root = ET.fromstring(xml_bytes)
    body = root.find("w:body", WORD_NS)
    if body is None:
        return ""

    w_t = f"{{{WORD_NS['w']}}}t"
    w_tab = f"{{{WORD_NS['w']}}}tab"
    w_br = f"{{{WORD_NS['w']}}}br"
    w_p = f"{{{WORD_NS['w']}}}p"

    lines: list[str] = []
    for p in body.iter(w_p):
        parts: list[str] = []
        for elem in p.iter():
            if elem.tag == w_t and elem.text:
                parts.append(elem.text)
            elif elem.tag == w_tab:
                parts.append(" ")
            elif elem.tag == w_br:
                parts.append("\n")
        text = "".join(parts)
        for sub in text.split("\n"):
            cleaned = re.sub(r"[ \t]+", " ", sub).strip()
            if cleaned:
                lines.append(cleaned)
    return "\n".join(lines)


def _extract_rtf_text(raw: bytes) -> str:
    """Bộ giải mã RTF thuần Python hỗ trợ ký tự Unicode tiếng Việt (\\uN)."""
    text = raw.decode("latin-1", errors="ignore")
    # Giải mã \uN? (Unicode codepoint trong RTF)
    def _u_repl(m: re.Match) -> str:
        code = int(m.group(1))
        if code < 0:
            code += 65536
        try:
            return chr(code)
        except ValueError:
            return ""

    text = re.sub(r"\\u(-?\d+)\??", _u_repl, text)
    text = re.sub(r"\\par\b|\\line\b", "\n", text)
    text = re.sub(r"\\tab\b", " ", text)
    # Bỏ các nhóm điều khiển fonttbl/colortbl/stylesheet
    text = re.sub(r"\{\\(?:fonttbl|colortbl|stylesheet|info|pict|header|footer)[^{}]*\}", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\\'[0-9a-fA-F]{2}", "", text)
    text = re.sub(r"\\[a-zA-Z]+-?\d* ?", "", text)
    text = text.replace("{", "").replace("}", "")
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def _extract_html_text(raw: bytes) -> str:
    decoded = _decode_text_bytes(raw)
    soup = BeautifulSoup(decoded, "html.parser")
    for tag in soup(["script", "style", "head", "meta", "link"]):
        tag.decompose()
    raw_text = soup.get_text(separator="\n")
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in raw_text.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def _extract_legacy_ole_doc_via_word_or_soffice(raw: bytes, filename: str) -> str:
    """
    Chuyển đổi tệp .doc nhị phân (Word 97-2003 OLE2) sang UTF-8 text:
    - Ưu tiên Microsoft Word COM (Windows) hoặc LibreOffice headless (Linux/Docker).
    """
    with tempfile.TemporaryDirectory(prefix="legal_doc_conv_") as tmpdir:
        tmp_path = Path(tmpdir)
        src_doc = tmp_path / "input.doc"
        out_txt = tmp_path / "output.txt"
        src_doc.write_bytes(raw)

        # 1. Thử LibreOffice nếu có sẵn
        soffice = shutil.which("soffice") or shutil.which("libreoffice")
        if soffice:
            try:
                proc = subprocess.run(
                    [soffice, "--headless", "--convert-to", "txt:Text (encoded):UTF8", "--outdir", str(tmp_path), str(src_doc)],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                generated = tmp_path / "input.txt"
                if proc.returncode == 0 and generated.exists():
                    content = _decode_text_bytes(generated.read_bytes()).strip()
                    if content:
                        return content
            except Exception as exc:
                logger.warning("LibreOffice convert failed for %s: %s", filename, exc)

        # 2. Thử Microsoft Word COM qua PowerShell trên Windows
        ps_script = (
            "$ErrorActionPreference = 'Stop'; "
            "$word = $null; $doc = $null; "
            "try { "
            "  $word = New-Object -ComObject Word.Application; "
            "  $word.Visible = $false; "
            "  $word.DisplayAlerts = 0; "
            f"  $doc = $word.Documents.Open('{str(src_doc)}', $false, $true); "
            f"  $doc.SaveAs([ref]'{str(out_txt)}', [ref]7, [ref]$false, [ref]'', [ref]$false, [ref]'', [ref]$false, [ref]$false, [ref]$false, [ref]$false, [ref]$false, [ref]65001); "
            "} finally { "
            "  if ($doc -ne $null) { $doc.Close($false) | Out-Null }; "
            "  if ($word -ne $null) { $word.Quit() | Out-Null }; "
            "}"
        )
        try:
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=35,
            )
            if proc.returncode == 0 and out_txt.exists():
                content = _decode_text_bytes(out_txt.read_bytes()).strip()
                if content:
                    return content
        except Exception as exc:
            logger.warning("Word COM convert failed for %s: %s", filename, exc)

    raise DocumentConversionError(
        f"Không thể đọc tệp .doc nhị phân cũ '{filename}' (cần Microsoft Word hoặc LibreOffice khả dụng, "
        f"hoặc chuyển tệp sang .docx/.txt trước khi tải lên)."
    )


def _extract_doc_bytes(raw: bytes, filename: str) -> tuple[str, str]:
    head = raw[:512].lstrip()
    head_low = head.lower()

    # Dạng 1: OOXML (.docx) nhưng đặt đuôi .doc
    if head.startswith(b"PK\x03\x04"):
        return _extract_docx_bytes(raw), "docx_xml"

    # Dạng 2: RTF lưu đuôi .doc
    if head.startswith(b"{\\rtf"):
        return _extract_rtf_text(raw), "rtf_parser"

    # Dạng 3: HTML / MHTML tải từ trang pháp luật lưu đuôi .doc
    if (
        b"<html" in head_low
        or b"<!doctype html" in head_low
        or b"<meta" in head_low
        or b"<div" in head_low
        or b"<p" in head_low
    ):
        return _extract_html_text(raw), "html_doc_parser"

    # Dạng 4: OLE2 nhị phân (.doc Word 97-2003)
    if raw[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return _extract_legacy_ole_doc_via_word_or_soffice(raw, filename), "word_ole_converter"

    # Dạng 5: Văn bản thuần đặt đuôi .doc
    decoded = _decode_text_bytes(raw)
    if decoded and sum(1 for c in decoded[:200] if c.isprintable() or c in "\r\n\t") / max(len(decoded[:200]), 1) > 0.85:
        return decoded, "plain_text_doc"

    raise DocumentConversionError(f"Không nhận diện được cấu trúc tệp .doc '{filename}'.")


def _extract_pdf_bytes(raw: bytes, filename: str) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise DocumentConversionError(
            "Thiếu thư viện 'pypdf' để đọc tệp PDF. Vui lòng cài đặt: pip install pypdf"
        ) from exc

    try:
        reader = PdfReader(io.BytesIO(raw))
    except Exception as exc:
        raise DocumentConversionError(f"Không thể mở tệp PDF '{filename}': {exc}") from exc

    if getattr(reader, "is_encrypted", False):
        try:
            reader.decrypt("")
        except Exception as exc:
            raise DocumentConversionError(f"Tệp PDF '{filename}' bị khóa mật khẩu, không thể trích xuất.") from exc

    page_blocks: list[str] = []
    for idx, page in enumerate(reader.pages, start=1):
        txt = (page.extract_text() or "").strip()
        if txt:
            cleaned_lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in txt.splitlines() if ln.strip()]
            if cleaned_lines:
                page_blocks.append(f"[Trang {idx}]\n" + "\n".join(cleaned_lines))

    if not page_blocks:
        raise DocumentConversionError(
            f"Tệp PDF '{filename}' không chứa lớp văn bản trích xuất được (có thể là PDF scan ảnh, cần OCR trước khi nạp)."
        )
    return "\n\n".join(page_blocks)


def convert_uploaded_document(raw_filename: str, content: bytes) -> ConvertedDocumentResult:
    """
    Chuyển đổi một tệp đầu vào (.doc, .docx, .pdf, .txt, .json) về đúng định dạng chuẩn (.txt hoặc .json)
    UTF-8 sạch để nạp vào `data/legal_documents/` và đồng bộ Qdrant.
    """
    if not content or not content.strip():
        raise DocumentConversionError(f"Tệp '{raw_filename}' rỗng, không có nội dung để nạp.")

    base_name = Path(raw_filename.replace("\\", "/")).name
    ext = Path(base_name).suffix.lower()
    if ext not in CONVERTIBLE_EXTENSIONS:
        raise DocumentConversionError(
            f"Định dạng '{ext or '(không có đuôi)'}' không được hỗ trợ. Chấp nhận: .doc, .docx, .pdf, .txt, .json."
        )

    safe_stem = _safe_target_stem(raw_filename)

    if ext == ".json":
        decoded = _decode_text_bytes(content)
        return ConvertedDocumentResult(
            original_filename=raw_filename,
            original_ext=ext,
            target_filename=f"{safe_stem}.json",
            target_bytes=decoded.encode("utf-8"),
            converter_used="json_passthrough",
            converted=False,
        )

    if ext == ".txt":
        decoded = _decode_text_bytes(content)
        if not decoded.strip():
            raise DocumentConversionError(f"Tệp '{base_name}' không có nội dung văn bản.")
        return ConvertedDocumentResult(
            original_filename=raw_filename,
            original_ext=ext,
            target_filename=f"{safe_stem}.txt",
            target_bytes=decoded.encode("utf-8"),
            converter_used="txt_utf8_normalizer",
            converted=False,
        )

    if ext == ".docx":
        extracted = _extract_docx_bytes(content)
        if not extracted.strip():
            raise DocumentConversionError(f"Tệp Word '{base_name}' không có nội dung văn bản.")
        return ConvertedDocumentResult(
            original_filename=raw_filename,
            original_ext=ext,
            target_filename=f"{safe_stem}.txt",
            target_bytes=extracted.encode("utf-8"),
            converter_used="docx_to_txt",
            converted=True,
        )

    if ext == ".doc":
        extracted, conv_name = _extract_doc_bytes(content, base_name)
        if not extracted.strip():
            raise DocumentConversionError(f"Tệp Word (.doc) '{base_name}' không có nội dung văn bản.")
        return ConvertedDocumentResult(
            original_filename=raw_filename,
            original_ext=ext,
            target_filename=f"{safe_stem}.txt",
            target_bytes=extracted.encode("utf-8"),
            converter_used=conv_name,
            converted=True,
        )

    if ext == ".pdf":
        extracted = _extract_pdf_bytes(content, base_name)
        return ConvertedDocumentResult(
            original_filename=raw_filename,
            original_ext=ext,
            target_filename=f"{safe_stem}.txt",
            target_bytes=extracted.encode("utf-8"),
            converter_used="pdf_to_txt",
            converted=True,
        )

    raise DocumentConversionError(f"Định dạng '{ext}' chưa được hỗ trợ.")
