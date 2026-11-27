# LEGAL AI ASSISTANT — Trợ lý tra cứu pháp luật sử dụng RAG, Multi-Agent và cơ chế tự kiểm tra trích dẫn

## 1. Giới thiệu đề tài

**LEGAL AI ASSISTANT** là hệ thống hỗ trợ người dùng phổ thông và sinh viên tra cứu pháp luật Việt Nam bằng ngôn ngữ tự nhiên, giải quyết bài toán đối chiếu nhiều văn bản pháp luật theo Điều/Khoản/Điểm và tự kiểm tra tính xác thực của trích dẫn trước khi trả kết quả.

> **Phạm vi:** Hệ thống hỗ trợ tra cứu, tổng hợp và dẫn nguồn pháp luật; **không thay thế tư vấn pháp lý chính thức**.

## 2. Kiến trúc sản phẩm & Hai cổng giao diện riêng biệt

- **User Portal (`/user` & `/`):** 8 trang chuyên biệt (Trang chủ, Trợ lý pháp luật nhiều lượt, Theo dõi 7 bước xử lý thật, Kết quả tra cứu chuẩn A–E, Tra cứu văn bản, Lịch sử tra cứu, Văn bản đã lưu, Tài khoản).
- **Admin Portal (`/admin` — bảo vệ RBAC `role=admin`):** 8 trang quản trị riêng (Dashboard số liệu thật, Quản lý văn bản, Quản lý dữ liệu RAG, Theo dõi Agent, Citation Validator, Testing Dashboard, Quản lý người dùng & phân quyền, Cấu hình hệ thống không lộ API Key).
- **Unified FastAPI Backend (`:8000`):** Dùng chung một Backend FastAPI, PostgreSQL (fallback SQLite cục bộ), Qdrant Vector DB, RAG (`rag/`), Agent & Citation Validator (`agent/`).

Xem tài liệu kiến trúc chi tiết & sơ đồ Mermaid tại [docs/ARCHITECTURE_AND_GUIDE.md](docs/ARCHITECTURE_AND_GUIDE.md).

## 3. Phân công thành viên nhóm

| Thành viên | Branch | Phạm vi phụ trách |
|---|---|---|
| **Nguyễn Thanh Hiền** | `feature/rag` | Thu thập/làm sạch dữ liệu pháp luật, Chunking, Embedding, Qdrant, Vector Search, Đánh giá Retrieval (`rag/`) |
| **Đặng Thị Ngọc Ánh** | `feature/agent` | LangGraph Agent, Phân tích & phân rã câu hỏi, Multi-document Retrieval, Citation Validator, Self-Correction (`agent/`) |
| **Đỗ Lê Hân** | `feature/backend`, `feature/frontend` | Backend FastAPI, Authentication/RBAC, User Portal, Admin Portal, AI Integration Adapter, Demo & Tổng hợp kiến trúc |
| **Nguyễn Thị Nhi** | `feature/devops` | GitHub, Branch Protection, Docker, Docker Compose, CI/CD, Testing, Evaluation (`evaluation/`), Deployment |

## 4. Hướng dẫn cài đặt & chạy nhanh

### Cách 1: Chạy trực tiếp trên máy tính (Python 3.12+)

```bash
pip install -r backend/requirements.txt
python app.py
```

Truy cập:
- **User Portal:** `http://127.0.0.1:8000/user` (hoặc `http://127.0.0.1:8000`)
- **Admin Portal:** `http://127.0.0.1:8000/admin`
- **Swagger API Docs:** `http://127.0.0.1:8000/docs`
- **Healthcheck:** `http://127.0.0.1:8000/health`

Tài khoản khởi tạo phục vụ kiểm thử / bảo vệ đồ án:
- **Admin:** `admin@legalai.vn` / `Admin@123`
- **User:** `user@legalai.vn` / `User@123`

### Cách 2: Chạy đầy đủ với Docker Compose (PostgreSQL + Qdrant + Backend + Next.js Frontend)

```bash
cp .env.example .env
docker compose up --build -d
```
- **Next.js Frontend:** `http://localhost:3000` (User) và `http://localhost:3000/admin` (Admin)
- **FastAPI Backend & Portal tích hợp:** `http://localhost:8000`
- **Qdrant Dashboard:** `http://localhost:6333/dashboard`

## 5. Nhóm API chính (Swagger `/docs`)

- **Authentication:** `POST /api/auth/register`, `POST /api/auth/login`, `POST /api/auth/logout`, `GET/PUT /api/auth/me`, `POST /api/auth/change-password`
- **Chat & History:** `POST /api/chat`, `GET/DELETE /api/chat/conversations/*`, `POST /api/chat/{id}/feedback`, `GET/DELETE /api/history/*`
- **Saved Items:** `GET/POST/DELETE /api/saved/*`
- **Legal Documents:** `GET/POST/PUT/DELETE /api/legal-documents/*`, `POST /api/legal-documents/scan`, `POST /api/legal-documents/upload`, `POST /api/legal-documents/create`, `POST /api/legal-documents/{id}/reingest`
- **RAG:** `POST /api/rag/search`, `POST /api/rag/ingest`, `GET /api/rag/status`
- **Agent:** `POST /api/agent/analyze`, `GET /api/agent/status`, `GET /api/agent/logs`
- **Citation Validator:** `POST /api/citations/validate`, `GET /api/citations/report`, `GET /api/citations`, `GET /api/citations/{id}`
- **Questions Dataset (không đưa vào Qdrant):** `GET /api/questions`, `GET /api/questions/categories`, `POST /api/questions/upload`
- **Admin Portal (RBAC `admin`):** `GET /api/admin/dashboard`, `GET/PUT /api/admin/users/*`, `GET /api/admin/activity-logs`, `GET/PUT /api/admin/system-config`, `GET /api/admin/test-results`

## 6. Kiểm thử tự động (Pytest)

```bash
# Chạy toàn bộ test suite
python -m pytest backend/tests -v

# Chạy và lưu báo cáo kiểm thử thật vào Testing Dashboard của Admin Portal
python scripts/record_test_report.py
```
