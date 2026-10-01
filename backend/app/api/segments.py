from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Segment
router = APIRouter(prefix="/segments", tags=["segments"])

@router.get("")
def list_segments(db: Session = Depends(get_db)):
    return [{"id": r.id, "market_day_id": r.market_day_id, "name": r.name, "width_m": r.width_m}
            for r in db.scalars(select(Segment).order_by(Segment.id)).all()]


class SegmentPatch(BaseModel):
    width_m: float


@router.patch("/{segment_id}")
def patch_segment(segment_id: int, body: SegmentPatch, db: Session = Depends(get_db)):
    if body.width_m <= 0:
        raise HTTPException(422, "街宽必须为正数")
    seg = db.get(Segment, segment_id)
    if not seg:
        raise HTTPException(404, "街段不存在")
    seg.width_m = float(body.width_m)
    db.commit()
    db.refresh(seg)
    return {"id": seg.id, "market_day_id": seg.market_day_id,
            "name": seg.name, "width_m": seg.width_m}
