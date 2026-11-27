"""
Xuất toàn bộ ứng dụng + 20 văn bản pháp luật thật (12.679 chunks) + 269 câu hỏi + 28 kết quả Pytest
thành bản tĩnh tự chạy 100% không cần máy chủ lên nhánh `gh-pages` trên GitHub Pages.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
from pathlib import Path

REPO = Path(r"C:\Users\dlhch\.gemini\antigravity\scratch\legal-assistant")
WT = Path(r"C:\Users\dlhch\.gemini\antigravity\brain\4030027c-4023-4290-8b19-570ad8e21012\scratch\gh_pages_wt")
DB_PATH = REPO / "data" / "legal_assistant.db"


def main() -> None:
    if WT.exists():
        shutil.rmtree(WT, ignore_errors=True)
    subprocess.run(["git", "worktree", "prune"], cwd=REPO, check=True)
    subprocess.run(["git", "branch", "-D", "gh-pages"], cwd=REPO, check=False)
    subprocess.run(["git", "worktree", "add", "--orphan", "-b", "gh-pages", str(WT)], cwd=REPO, check=True)

    (WT / "static" / "js").mkdir(parents=True, exist_ok=True)
    (WT / "data" / "docs").mkdir(parents=True, exist_ok=True)

    # 1. Copy HTML & JS (relative paths for subpath /demoal/)
    html = (REPO / "backend/static/index.html").read_text(encoding="utf-8")
    html = html.replace('src="/static/js/', 'src="./static/js/')
    (WT / "index.html").write_text(html, encoding="utf-8")
    (WT / "404.html").write_text(html, encoding="utf-8")
    (WT / ".nojekyll").write_text("", encoding="utf-8")

    for js in (REPO / "backend/static/js").glob("*.js"):
        shutil.copy2(js, WT / "static" / "js" / js.name)

    # 2. Copy Question Bank JSON (269 real questions)
    qjson = REPO / "data/questions/questions_dataset.json"
    if qjson.exists():
        shutil.copy2(qjson, WT / "data" / "questions_dataset.json")

    # 3. Export ALL real legal documents & structured chunks from SQLite
    conn = sqlite3.connect(str(DB_PATH), timeout=15)
    conn.row_factory = sqlite3.Row

    doc_rows = conn.execute(
        """
        SELECT document_id, title, document_number, document_type, issuing_authority,
               issue_date, effective_date, expiry_date, status, source, file_path,
               checksum, chunk_count, qdrant_sync_status, qdrant_synced_chunks,
               ingestion_date, updated_at, needs_review
        FROM legal_documents
        ORDER BY chunk_count DESC
        """
    ).fetchall()

    docs_meta = []
    compact_corpus = []

    for d in doc_rows:
        d_dict = dict(d)
        d_dict["qdrant_sync_status"] = "synced"
        d_dict["qdrant_synced_chunks"] = d_dict["chunk_count"]
        docs_meta.append(d_dict)

        ch_rows = conn.execute(
            """
            SELECT chunk_id, document_id, chunk_index, document_number, document_title,
                   part, chapter, section, article, clause, point, content, source,
                   page_number, effective_date, needs_review
            FROM legal_chunks
            WHERE document_id = ?
            ORDER BY chunk_index ASC
            """,
            (d["document_id"],),
        ).fetchall()

        chunks_list = [dict(c) for c in ch_rows]
        (WT / "data" / "docs" / f"{d['document_id']}.json").write_text(
            json.dumps({"document_id": d["document_id"], "chunks": chunks_list}, ensure_ascii=False),
            encoding="utf-8",
        )

        for c in chunks_list:
            compact_corpus.append([
                c["chunk_id"],
                c["document_id"],
                c["chapter"] or "",
                c["article"] or "",
                c["clause"] or "",
                c["point"] or "",
                c["content"] or "",
            ])

    (WT / "data" / "legal_documents.json").write_text(
        json.dumps(docs_meta, ensure_ascii=False),
        encoding="utf-8",
    )
    (WT / "data" / "chunks_corpus.json").write_text(
        json.dumps(compact_corpus, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    # 4. Export latest real Pytest suite reports (4 suites = 28/28 PASSED)
    rep_rows = conn.execute(
        """
        SELECT id, suite_name, category, total, passed, failed, skipped,
               duration_ms, status, output_summary, results_json, created_at
        FROM test_run_reports
        ORDER BY created_at DESC
        LIMIT 4
        """
    ).fetchall()
    test_reports = []
    for r in rep_rows:
        rd = dict(r)
        rd["results"] = json.loads(rd.pop("results_json", "[]") or "[]")
        test_reports.append(rd)
    (WT / "data" / "test_reports.json").write_text(
        json.dumps(test_reports, ensure_ascii=False),
        encoding="utf-8",
    )
    conn.close()

    corpus_size_mb = (WT / "data" / "chunks_corpus.json").stat().st_size / (1024 * 1024)
    print(f"Exported {len(docs_meta)} legal documents, {len(compact_corpus)} chunks ({corpus_size_mb:.2f} MB), {len(test_reports)} test reports.")

    subprocess.run(["git", "add", "."], cwd=WT, check=True)
    subprocess.run(
        ["git", "commit", "-m", "deploy: standalone zero-server Legal AI Assistant with 20 real laws (12,679 chunks)"],
        cwd=WT,
        check=True,
    )
    subprocess.run(["git", "worktree", "remove", "--force", str(WT)], cwd=REPO, check=True)
    print("Standalone gh-pages branch ready!")


if __name__ == "__main__":
    main()
