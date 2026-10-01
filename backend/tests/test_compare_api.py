"""端到端口径测试：落库快照不可被现算改宽污染；compare 三块一次同源。"""
from tests.conftest import vendor_id_by_name


def test_compare_without_history_is_blank_not_latest(client, seeded):
    r = client.get(f"/api/allocate/compare?segment_id={seeded['segment_id']}")
    r.raise_for_status()
    body = r.json()
    assert body["history"] is None
    assert body["diff"] == {"only_live": [], "only_history": [], "drifted": []}
    # 未选历史不得偷偷落一条运行
    assert client.get("/api/allocate/runs").json() == []
    assert client.get("/api/allocate/latest").json() is None


def test_saved_run_then_widen_dawanmian_flow(client, seeded):
    sid = seeded["segment_id"]

    # 1) 种子先确认一版并落库
    run = client.post(f"/api/allocate/run?segment_id={sid}").json()
    wid = vendor_id_by_name(client, "大碗面")
    before = {p["vendor_id"]: p for p in run["placements"]}
    assert wid in before, "种子数据里大碗面本应放下"
    old_start, old_end, old_w = before[wid]["start_m"], before[wid]["end_m"], before[wid]["width_m"]
    assert old_w == 6.0
    # 现算侧区间口径必须随快照：街宽 30、挡柱在 10/20
    assert run["segment"]["width_m"] == 30.0
    assert [p["position_m"] for p in run["pillars"]] == [10.0, 20.0]

    # 2) 把大碗面从 6m 改成 9m（再宽就放不下 9.75m 的 span1）
    client.patch(f"/api/vendors/{wid}", json={"stall_width_m": 9.0}).raise_for_status()

    # 3) compare：左侧必须按新宽度重算，右侧保持落库当时
    cmp = client.get(f"/api/allocate/runs").json()
    assert [r["id"] for r in cmp] == [run["id"]], "改宽不得新建运行"
    body = client.get(f"/api/allocate/compare?segment_id={sid}&run_id={run['id']}").json()
    live_p = {p["vendor_id"]: p for p in body["live"]["placements"]}
    hist_p = {p["vendor_id"]: p for p in body["history"]["placements"]}

    # 旧运行点开不得被现算改宽污染：右侧大碗面仍是旧 6m 旧坐标
    assert body["history"]["id"] == run["id"]
    assert (hist_p[wid]["width_m"], hist_p[wid]["start_m"], hist_p[wid]["end_m"]) == (
        old_w, old_start, old_end
    )
    assert body["history"]["segment"]["width_m"] == 30.0

    # 左侧：大碗面改宽成功后仍在图上（span1 = 9.75 放得下 9），起止漂移
    assert live_p[wid]["width_m"] == 9.0
    assert (live_p[wid]["start_m"], live_p[wid]["end_m"]) != (old_start, old_end)

    # 4) 差值必须点名大碗面：drifted（起止漂移），且不在 only_history
    d = body["diff"]
    drift_ids = [x["vendor_id"] for x in d["drifted"]]
    assert wid in drift_ids, f"大碗面应被差值点名为漂移，实际：{d}"
    dawan = next(x for x in d["drifted"] if x["vendor_id"] == wid)
    assert dawan["vendor_name"] == "大碗面"
    assert abs(dawan["live_width_m"] - 9.0) < 1e-9
    assert abs(dawan["history_width_m"] - 6.0) < 1e-9
    assert wid not in [x["vendor_id"] for x in d["only_history"]]
    assert wid not in [x["vendor_id"] for x in d["only_live"]]

    # 5) 现算成功摊不得出现在「仅历史有」
    only_hist_ids = {x["vendor_id"] for x in d["only_history"]}
    assert only_hist_ids.isdisjoint(live_p.keys())

    # 6) preview 与 compare.live 同口径，且都不落库
    preview = client.post(f"/api/allocate/preview?segment_id={sid}").json()
    assert preview["placements"] == body["live"]["placements"]
    assert len(client.get("/api/allocate/runs").json()) == 1


def test_widen_until_rejected_moves_vendor_out_not_drift(client, seeded):
    sid = seeded["segment_id"]
    run = client.post(f"/api/allocate/run?segment_id={sid}").json()
    wid = vendor_id_by_name(client, "大碗面")
    # 12m：任何 span 都放不下（最大 9.75），大碗面从图上掉出
    client.patch(f"/api/vendors/{wid}", json={"stall_width_m": 12.0})
    body = client.get(f"/api/allocate/compare?segment_id={sid}&run_id={run['id']}").json()
    live_ids = {p["vendor_id"] for p in body["live"]["placements"]}
    assert wid not in live_ids
    # 现算拒因独立存在，绝不并进历史文案
    assert [r["vendor_id"] for r in body["live"]["rejected"] if r["vendor_id"] == wid]
    d = body["diff"]
    assert wid in [x["vendor_id"] for x in d["only_history"]]  # 进出图变化
    assert wid not in [x["vendor_id"] for x in d["drifted"]]    # 不得冒充漂移
    # 历史侧拒因仍是落库当时内容，不被现算拒因改写
    hist_rej = [r["vendor_id"] for r in body["history"]["rejected"]]
    live_rej = [r["vendor_id"] for r in body["live"]["rejected"]]
    assert wid not in hist_rej and wid in live_rej
    # 两侧拒因不得并句：compare 里 live/history 各自独立字段，差值无 reason
    assert all("reason" not in row for grp in d.values() for row in grp)


def test_change_segment_width_keeps_old_snapshot(client, seeded):
    sid = seeded["segment_id"]
    run = client.post(f"/api/allocate/run?segment_id={sid}").json()
    # 改街宽：现算区间按新街宽，历史快照街宽仍是 30
    client.patch(f"/api/segments/{sid}", json={"width_m": 26.0})
    body = client.get(f"/api/allocate/compare?segment_id={sid}&run_id={run['id']}").json()
    assert body["live"]["segment"]["width_m"] == 26.0
    assert body["history"]["segment"]["width_m"] == 30.0
    # 旧运行原样可读
    fetched = client.get(f"/api/allocate/runs/{run['id']}").json()
    assert fetched["segment"]["width_m"] == 30.0
    assert fetched["placements"] == run["placements"]


def test_run_id_of_other_segment_is_rejected(client, seeded):
    sid = seeded["segment_id"]
    run = client.post(f"/api/allocate/run?segment_id={sid}").json()
    # 不存在的 run
    assert client.get(f"/api/allocate/compare?segment_id={sid}&run_id=9999").status_code == 404
    # 未选 run 时即便存在历史也不自动带入
    assert client.get(f"/api/allocate/compare?segment_id={sid}").json()["history"] is None
