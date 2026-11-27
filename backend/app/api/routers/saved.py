from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from backend.app.core.database import SavedItemORM, UserORM, get_db
from backend.app.core.security import get_current_user_optional
from backend.app.schemas.legal import SavedItemCreateRequest, SavedItemResponse

router = APIRouter(prefix="/api/saved", tags=["Saved Items"])


def _to_response(row: SavedItemORM) -> SavedItemResponse:
    return SavedItemResponse(
        id=row.id,
        item_type=row.item_type,  # type: ignore[arg-type]
        target_id=row.target_id,
        title=row.title,
        subtitle=row.subtitle,
        content=row.content,
        metadata=json.loads(row.metadata_json or "{}"),
        created_at=row.created_at,
    )


@router.get("", response_model=list[SavedItemResponse])
def list_saved_items(
    item_type: str | None = Query(default=None),
    current_user: UserORM | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> list[SavedItemResponse]:
    stmt = select(SavedItemORM).order_by(desc(SavedItemORM.created_at))
    if current_user is not None:
        stmt = stmt.where((SavedItemORM.user_id == current_user.id) | (SavedItemORM.user_id.is_(None)))
    else:
        stmt = stmt.where(SavedItemORM.user_id.is_(None))
    if item_type and item_type in {"document", "clause", "answer"}:
        stmt = stmt.where(SavedItemORM.item_type == item_type)
    rows = db.execute(stmt).scalars().all()
    return [_to_response(r) for r in rows]


@router.post("", response_model=SavedItemResponse, status_code=201)
def create_saved_item(
    payload: SavedItemCreateRequest,
    current_user: UserORM | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> SavedItemResponse:
    uid = current_user.id if current_user else None
    existing = db.execute(
        select(SavedItemORM).where(
            SavedItemORM.user_id == uid,
            SavedItemORM.item_type == payload.item_type,
            SavedItemORM.target_id == payload.target_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return _to_response(existing)

    row = SavedItemORM(
        id=f"SAV-{uuid.uuid4().hex[:10].upper()}",
        user_id=uid,
        item_type=payload.item_type,
        target_id=payload.target_id,
        title=payload.title,
        subtitle=payload.subtitle,
        content=payload.content,
        metadata_json=json.dumps(payload.metadata, ensure_ascii=False),
        created_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_response(row)


@router.delete("/{saved_id}")
def delete_saved_item(
    saved_id: str,
    current_user: UserORM | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    row = db.get(SavedItemORM, saved_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy mục đã lưu.")
    if row.user_id is not None:
        if current_user is None or (current_user.role != "admin" and row.user_id != current_user.id):
            raise HTTPException(status_code=403, detail="Bạn không có quyền xóa mục đã lưu này.")
    db.delete(row)
    db.commit()
    return {"status": "deleted", "id": saved_id}
