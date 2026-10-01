import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import AllocationRun, Pillar, Segment, Vendor
from app.services.first_fit_engine import (
    allocate_first_fit,
    diff_allocations,
    make_snapshot,
    result_to_dict,
)

router = APIRouter(prefix="/allocate", tags=["allocate"])


def _load_inputs(segment_id: int, db: Session) -> tuple[Segment, list[dict], list[dict]]:
    seg = db.get(Segment, segment_id)
    if not seg:
        raise HTTPException(404, "街段不存在")
    pillars = [
        {"id": p.id, "position_m": p.position_m, "thickness_m": p.thickness_m, "label": p.label}
        for p in db.scalars(select(Pillar).where(Pillar.segment_id == segment_id).order_by(Pillar.id)).all()
    ]
    vendors = [
        {"id": v.id, "name": v.name, "stall_width_m": v.stall_width_m, "priority": v.priority}
        for v in db.scalars(
            select(Vendor).where(Vendor.market_day_id == seg.market_day_id).order_by(Vendor.id)
        ).all()
    ]
    return seg, pillars, vendors


def _live_snapshot(seg: Segment, pillars: list[dict], vendors: list[dict]) -> dict:
    """现算：只跟当前街段宽度、当前挡柱、当前摊主宽度走，绝不读历史快照。"""
    result = result_to_dict(allocate_first_fit(seg.width_m, vendors, pillars))
    segment = {"id": seg.id, "name": seg.name, "width_m": seg.width_m}
    return make_snapshot(segment, pillars, result)


def _snapshot_from_run(run: AllocationRun) -> dict:
    """历史：原样解冻落库当时的快照，现算侧的任何改动都碰不到它。"""
    data = json.loads(run.result_json)
    return {"id": run.id, "created_at": run.created_at.isoformat(), **data}


@router.post("/preview")
def preview(segment_id: int = 1, db: Session = Depends(get_db)):
    """现算一版但不落库——改摊宽/街宽后左侧与差值都以它为准。"""
    seg, pillars, vendors = _load_inputs(segment_id, db)
    return _live_snapshot(seg, pillars, vendors)


@router.post("/run")
def run_allocate(segment_id: int = 1, db: Session = Depends(get_db)):
    """把当下的现算固化成一次历史运行；旧运行永不被回写。"""
    seg, pillars, vendors = _load_inputs(segment_id, db)
    snapshot = _live_snapshot(seg, pillars, vendors)
    run = AllocationRun(
        segment_id=segment_id,
        created_at=datetime.utcnow(),
        result_json=json.dumps(snapshot, ensure_ascii=False),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return _snapshot_from_run(run)


@router.get("/runs")
def list_runs(segment_id: int = 1, db: Session = Depends(get_db)):
    runs = db.scalars(
        select(AllocationRun)
        .where(AllocationRun.segment_id == segment_id)
        .order_by(AllocationRun.id.desc())
    ).all()
    return [
        {
            "id": r.id,
            "segment_id": r.segment_id,
            "created_at": r.created_at.isoformat(),
            "segment": json.loads(r.result_json).get("segment"),
            "placed_count": len(json.loads(r.result_json).get("placements", [])),
            "rejected_count": len(json.loads(r.result_json).get("rejected", [])),
        }
        for r in runs
    ]


@router.get("/runs/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db)):
    run = db.get(AllocationRun, run_id)
    if not run:
        raise HTTPException(404, "历史运行不存在")
    return _snapshot_from_run(run)


@router.get("/compare")
def compare(segment_id: int = 1, run_id: int | None = None, db: Session = Depends(get_db)):
    """一次响应同时给出左（现算）、右（历史）、中（差值）。

    三块共用本端点、同一套区间算法：live 永远用当前宽度重算；history 只取自落库快照；
    diff 由两侧 placements 坐标算出，不引用任何拒因。未给 run_id 时 history=null，
    diff 三类全空，不会偷偷补最近一次运行，也不会半成功写出差值行。
    """
    seg, pillars, vendors = _load_inputs(segment_id, db)
    live = _live_snapshot(seg, pillars, vendors)

    history = None
    if run_id is not None:
        run = db.get(AllocationRun, run_id)
        if not run or run.segment_id != segment_id:
            raise HTTPException(404, "历史运行不存在")
        history = _snapshot_from_run(run)

    return {
        "segment_id": segment_id,
        "live": live,
        "history": history,
        "diff": diff_allocations(live, history),
    }


@router.get("/latest")
def latest(segment_id: int = 1, db: Session = Depends(get_db)):
    """最近一次历史运行；没有运行时返回 null（不再自动创建）。"""
    run = db.scalars(
        select(AllocationRun)
        .where(AllocationRun.segment_id == segment_id)
        .order_by(AllocationRun.id.desc())
    ).first()
    return _snapshot_from_run(run) if run else None
