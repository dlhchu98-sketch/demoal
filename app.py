"""
LEGAL ASSISTANT — Trợ lý tra cứu pháp luật sử dụng RAG, Agent và cơ chế tự kiểm tra trích dẫn.
Chạy trực tiếp: python app.py
"""

from __future__ import annotations

import socket
import sys
from pathlib import Path
import uvicorn

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from backend.app.core.config import get_settings


def get_local_ip() -> str:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except Exception:
        return "127.0.0.1"


if __name__ == "__main__":
    settings = get_settings()
    local_ip = get_local_ip()
    port = settings.app_port

    print("\n" + "=" * 72)
    print("  LEGAL ASSISTANT — Trợ lý tra cứu pháp luật (RAG + Agent + Citation Validator)")
    print(f"  Chế độ hiện tại (APP_MODE): {settings.app_mode.upper()}")
    print("=" * 72)
    print(f"  Giao diện Web (Localhost):  http://127.0.0.1:{port}")
    print(f"  Truy cập nội bộ (Wi-Fi):    http://{local_ip}:{port}")
    print(f"  Tài liệu API (Swagger):     http://127.0.0.1:{port}/docs")
    print(f"  Healthcheck API:            http://127.0.0.1:{port}/health")
    print("=" * 72 + "\n")

    uvicorn.run(
        "backend.app.main:app",
        host=settings.app_host,
        port=port,
        reload=False,
    )
