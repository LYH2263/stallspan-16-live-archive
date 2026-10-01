import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import AllocationRun, Pillar, Segment, Vendor
from app.services.first_fit_engine import (
    allocate_first_fit,
    diff_allocations,
    result_to_dict,
)

router = APIRouter(prefix="/allocate", tags=["allocate"])


def _compute_current(db: Session, seg: Segment) -> dict:
    """按数据库当前状态（街宽 / 挡柱 / 摊宽）现场重算，绝不读取任何历史快照边界。"""
    pillars = [{"position_m": p.position_m, "thickness_m": p.thickness_m, "label": p.label}
               for p in db.scalars(select(Pillar).where(Pillar.segment_id == seg.id)).all()]
    vendors = [{"id": v.id, "name": v.name, "stall_width_m": v.stall_width_m, "priority": v.priority}
               for v in db.scalars(select(Vendor).where(Vendor.market_day_id == seg.market_day_id)).all()]
    result = result_to_dict(allocate_first_fit(seg.width_m, vendors, pillars))
    result["segment"] = {"id": seg.id, "name": seg.name, "width_m": seg.width_m}
    result["pillars"] = pillars
    return result


@router.get("/preview")
def preview(segment_id: int = 1, run_id: int | None = None, db: Session = Depends(get_db)):
    """左现算 + 右历史 + 中差值，一次请求原子产出。

    - current 永远按当前 DB 状态现算（改宽后调用即得新结果，不沿用改前快照）。
    - run_id 为空：history=None、diff 三类全空，绝不偷偷填最近一次运行。
    - run_id 给定但不存在 / 不属于该街段：404，不返回半成功的差值行。
    - 历史内容原样读落库 JSON，不用现算结果改它一个字。
    """
    seg = db.get(Segment, segment_id)
    if not seg:
        raise HTTPException(404, "街段不存在")

    current = _compute_current(db, seg)

    history = None
    history_data = None
    if run_id is not None:
        run = db.get(AllocationRun, run_id)
        if not run or run.segment_id != segment_id:
            raise HTTPException(404, "历史运行不存在")
        history_data = json.loads(run.result_json)
        history = {
            "id": run.id,
            "created_at": run.created_at.isoformat() if run.created_at else None,
            **history_data,
        }

    # 左右图与差值共用同一套区间口径：两边 placements 均为 allocate_first_fit 产物。
    diff = diff_allocations(current, history_data)
    return {"current": current, "history": history, "diff": diff}


@router.post("/run")
def run_allocate(segment_id: int = 1, db: Session = Depends(get_db)):
    """把当前现算结果存档为一次历史运行（落库当时是什么，以后点开就是什么）。"""
    seg = db.get(Segment, segment_id)
    if not seg:
        raise HTTPException(404, "街段不存在")
    result = _compute_current(db, seg)
    run = AllocationRun(segment_id=segment_id, created_at=datetime.utcnow(),
                        result_json=json.dumps(result, ensure_ascii=False))
    db.add(run)
    db.commit()
    db.refresh(run)
    return {"id": run.id, "created_at": run.created_at.isoformat(), **result}


@router.get("/runs")
def list_runs(segment_id: int = 1, db: Session = Depends(get_db)):
    runs = db.scalars(
        select(AllocationRun)
        .where(AllocationRun.segment_id == segment_id)
        .order_by(AllocationRun.id.desc())
    ).all()
    out = []
    for run in runs:
        data = json.loads(run.result_json)
        seg_meta = data.get("segment") or {}
        out.append({
            "id": run.id,
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "segment_name": seg_meta.get("name"),
            "width_m": seg_meta.get("width_m"),
            "placed_count": len(data.get("placements") or []),
            "rejected_count": len(data.get("rejected") or []),
        })
    return out


@router.get("/runs/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db)):
    """原样返回落库快照；不存在就是 404，绝不现算补填。"""
    run = db.get(AllocationRun, run_id)
    if not run:
        raise HTTPException(404, "历史运行不存在")
    data = json.loads(run.result_json)
    return {"id": run.id,
            "created_at": run.created_at.isoformat() if run.created_at else None,
            **data}


@router.get("/latest")
def latest(segment_id: int = 1, db: Session = Depends(get_db)):
    """只读最近一次存档；没有存档时返回 null，不隐式触发现算落库。"""
    run = db.scalars(select(AllocationRun).where(AllocationRun.segment_id == segment_id)
                     .order_by(AllocationRun.id.desc())).first()
    if not run:
        return None
    data = json.loads(run.result_json)
    return {"id": run.id,
            "created_at": run.created_at.isoformat() if run.created_at else None,
            **data}
