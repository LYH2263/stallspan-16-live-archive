from app.services.first_fit_engine import (
    INTERVAL_EPS,
    allocate_first_fit,
    diff_allocations,
    free_spans_from_pillars,
    result_to_dict,
)

PILLARS = [{"position_m": 10.0, "thickness_m": 0.5}, {"position_m": 20.0, "thickness_m": 0.5}]
VENDORS = [
    {"id": 1, "name": "阿强烧烤", "stall_width_m": 4.0, "priority": 1},
    {"id": 2, "name": "林记糖水", "stall_width_m": 3.0, "priority": 1},
    {"id": 3, "name": "老周水果", "stall_width_m": 5.0, "priority": 2},
    {"id": 4, "name": "小美饰品", "stall_width_m": 2.5, "priority": 2},
    {"id": 5, "name": "大碗面", "stall_width_m": 6.0, "priority": 1},
    {"id": 6, "name": "手作皮具", "stall_width_m": 3.5, "priority": 3},
    {"id": 7, "name": "巨型舞台车", "stall_width_m": 12.0, "priority": 9},
]


def _run(width_m=30.0, widths=None):
    vs = [dict(v) for v in VENDORS]
    for vid, w in (widths or {}).items():
        for v in vs:
            if v["id"] == vid:
                v["stall_width_m"] = w
    return result_to_dict(allocate_first_fit(width_m, vs, PILLARS))


def test_free_spans_with_pillars():
    spans = free_spans_from_pillars(30.0, PILLARS)
    assert len(spans) == 3
    assert spans[0][0] == 0.0


def test_first_fit_no_cross_pillar():
    r = allocate_first_fit(30.0, VENDORS[:2], [{"position_m": 10.0, "thickness_m": 0.5}])
    assert any(p.vendor_name == "阿强烧烤" for p in r.placements)
    assert len(r.placements) + len(r.rejected) == 2


def test_reject_oversized():
    r = allocate_first_fit(30.0, [VENDORS[6]], PILLARS)
    assert len(r.rejected) == 1
    assert r.rejected[0].vendor_name == "巨型舞台车"


# ---------- 差值口径 ----------

def test_diff_none_history_is_empty():
    seed = _run()
    assert diff_allocations(seed, None) == {"only_current": [], "only_history": [], "drift": []}


def test_diff_identical_runs_empty():
    d = diff_allocations(_run(), _run())
    assert d == {"only_current": [], "only_history": [], "drift": []}


def test_widen_danwanmian_names_drift_not_gap():
    # 历史=种子（大碗面6m）；现算=大碗面8m。大碗面仍放下，但终点漂移。
    history = _run()
    current = _run(widths={5: 8.0})
    d = diff_allocations(current, history)

    by_id = {row["vendor_id"]: row for row in d["drift"]}
    assert 5 in by_id, "差值必须点名大碗面"
    row = by_id[5]
    assert abs(row["history_end_m"] - 16.25) < 1e-6
    assert abs(row["current_end_m"] - 18.25) < 1e-6
    assert abs(row["delta_end_m"] - 2.0) < 1e-6
    # 两侧都在，故不得同时出现在进出图列表
    assert all(x["vendor_id"] != 5 for x in d["only_current"])
    assert all(x["vendor_id"] != 5 for x in d["only_history"])


def test_placed_current_never_in_only_history():
    history = _run()
    current = _run(widths={5: 8.0})
    d = diff_allocations(current, history)
    cur_placed = {p["vendor_id"] for p in current["placements"]}
    only_history = {x["vendor_id"] for x in d["only_history"]}
    assert cur_placed.isdisjoint(only_history)


def test_rejected_vendor_never_enters_diff():
    # 巨型舞台车两侧都因空隙不足被拒；漂移不是空隙不足，不得冒充进差值。
    history = _run()
    current = _run(widths={5: 8.0})
    d = diff_allocations(current, history)
    diff_ids = {x["vendor_id"] for grp in d.values() for x in grp}
    assert 7 not in diff_ids


def test_enter_and_exit_lists_when_width_change_evicts():
    # 街宽压到 22m：多个摊主在现算中放不下 -> 仅历史有；无新增放下。
    history = _run(30.0)
    current = _run(22.0)
    d = diff_allocations(current, history)
    cur_placed = {p["vendor_id"] for p in current["placements"]}
    his_placed = {p["vendor_id"] for p in history["placements"]}
    # 引擎口径与差植口径必须一致（同一套区间算法）
    assert {x["vendor_id"] for x in d["only_history"]} == (his_placed - cur_placed)
    assert {x["vendor_id"] for x in d["only_current"]} == (cur_placed - his_placed)
    # 漂移者 = 两侧都放下但区间移动
    drift_ids = {x["vendor_id"] for x in d["drift"]}
    assert drift_ids <= (cur_placed & his_placed)
    for x in d["drift"]:
        assert abs(x["delta_start_m"]) > INTERVAL_EPS or abs(x["delta_end_m"]) > INTERVAL_EPS


def test_diff_does_not_read_reasons():
    history = _run()
    current = _run(widths={5: 8.0})
    d = diff_allocations(current, history)
    # 差值载荷里不允许夹带任何一方的拒因文案
    import json
    blob = json.dumps(d, ensure_ascii=False)
    assert "无连续空档" not in blob
    assert "reason" not in blob
