from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Vendor
router = APIRouter(prefix="/vendors", tags=["vendors"])

@router.get("")
def list_vendors(db: Session = Depends(get_db)):
    return [{"id": r.id, "market_day_id": r.market_day_id, "name": r.name,
             "stall_width_m": r.stall_width_m, "priority": r.priority}
            for r in db.scalars(select(Vendor).order_by(Vendor.priority, Vendor.id)).all()]


class VendorPatch(BaseModel):
    stall_width_m: float


@router.patch("/{vendor_id}")
def patch_vendor(vendor_id: int, body: VendorPatch, db: Session = Depends(get_db)):
    if body.stall_width_m <= 0:
        raise HTTPException(422, "摊宽必须为正数")
    v = db.get(Vendor, vendor_id)
    if not v:
        raise HTTPException(404, "摊主不存在")
    v.stall_width_m = float(body.stall_width_m)
    db.commit()
    db.refresh(v)
    return {"id": v.id, "market_day_id": v.market_day_id, "name": v.name,
            "stall_width_m": v.stall_width_m, "priority": v.priority}
