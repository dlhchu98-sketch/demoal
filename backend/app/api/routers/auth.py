from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.app.core.database import UserORM, get_db
from backend.app.core.security import (
    bearer_scheme,
    create_access_token,
    get_current_user,
    hash_password,
    revoke_token,
    verify_password,
)
from backend.app.schemas.legal import (
    AuthTokenResponse,
    ChangePasswordRequest,
    UserLoginRequest,
    UserProfile,
    UserRegisterRequest,
    UserUpdateProfileRequest,
)
from backend.app.services.admin_service import log_activity, to_user_profile

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post("/register", response_model=AuthTokenResponse, status_code=status.HTTP_201_CREATED)
def register_user(payload: UserRegisterRequest, db: Session = Depends(get_db)) -> AuthTokenResponse:
    existing = db.execute(
        select(UserORM).where(
            or_(UserORM.email == payload.email.lower(), UserORM.username == payload.username.lower())
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email hoặc tên đăng nhập đã được sử dụng.",
        )

    now = datetime.now(timezone.utc)
    user = UserORM(
        id=f"USR-{uuid.uuid4().hex[:10].upper()}",
        username=payload.username.lower(),
        email=payload.email.lower(),
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        role="user",
        is_active=True,
        created_at=now,
        last_login_at=now,
    )
    db.add(user)
    log_activity(db, user=user, action="register", resource="auth", detail=f"Đăng ký tài khoản mới: {user.email}")
    db.commit()

    token, _, expires_in = create_access_token(user.id, user.email, user.role)
    return AuthTokenResponse(
        access_token=token,
        expires_in=expires_in,
        user=to_user_profile(user),
    )


@router.post("/login", response_model=AuthTokenResponse)
def login_user(payload: UserLoginRequest, db: Session = Depends(get_db)) -> AuthTokenResponse:
    ident = payload.identifier.strip().lower()
    user = db.execute(
        select(UserORM).where(or_(UserORM.email == ident, UserORM.username == ident))
    ).scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email/tên đăng nhập hoặc mật khẩu không chính xác.",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tài khoản đã bị khóa. Vui lòng liên hệ quản trị viên.",
        )

    user.last_login_at = datetime.now(timezone.utc)
    log_activity(db, user=user, action="login", resource="auth", detail=f"Đăng nhập thành công ({user.role})")
    db.commit()

    token, _, expires_in = create_access_token(user.id, user.email, user.role)
    return AuthTokenResponse(
        access_token=token,
        expires_in=expires_in,
        user=to_user_profile(user),
    )


@router.post("/logout")
def logout_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    current_user: UserORM = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    if credentials and credentials.credentials:
        revoke_token(db, credentials.credentials)
    log_activity(db, user=current_user, action="logout", resource="auth", detail="Đăng xuất phiên làm việc", commit=True)
    return {"status": "logged_out", "message": "Đã đăng xuất thành công."}


@router.get("/me", response_model=UserProfile)
def get_me(current_user: UserORM = Depends(get_current_user)) -> UserProfile:
    return to_user_profile(current_user)


@router.put("/me", response_model=UserProfile)
def update_me(
    payload: UserUpdateProfileRequest,
    current_user: UserORM = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserProfile:
    current_user.full_name = payload.full_name.strip()
    log_activity(db, user=current_user, action="update_profile", resource="auth", detail="Cập nhật họ tên cá nhân")
    db.commit()
    db.refresh(current_user)
    return to_user_profile(current_user)


@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    current_user: UserORM = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mật khẩu hiện tại không đúng.",
        )
    current_user.password_hash = hash_password(payload.new_password)
    log_activity(db, user=current_user, action="change_password", resource="auth", detail="Đổi mật khẩu tài khoản")
    db.commit()
    return {"status": "ok", "message": "Đổi mật khẩu thành công."}
