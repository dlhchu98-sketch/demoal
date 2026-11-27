from __future__ import annotations

import logging
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.app.api.routes import router as api_router
from backend.app.core.config import get_settings
from backend.app.core.database import SessionLocal, init_db
from backend.app.services.legal_ingestion_service import legal_ingestion_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[1]
STATIC_DIR = BACKEND_DIR / "static"


def _background_startup_sync() -> None:
    try:
        with SessionLocal() as db:
            if legal_ingestion_service._list_directory_files():
                scan_res = legal_ingestion_service.scan_directory(
                    db,
                    auto_ingest=True,
                    allow_update=False,
                )
                logger.info("Auto-scan startup (background): %s", scan_res.message)
    except Exception as exc:
        logger.warning("Không thể tự động quét data/legal_documents/ khi khởi động: %s", exc)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    settings = get_settings()
    if settings.auto_scan_on_startup:
        threading.Thread(
            target=_background_startup_sync,
            name="legal-auto-scan-startup",
            daemon=True,
        ).start()
    yield


def create_app() -> FastAPI:
    init_db()
    settings = get_settings()
    app = FastAPI(
        title=f"{settings.app_name} API",
        description=settings.app_full_name,
        version="2.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()] or ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_timing_middleware(request: Request, call_next):
        t0 = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception as exc:
            logger.exception("Unhandled error on %s %s: %s", request.method, request.url.path, exc)
            return JSONResponse(
                status_code=500,
                content={"detail": "Lỗi hệ thống nội bộ. Vui lòng thử lại hoặc kiểm tra nhật ký máy chủ."},
            )
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        response.headers["X-Process-Time-Ms"] = str(elapsed_ms)
        # Cho phép trình duyệt gọi từ HTTPS (GitHub Pages) về Backend cục bộ (Private Network Access)
        if request.headers.get("access-control-request-private-network") == "true":
            response.headers["Access-Control-Allow-Private-Network"] = "true"
        return response

    app.include_router(api_router)

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    def _serve_spa():
        index_file = STATIC_DIR / "index.html"
        if index_file.exists():
            return FileResponse(index_file, media_type="text/html")
        return {
            "name": settings.app_name,
            "description": settings.app_full_name,
            "docs": "/docs",
            "health": "/health",
        }

    @app.get("/", include_in_schema=False)
    @app.get("/index.html", include_in_schema=False)
    @app.get("/user", include_in_schema=False)
    @app.get("/user/{subpath:path}", include_in_schema=False)
    @app.get("/admin", include_in_schema=False)
    @app.get("/admin/{subpath:path}", include_in_schema=False)
    @app.get("/login", include_in_schema=False)
    def serve_ui(subpath: str = ""):
        return _serve_spa()

    return app


app = create_app()
