"""差值纯函数测试：三类划分、拒因隔离、无历史不半成功。"""
import json

from app.services.first_fit_engine import REJECT_REASON, diff_allocations


def _pl(vid, name, s, e, w):
    return {"vendor_id": vid, "vendor_name": name, "start_m": s, "end_m": e, "width_m": w}


def _rx(vid, name, w, reason=REJECT_REASON):
    return {"vendor_id": vid, "vendor_name": name, "width_m": w, "reason": reason}


def test_empty_when_either_side_missing():
    live = {"placements": [_pl(1, "甲", 0, 4, 4)]}
    assert diff_allocations(live, None) == {"only_live": [], "only_history": [], "drifted": []}
    assert diff_allocations(None, live) == {"only_live": [], "only_history": [], "drifted": []}
    assert diff_allocations(None, None)["drifted"] == []


def test_only_live_and_only_history_are_in_out_changes():
    live = {"placements": [_pl(1, "甲", 0, 4, 4), _pl(2, "乙", 4, 7, 3)]}
    history = {"placements": [_pl(2, "乙", 4, 7, 3), _pl(3, "丙", 7, 12, 5)]}
    d = diff_allocations(live, history)
    assert [x["vendor_id"] for x in d["only_live"]] == [1]
    assert [x["vendor_id"] for x in d["only_history"]] == [3]
    assert d["drifted"] == []


def test_drifted_reports_start_end_deltas():
    # 手作皮具因大碗面改宽而前移：仅坐标变化，宽度本身未变
    live = {"placements": [_pl(6, "手作皮具", 10.25, 13.75, 3.5)]}
    history = {"placements": [_pl(6, "手作皮具", 16.25, 19.75, 3.5)]}
    d = diff_allocations(live, history)
    assert d["only_live"] == [] and d["only_history"] == []
    row = d["drifted"][0]
    assert row["vendor_id"] == 6
    assert row["start_delta_m"] == -6.0
    assert row["end_delta_m"] == -6.0


def test_vendor_width_change_that_keeps_placement_is_drift_not_reject():
    # 改宽后仍在图上但起止变化 -> drifted，而不是被写成任何拒因
    live = {"placements": [_pl(5, "大碗面", 0, 8, 8)]}
    history = {"placements": [_pl(5, "大碗面", 0, 6, 6)]}
    d = diff_allocations(live, history)
    assert [x["vendor_id"] for x in d["drifted"]] == [5]
    assert d["only_live"] == [] and d["only_history"] == []


def test_rejected_never_creates_drift_and_reason_never_merges_into_diff():
    # 大碗面历史上画着，现算被拒（placements 缺席）-> 仅历史有，属进出图，不是漂移
    live = {"placements": [_pl(1, "阿强烧烤", 0, 4, 4)],
            "rejected": [_rx(5, "大碗面", 12)]}
    history = {"placements": [_pl(1, "阿强烧烤", 0, 4, 4), _pl(5, "大碗面", 10.25, 16.25, 6)],
               "rejected": [_rx(7, "巨型舞台车", 12)]}
    d = diff_allocations(live, history)
    assert [x["vendor_id"] for x in d["only_history"]] == [5]
    assert d["drifted"] == []
    # 差值条不得出现任何一侧的拒因文案（不得并句、不得把漂移冒充空隙不足）
    assert REJECT_REASON not in json.dumps(d, ensure_ascii=False)
    for key in ("reason", "rejected", "live_reason", "history_reason"):
        assert key not in d["only_history"][0]


def test_identical_coordinates_mean_no_diff():
    side = {"placements": [_pl(1, "甲", 0, 4, 4), _pl(2, "乙", 4.0, 7.0, 3.0)]}
    d = diff_allocations(side, {"placements": list(reversed(side["placements"]))})
    assert d == {"only_live": [], "only_history": [], "drifted": []}


def test_float_noise_below_tolerance_is_not_drift():
    # 引擎统一 round 到 0.001，真实输出只会差 >=0.001；容差只为吸收浮点噪声
    live = {"placements": [_pl(1, "甲", 0.0, 4.0, 4.0)]}
    history = {"placements": [_pl(1, "甲", 1e-10, 4.0 + 1e-10, 4.0)]}
    assert diff_allocations(live, history)["drifted"] == []


def test_real_millimetre_delta_is_drift():
    live = {"placements": [_pl(1, "甲", 0.0, 4.0, 4.0)]}
    history = {"placements": [_pl(1, "甲", 0.0, 4.001, 4.0)]}
    d = diff_allocations(live, history)
    assert len(d["drifted"]) == 1
    assert d["drifted"][0]["end_delta_m"] == -0.001
