"""
Kiểm thử Authentication (Register, Login, Logout, JWT revocation, Change Password)
và Role-Based Access Control (RBAC) giữa User Portal và Admin Portal.
"""

from __future__ import annotations

import uuid
from fastapi.testclient import TestClient

from backend.app.core.config import get_settings
from backend.app.main import app

client = TestClient(app)


def _login(identifier: str, password: str) -> dict:
    resp = client.post("/api/auth/login", json={"identifier": identifier, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_admin_and_user_default_login_and_rbac():
    settings = get_settings()

    # 1. Guest không được truy cập Admin Portal APIs
    assert client.get("/api/admin/dashboard").status_code == 401
    assert client.get("/api/admin/users").status_code == 401
    assert client.get("/api/admin/system-config").status_code == 401

    # 2. Regular User login -> /api/auth/me OK, nhưng Admin APIs trả 403 Forbidden
    user_auth = _login(settings.default_user_email, settings.default_user_password)
    assert user_auth["user"]["role"] == "user"
    user_headers = {"Authorization": f"Bearer {user_auth['access_token']}"}

    me_resp = client.get("/api/auth/me", headers=user_headers)
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == settings.default_user_email

    assert client.get("/api/admin/dashboard", headers=user_headers).status_code == 403
    assert client.get("/api/admin/users", headers=user_headers).status_code == 403
    assert client.get("/api/admin/system-config", headers=user_headers).status_code == 403

    # 3. Admin login -> truy cập đầy đủ Admin Portal APIs
    admin_auth = _login(settings.default_admin_email, settings.default_admin_password)
    assert admin_auth["user"]["role"] == "admin"
    admin_headers = {"Authorization": f"Bearer {admin_auth['access_token']}"}

    dash = client.get("/api/admin/dashboard", headers=admin_headers)
    assert dash.status_code == 200
    dash_body = dash.json()
    assert "total_documents" in dash_body
    assert "qdrant_status" in dash_body
    assert "database_status" in dash_body

    # 4. System config tuyệt đối không lộ raw API key
    cfg = client.get("/api/admin/system-config", headers=admin_headers)
    assert cfg.status_code == 200
    cfg_body = cfg.json()
    assert "llm_api_key_masked" in cfg_body
    assert "llm_api_key" not in cfg_body


def test_register_profile_password_change_logout_and_admin_lock():
    suffix = uuid.uuid4().hex[:8]
    username = f"tester_{suffix}"
    email = f"tester_{suffix}@legalai.vn"

    # Register
    reg = client.post(
        "/api/auth/register",
        json={
            "username": username,
            "email": email,
            "full_name": "Sinh Viên Kiểm Thử",
            "password": "Password123!",
        },
    )
    assert reg.status_code == 201, reg.text
    token = reg.json()["access_token"]
    user_id = reg.json()["user"]["id"]
    headers = {"Authorization": f"Bearer {token}"}

    # Duplicate rejected
    dup = client.post(
        "/api/auth/register",
        json={
            "username": username,
            "email": email,
            "full_name": "Duplicate",
            "password": "Password123!",
        },
    )
    assert dup.status_code == 409

    # Update profile
    upd = client.put("/api/auth/me", json={"full_name": "Sinh Viên Đã Cập Nhật"}, headers=headers)
    assert upd.status_code == 200
    assert upd.json()["full_name"] == "Sinh Viên Đã Cập Nhật"

    # Change password
    ch = client.post(
        "/api/auth/change-password",
        json={"current_password": "Password123!", "new_password": "NewPassword456!"},
        headers=headers,
    )
    assert ch.status_code == 200

    # Logout -> token bị thu hồi ngay lập tức
    out = client.post("/api/auth/logout", headers=headers)
    assert out.status_code == 200
    assert client.get("/api/auth/me", headers=headers).status_code == 401

    # Login lại bằng mật khẩu mới
    relogin = _login(email, "NewPassword456!")
    new_headers = {"Authorization": f"Bearer {relogin['access_token']}"}
    assert client.get("/api/auth/me", headers=new_headers).status_code == 200

    # Admin khóa tài khoản -> user bị 403
    settings = get_settings()
    admin_auth = _login(settings.default_admin_email, settings.default_admin_password)
    admin_headers = {"Authorization": f"Bearer {admin_auth['access_token']}"}

    lock_resp = client.put(
        f"/api/admin/users/{user_id}/status",
        json={"is_active": False},
        headers=admin_headers,
    )
    assert lock_resp.status_code == 200
    assert lock_resp.json()["is_active"] is False

    # User bị khóa không thể đăng nhập hay dùng token cũ
    assert client.get("/api/auth/me", headers=new_headers).status_code == 403
    assert client.post("/api/auth/login", json={"identifier": email, "password": "NewPassword456!"}).status_code == 403

    # Mở khóa lại
    unlock_resp = client.put(
        f"/api/admin/users/{user_id}/status",
        json={"is_active": True},
        headers=admin_headers,
    )
    assert unlock_resp.status_code == 200
    assert unlock_resp.json()["is_active"] is True
