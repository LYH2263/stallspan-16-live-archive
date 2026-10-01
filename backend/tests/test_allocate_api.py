"""端到端验收：种子 → 存档一版 → 改大碗面宽度，验证现算/历史/差值三者口径。"""
from app.services.first_fit_engine import result_to_dict, allocate_first_fit


def _ids(rows):
    return {r["vendor_id"] for r in rows}


def test_preview_without_run_has_blank_history_and_empty_diff(client):
    r = client.get("/api/allocate/preview?segment_id=1")
    assert r.status_code == 200
    body = r.json()
    assert body["history"] is None
    assert body["diff"] == {"only_current": [], "only_history": [], "drift": []}
    # 左侧必须已经现算出来（不是半成功空壳）
    assert len(body["current"]["placements"]) == 6
    assert {p["vendor_name"] for p in body["current"]["rejected"]} == {"巨型舞台车"}


def test_preview_unknown_run_404_not_synthetic(client):
    r = client.get("/api/allocate/preview?segment_id=1&run_id=999")
    assert r.status_code == 404


def test_archive_then_select_shows_frozen_snapshot(client):
    saved = client.post("/api/allocate/run?segment_id=1").json()
    run_id = saved["id"]
    body = client.get(f"/api/allocate/preview?segment_id=1&run_id={run_id}").json()

    assert body["history"] is not None
    assert body["history"]["id"] == run_id
    # 刚存档、数据未改 => 无差值
    assert body["diff"] == {"only_current": [], "only_history": [], "drift": []}
    # 历史快照与现算逐字段一致（同一套区间算法）
    assert body["history"]["placements"] == body["current"]["placements"]


def test_change_danwanmian_width_current_recomputes_diff_names_drift_history_frozen(client):
    # 1) 先确认种子一版并存档
    saved = client.post("/api/allocate/run?segment_id=1").json()
    run_id = saved["id"]
    hist_placements = {p["vendor_id"]: p for p in saved["placements"]}
    assert hist_placements[5]["vendor_name"] == "大碗面"
    assert abs(hist_placements[5]["end_m"] - 16.25) < 1e-6

    # 2) 改大碗面摊宽 6 -> 8
    pr = client.patch("/api/vendors/5", json={"stall_width_m": 8.0})
    assert pr.status_code == 200
    assert pr.json()["stall_width_m"] == 8.0

    # 3) 现算按刚改宽度重算；差值点名大碗面漂移；历史保持落库当时
    body = client.get(f"/api/allocate/preview?segment_id=1&run_id={run_id}").json()
    cur_placements = {p["vendor_id"]: p for p in body["current"]["placements"]}
    his = body["history"]

    # 左侧用的是新宽度（不得沿用改前现算快照）
    assert abs(cur_placements[5]["width_m"] - 8.0) < 1e-6
    assert abs(cur_placements[5]["end_m"] - 18.25) < 1e-6

    # 右侧旧运行不被现算改宽污染
    his_dwm = next(p for p in his["placements"] if p["vendor_id"] == 5)
    assert abs(his_dwm["width_m"] - 6.0) < 1e-6
    assert his_dwm["end_m"] == 16.25

    # 差值同步：点名大碗面漂移（不是 only_*，因为两侧都放下）
    drift = {d["vendor_id"]: d for d in body["diff"]["drift"]}
    assert 5 in drift
    assert abs(drift[5]["delta_end_m"] - 2.0) < 1e-6
    # 现算放下者绝不出现在「仅历史有」
    assert _ids(cur_placements.values()).isdisjoint(_ids(body["diff"]["only_history"]))


def test_history_not_polluted_after_street_width_change(client):
    saved = client.post("/api/allocate/run?segment_id=1").json()
    run_id = saved["id"]
    client.patch("/api/segments/1", json={"width_m": 22.0})

    body = client.get(f"/api/allocate/preview?segment_id=1&run_id={run_id}").json()
    his = body["history"]
    # 历史街宽/色块仍是 30m 那一版
    assert his["segment"]["width_m"] == 30.0
    assert abs(next(p for p in his["placements"] if p["vendor_id"] == 5)["end_m"] - 16.25) < 1e-6
    # 左侧按新街宽
    assert body["current"]["segment"]["width_m"] == 22.0

    # 再拉一次独立快照接口，落库 JSON 原样未变
    again = client.get(f"/api/allocate/runs/{run_id}").json()
    assert again["segment"]["width_m"] == 30.0
    assert len(again["placements"]) == 6


def test_runs_endpoint_and_get_missing(client):
    assert client.get("/api/allocate/runs?segment_id=1").json() == []
    assert client.get("/api/allocate/runs/123").status_code == 404


def test_latest_null_when_no_run(client):
    # 不再隐式触发现算落库
    assert client.get("/api/allocate/latest?segment_id=1").json() is None
    assert client.get("/api/allocate/runs?segment_id=1").json() == []


def test_invalid_width_rejected(client):
    assert client.patch("/api/segments/1", json={"width_m": -1}).status_code == 422
    assert client.patch("/api/vendors/5", json={"stall_width_m": 0}).status_code == 422


def test_preview_current_matches_engine_run_on_live_db(client, db_session):
    # 改宽后，/preview 的现算侧必须等于拿当前 DB 数据直接跑同一引擎（不得沿用改前快照）
    from app.models.models import Pillar, Segment, Vendor
    from sqlalchemy import select

    client.patch("/api/vendors/5", json={"stall_width_m": 9.5})
    body = client.get("/api/allocate/preview?segment_id=1").json()

    seg = db_session.get(Segment, 1)
    pillars = [{"position_m": p.position_m, "thickness_m": p.thickness_m}
               for p in db_session.scalars(select(Pillar).where(Pillar.segment_id == 1)).all()]
    vendors = [{"id": v.id, "name": v.name, "stall_width_m": v.stall_width_m, "priority": v.priority}
               for v in db_session.scalars(select(Vendor).where(Vendor.market_day_id == seg.market_day_id)).all()]
    expect = result_to_dict(allocate_first_fit(seg.width_m, vendors, pillars))
    assert body["current"]["placements"] == expect["placements"]
    assert body["current"]["rejected"] == expect["rejected"]


def test_archived_snapshot_remains_identical_bytes(client):
    first = client.post("/api/allocate/run?segment_id=1").json()
    rid = first["id"]
    # 多次改宽 + 再存档，旧 run 原样不变
    client.patch("/api/vendors/5", json={"stall_width_m": 8.0})
    client.patch("/api/segments/1", json={"width_m": 24.0})
    client.post("/api/allocate/run?segment_id=1")

    old = client.get(f"/api/allocate/runs/{rid}").json()
    for key in ("placements", "rejected", "free_spans", "pillars"):
        assert old[key] == first[key]
    assert old["segment"]["width_m"] == 30.0
    listed = {r["id"] for r in client.get("/api/allocate/runs?segment_id=1").json()}
    assert listed == {rid, rid + 1}

