from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from backend.app.core.database import UserORM, get_db
from backend.app.core.security import require_admin
from backend.app.schemas.legal import (
    ActivityLogItem,
    AdminDashboardResponse,
    AdminUserUpdateRoleRequest,
    AdminUserUpdateStatusRequest,
    SystemConfigResponse,
    SystemConfigUpdateRequest,
    TestRunReportItem,
    UserProfile,
)
from backend.app.services.admin_service import (
    build_admin_dashboard,
    get_system_config_masked,
    list_activity_logs,
    list_test_reports,
    log_activity,
    to_user_profile,
)
from backend.app.services.chat_service import runtime_state

router = APIRouter(prefix="/api/admin", tags=["Admin Portal"])


def _get_ingestion_service():
    from backend.app.api import routes as routes_module

    return routes_module.legal_ingestion_service


@router.get("/dashboard", response_model=AdminDashboardResponse)
def get_admin_dashboard(
    admin: UserORM = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminDashboardResponse:
    return build_admin_dashboard(db, _get_ingestion_service())


@router.get("/users", response_model=list[UserProfile])
def list_users(
    search: str | None = Query(default=None),
    role: str | None = Query(default=None),
    admin: UserORM = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[UserProfile]:
    rows = db.execute(select(UserORM).order_by(desc(UserORM.created_at))).scalars().all()
    if role and role in {"user", "admin"}:
        rows = [u for u in rows if u.role == role]
    if search and search.strip():
        q = search.strip().lower()
        rows = [
            u
            for u in rows
            if q in u.username.lower() or q in u.email.lower() or q in u.full_name.lower()
        ]
    return [to_user_profile(u) for u in rows]


@router.put("/users/{user_id}/role", response_model=UserProfile)
def update_user_role(
    user_id: str,
    payload: AdminUserUpdateRoleRequest,
    admin: UserORM = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UserProfile:
    target = db.get(UserORM, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng.")
    if target.id == admin.id and payload.role != "admin":
        raise HTTPException(status_code=400, detail="Không thể tự hạ quyền quản trị viên của chính mình.")
    target.role = payload.role
    log_activity(
        db,
        user=admin,
        action="update_user_role",
        resource=f"user:{target.username}",
        detail=f"Đổi quyền tài khoản '{target.username}' sang '{payload.role}'.",
    )
    db.commit()
    db.refresh(target)
    return to_user_profile(target)


@router.put("/users/{user_id}/status", response_model=UserProfile)
def update_user_status(
    user_id: str,
    payload: AdminUserUpdateStatusRequest,
    admin: UserORM = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UserProfile:
    target = db.get(UserORM, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng.")
    if target.id == admin.id and not payload.is_active:
        raise HTTPException(status_code=400, detail="Không thể tự khóa tài khoản quản trị viên của chính mình.")
    target.is_active = payload.is_active
    log_activity(
        db,
        user=admin,
        action="update_user_status",
        resource=f"user:{target.username}",
        detail=f"{'Mở khóa' if payload.is_active else 'Khóa'} tài khoản '{target.username}'.",
    )
    db.commit()
    db.refresh(target)
    return to_user_profile(target)


@router.get("/activity-logs", response_model=list[ActivityLogItem])
def get_activity_logs(
    limit: int = Query(default=100, ge=1, le=500),
    admin: UserORM = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[ActivityLogItem]:
    return list_activity_logs(db, limit=limit)


@router.get("/system-config", response_model=SystemConfigResponse)
def get_system_config(admin: UserORM = Depends(require_admin)) -> SystemConfigResponse:
    return get_system_config_masked()


@router.put("/system-config", response_model=SystemConfigResponse)
def update_system_config(
    payload: SystemConfigUpdateRequest,
    admin: UserORM = Depends(require_admin),
    db: Session = Depends(get_db),
) -> SystemConfigResponse:
    changes: list[str] = []
    if payload.app_mode is not None:
        runtime_state.app_mode = payload.app_mode
        changes.append(f"app_mode={payload.app_mode}")
    if payload.llm_model is not None and payload.llm_model.strip():
        runtime_state.llm_model = payload.llm_model.strip()
        changes.append(f"llm_model={runtime_state.llm_model}")
    if payload.max_self_correction_attempts is not None:
        runtime_state.max_self_correction_attempts = payload.max_self_correction_attempts
        changes.append(f"max_self_correction_attempts={payload.max_self_correction_attempts}")
    log_activity(
        db,
        user=admin,
        action="update_system_config",
        resource="system_config",
        detail="Cập nhật cấu hình: " + (", ".join(changes) if changes else "không thay đổi"),
        commit=True,
    )
    return get_system_config_masked()


@router.get("/test-results", response_model=list[TestRunReportItem])
def get_test_results(
    limit: int = Query(default=30, ge=1, le=100),
    admin: UserORM = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[TestRunReportItem]:
    return list_test_reports(db, limit=limit)
