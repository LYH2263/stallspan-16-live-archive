from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Segment
router = APIRouter(prefix="/segments", tags=["segments"])


class SegmentPatch(BaseModel):
    width_m: float | None = None
    name: str | None = None


@router.get("")
def list_segments(db: Session = Depends(get_db)):
    return [{"id": r.id, "market_day_id": r.market_day_id, "name": r.name, "width_m": r.width_m}
            for r in db.scalars(select(Segment).order_by(Segment.id)).all()]


@router.patch("/{segment_id}")
def patch_segment(segment_id: int, body: SegmentPatch, db: Session = Depends(get_db)):
    row = db.get(Segment, segment_id)
    if not row:
        raise HTTPException(404, "街段不存在")
    if body.width_m is not None:
        if body.width_m <= 0:
            raise HTTPException(400, "街宽必须为正")
        row.width_m = body.width_m
    if body.name is not None and body.name.strip():
        row.name = body.name
    db.commit()
    return {"id": row.id, "market_day_id": row.market_day_id, "name": row.name, "width_m": row.width_m}
