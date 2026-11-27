from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "LEGAL ASSISTANT"
    app_full_name: str = "Trợ lý tra cứu pháp luật sử dụng RAG, Agent và cơ chế tự kiểm tra trích dẫn"
    app_mode: str = os.getenv("APP_MODE", "demo")  # demo | live
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    # Authentication & RBAC (override JWT_SECRET_KEY in production .env)
    jwt_secret_key: str = os.getenv("JWT_SECRET_KEY", "legal-assistant-dev-secret-change-in-prod-2026")
    jwt_expire_minutes: int = int(os.getenv("JWT_EXPIRE_MINUTES", "720"))
    default_admin_email: str = os.getenv("DEFAULT_ADMIN_EMAIL", "admin@legalai.vn")
    default_admin_password: str = os.getenv("DEFAULT_ADMIN_PASSWORD", "Admin@123")
    default_user_email: str = os.getenv("DEFAULT_USER_EMAIL", "user@legalai.vn")
    default_user_password: str = os.getenv("DEFAULT_USER_PASSWORD", "User@123")

    # Database: PostgreSQL in production/Docker, SQLite local fallback for instant run
    database_url: str = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{(PROJECT_ROOT / 'data' / 'legal_assistant.db').as_posix()}",
    )

    # Vector DB (Qdrant): auto | remote | local
    qdrant_mode: str = os.getenv("QDRANT_MODE", "auto")
    qdrant_url: str = os.getenv("QDRANT_URL", "http://localhost:6333")
    qdrant_collection: str = os.getenv("QDRANT_COLLECTION", "vietnam_legal_docs")
    qdrant_local_path: str = os.getenv(
        "QDRANT_LOCAL_PATH",
        str(PROJECT_ROOT / "data" / "qdrant_storage"),
    )

    # LLM & Embedding (never hardcode API keys)
    llm_provider: str = os.getenv("LLM_PROVIDER", "openai_compatible")
    llm_model: str = os.getenv("LLM_MODEL", "gemini-2.0-flash")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    embedding_model: str = os.getenv(
        "EMBEDDING_MODEL",
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    )

    # Tự động quét thư mục văn bản pháp luật khi khởi động
    auto_scan_on_startup: bool = True

    # Agent self-correction limit
    max_self_correction_attempts: int = 2
    cors_origins: str = "*"

    @property
    def data_dir(self) -> Path:
        return PROJECT_ROOT / "data"

    @property
    def questions_dir(self) -> Path:
        return self.data_dir / "questions"

    @property
    def legal_documents_dir(self) -> Path:
        return self.data_dir / "legal_documents"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.questions_dir.mkdir(parents=True, exist_ok=True)
    settings.legal_documents_dir.mkdir(parents=True, exist_ok=True)
    return settings
