"""
Chạy toàn bộ bộ kiểm thử Pytest thật và lưu kết quả vào bảng `test_run_reports`
để Admin Portal -> Testing Dashboard hiển thị dữ liệu thực tế (không giả lập).
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.core.database import SessionLocal, init_db
from backend.app.services.admin_service import save_test_report

SUITES = [
    ("API & Core Chat Tests", "API / Unit Test", "backend/tests/test_api.py"),
    ("Auth & RBAC Security Tests", "Integration / Security Test", "backend/tests/test_auth_and_rbac.py"),
    ("RAG, Qdrant & Ingestion Tests", "RAG / Integration Test", "backend/tests/test_legal_ingestion.py"),
    ("Dual Portal, Agent & Citation Tests", "Agent / Citation / E2E Test", "backend/tests/test_portals_and_workflow.py"),
]


def main() -> int:
    init_db()
    overall_exit = 0

    for suite_name, category, rel_path in SUITES:
        t0 = time.perf_counter()
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", str(PROJECT_ROOT / rel_path), "-v", "--tb=short"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        out = (proc.stdout or "") + "\n" + (proc.stderr or "")

        passed = 0
        failed = 0
        skipped = 0
        case_results = []
        for line in out.splitlines():
            if "::test_" in line:
                if " PASSED" in line:
                    passed += 1
                    case_results.append({"test": line.split()[0], "status": "PASSED"})
                elif " FAILED" in line:
                    failed += 1
                    case_results.append({"test": line.split()[0], "status": "FAILED"})
                elif " SKIPPED" in line:
                    skipped += 1
                    case_results.append({"test": line.split()[0], "status": "SKIPPED"})

        total = passed + failed + skipped
        summary = f"Exit {proc.returncode}: {passed} passed, {failed} failed, {skipped} skipped ({elapsed_ms} ms)"
        print(f"[{suite_name}] {summary}")
        if proc.returncode != 0:
            overall_exit = proc.returncode
            print(out)

        with SessionLocal() as db:
            save_test_report(
                db,
                suite_name=suite_name,
                category=category,
                total=total,
                passed=passed,
                failed=failed,
                skipped=skipped,
                duration_ms=elapsed_ms,
                output_summary=summary,
                results=case_results,
            )

    return overall_exit


if __name__ == "__main__":
    raise SystemExit(main())
