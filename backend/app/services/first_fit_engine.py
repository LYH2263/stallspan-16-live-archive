"""1D First-Fit stall placement along a street segment; stalls cannot cross pillars.

现算（live）与历史快照（history）必须来自同一套区间算法：
两者的色块数据都由 ``allocate_first_fit`` / ``result_to_dict`` 产出，
差值 ``diff_allocations`` 只做坐标比对，不引用任何一侧的拒因文案。
"""
from __future__ import annotations
from dataclasses import asdict, dataclass

# 坐标比对容差：引擎输出已四舍五入到 0.001m，1e-6 足以分辨真实漂移
COORD_EPS = 1e-6
SNAPSHOT_VERSION = 1

REJECT_REASON = "无连续空档可放下且不跨越挡柱"


@dataclass
class Placement:
    vendor_id: int
    vendor_name: str
    start_m: float
    end_m: float
    width_m: float


@dataclass
class Rejected:
    vendor_id: int
    vendor_name: str
    width_m: float
    reason: str


@dataclass
class AllocResult:
    placements: list[Placement]
    rejected: list[Rejected]
    free_spans: list[tuple[float, float]]


def free_spans_from_pillars(width_m: float, pillars: list[dict]) -> list[tuple[float, float]]:
    """pillars: position_m, thickness_m — treated as blocked intervals."""
    blocked = []
    for p in pillars:
        half = p.get("thickness_m", 0.4) / 2.0
        lo = max(0.0, p["position_m"] - half)
        hi = min(width_m, p["position_m"] + half)
        if hi > lo:
            blocked.append((lo, hi))
    blocked.sort()
    merged = []
    for lo, hi in blocked:
        if not merged or lo > merged[-1][1]:
            merged.append([lo, hi])
        else:
            merged[-1][1] = max(merged[-1][1], hi)
    spans = []
    cursor = 0.0
    for lo, hi in merged:
        if lo > cursor:
            spans.append((cursor, lo))
        cursor = hi
    if cursor < width_m:
        spans.append((cursor, width_m))
    return [(round(a, 3), round(b, 3)) for a, b in spans if b - a > 1e-6]


def allocate_first_fit(width_m: float, vendors: list[dict], pillars: list[dict]) -> AllocResult:
    """vendors sorted by priority ascending then id; each needs stall_width_m contiguous in one free span (no pillar cross)."""
    spans = free_spans_from_pillars(width_m, pillars)
    # mutable remaining capacity per span
    remain = [[a, b] for a, b in spans]
    ordered = sorted(vendors, key=lambda v: (v.get("priority", 1), v["id"]))
    placements: list[Placement] = []
    rejected: list[Rejected] = []
    for v in ordered:
        need = float(v["stall_width_m"])
        placed = False
        for span in remain:
            avail = span[1] - span[0]
            if avail + 1e-9 >= need:
                start = span[0]
                end = start + need
                placements.append(Placement(v["id"], v["name"], round(start, 3), round(end, 3), need))
                span[0] = end
                placed = True
                break
        if not placed:
            rejected.append(Rejected(v["id"], v["name"], need, REJECT_REASON))
    free = [(round(a, 3), round(b, 3)) for a, b in remain if b - a > 1e-6]
    return AllocResult(placements, rejected, free)


def result_to_dict(r: AllocResult) -> dict:
    return {
        "placements": [asdict(p) for p in r.placements],
        "rejected": [asdict(x) for x in r.rejected],
        "free_spans": [{"start_m": a, "end_m": b} for a, b in r.free_spans],
    }


def make_snapshot(segment: dict, pillars: list[dict], result: dict) -> dict:
    """统一快照外壳：现算响应与落库 JSON 同形，左右两图只能吃这个结构。

    pillars 需带 label（挡柱文案随快照固化）；segment 带 width_m（区间口径随快照固化）。
    """
    return {
        "snapshot_version": SNAPSHOT_VERSION,
        "segment": dict(segment),
        "pillars": [dict(p) for p in pillars],
        "placements": result["placements"],
        "rejected": result["rejected"],
        "free_spans": result["free_spans"],
    }


def _placement_index(result: dict) -> dict[int, dict]:
    return {p["vendor_id"]: p for p in result.get("placements", [])}


def diff_allocations(live: dict | None, history: dict | None) -> dict:
    """比对现算与历史快照，返回仅现算有 / 仅历史有 / 起止漂移三类摊主。

    - 只比对 placements 坐标；rejected 不参与、不并句、不换算成任何差值文案。
    - 同一摊主两侧均放置成功才可能进 drifted；坐标一致则三类皆不入。
    - 任一侧缺失（未选历史）时差值为空，绝不半成功写出半行。
    """
    empty = {"only_live": [], "only_history": [], "drifted": []}
    if not live or not history:
        return empty

    live_map = _placement_index(live)
    hist_map = _placement_index(history)
    live_ids, hist_ids = set(live_map), set(hist_map)

    only_live = [_vendor_ref(live_map[v]) for v in sorted(live_ids - hist_ids)]
    only_history = [_vendor_ref(hist_map[v]) for v in sorted(hist_ids - live_ids)]

    drifted = []
    for vid in sorted(live_ids & hist_ids):
        lp, hp = live_map[vid], hist_map[vid]
        ds = lp["start_m"] - hp["start_m"]
        de = lp["end_m"] - hp["end_m"]
        if abs(ds) > COORD_EPS or abs(de) > COORD_EPS:
            drifted.append({
                "vendor_id": vid,
                "vendor_name": lp["vendor_name"],
                "live_start_m": lp["start_m"],
                "live_end_m": lp["end_m"],
                "live_width_m": lp["width_m"],
                "history_start_m": hp["start_m"],
                "history_end_m": hp["end_m"],
                "history_width_m": hp["width_m"],
                "start_delta_m": round(ds, 3),
                "end_delta_m": round(de, 3),
            })

    return {"only_live": only_live, "only_history": only_history, "drifted": drifted}


def _vendor_ref(p: dict) -> dict:
    return {
        "vendor_id": p["vendor_id"],
        "vendor_name": p["vendor_name"],
        "start_m": p["start_m"],
        "end_m": p["end_m"],
        "width_m": p["width_m"],
    }
