"""Khởi chạy tạm FastAPI Uvicorn trên cổng 8011, kiểm tra thực tế User Portal, Admin Portal, Swagger & RBAC rồi dừng sạch."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", "8011"],
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        ready = False
        for _ in range(35):
            try:
                r = httpx.get("http://127.0.0.1:8011/health", timeout=1.0)
                if r.status_code == 200:
                    ready = True
                    break
            except Exception:
                time.sleep(0.3)
        if not ready:
            print("ERROR: Uvicorn did not become ready in time.")
            return 1

        checks = [
            ("GET /health", httpx.get("http://127.0.0.1:8011/health")),
            ("GET /user", httpx.get("http://127.0.0.1:8011/user")),
            ("GET /admin", httpx.get("http://127.0.0.1:8011/admin")),
            ("GET /docs", httpx.get("http://127.0.0.1:8011/docs")),
            ("GET /api/status", httpx.get("http://127.0.0.1:8011/api/status")),
            ("GET /api/questions", httpx.get("http://127.0.0.1:8011/api/questions?page=1&page_size=5")),
        ]
        for label, resp in checks:
            print(f"{label:22s} -> HTTP {resp.status_code} ({len(resp.content)} bytes)")
            assert resp.status_code == 200

        # Verify RBAC blocks unauthenticated admin dashboard
        unauth = httpx.get("http://127.0.0.1:8011/api/admin/dashboard")
        print(f"GET /api/admin (anon)  -> HTTP {unauth.status_code} (expected 401)")
        assert unauth.status_code == 401

        login = httpx.post(
            "http://127.0.0.1:8011/api/auth/login",
            json={"identifier": "admin@legalai.vn", "password": "Admin@123"},
        )
        assert login.status_code == 200
        hdr = {"Authorization": f"Bearer {login.json()['access_token']}"}

        dash = httpx.get("http://127.0.0.1:8011/api/admin/dashboard", headers=hdr)
        tlist = httpx.get("http://127.0.0.1:8011/api/admin/test-results", headers=hdr)
        assert dash.status_code == 200 and tlist.status_code == 200
        dj = dash.json()
        print(
            f"Admin Dashboard        -> HTTP 200 | docs={dj['total_documents']} "
            f"queries={dj['total_queries']} users={dj['total_users']}"
        )
        print(f"Admin Test Reports     -> HTTP 200 | stored_reports={len(tlist.json())}")
        print("LIVE HTTP SMOKE VERIFICATION PASSED!")
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
