"""1D First-Fit stall placement along a street segment; stalls cannot cross pillars.

区间口径（唯一来源）：
- 现算图、历史快照图、差值条都只认本模块产出的 start_m / end_m / width_m 区间。
- 历史图读的是落库当时用同一算法算出的区间；差值不得拿历史边界去重算现算，
  也不得引用任何一方的 rejected.reason —— 拒因只属于各自那一次运行，不并句。
- 漂移（起止移动）与空隙不足（放不下）是两回事：后者只在 rejected 里，
  前者只在 diff_allocations 里按区间位移判定，不得互相冒充。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

# 区间比对容差：左右两侧 start/end 差异不超过该值即视为区间未漂移。
INTERVAL_EPS = 1e-6


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
            rejected.append(Rejected(v["id"], v["name"], need, "无连续空档可放下且不跨越挡柱"))
    free = [(round(a, 3), round(b, 3)) for a, b in remain if b - a > 1e-6]
    return AllocResult(placements, rejected, free)


def result_to_dict(r: AllocResult) -> dict:
    return {
        "placements": [asdict(p) for p in r.placements],
        "rejected": [asdict(x) for x in r.rejected],
        "free_spans": [{"start_m": a, "end_m": b} for a, b in r.free_spans],
    }


def _placement_index(placements: list[dict]) -> dict[int, dict]:
    return {int(p["vendor_id"]): p for p in placements}


def diff_allocations(current: dict, history: dict | None) -> dict:
    """比对两次分配（同一套区间口径，均为 result_to_dict 的产物）。

    只按 vendor_id + start_m/end_m 区间判定三类差值：
    - only_current : 仅现算放下（历史里该摊主不存在于 placements）
    - only_history : 仅历史放下（现算里该摊主不存在于 placements）
    - drift        : 两侧都放下，但起止发生漂移（位移超过 INTERVAL_EPS）

    绝不读取任何一方的 rejected / reason：空隙不足不进差值，漂移也不冒充空隙不足。
    history 为 None（未选历史运行）时三类全空 —— 不允许偷偷填最近一次运行。
    """
    empty: dict = {"only_current": [], "only_history": [], "drift": []}
    if history is None:
        return empty

    cur_map = _placement_index(current.get("placements", []))
    his_map = _placement_index(history.get("placements", []))

    only_current = [
        {"vendor_id": vid, "vendor_name": p["vendor_name"],
         "start_m": p["start_m"], "end_m": p["end_m"], "width_m": p["width_m"]}
        for vid, p in cur_map.items() if vid not in his_map
    ]
    only_history = [
        {"vendor_id": vid, "vendor_name": p["vendor_name"],
         "start_m": p["start_m"], "end_m": p["end_m"], "width_m": p["width_m"]}
        for vid, p in his_map.items() if vid not in cur_map
    ]
    drift = []
    for vid, cp in cur_map.items():
        hp = his_map.get(vid)
        if hp is None:
            continue
        d_start = round(float(cp["start_m"]) - float(hp["start_m"]), 3)
        d_end = round(float(cp["end_m"]) - float(hp["end_m"]), 3)
        if abs(d_start) > INTERVAL_EPS or abs(d_end) > INTERVAL_EPS:
            drift.append({
                "vendor_id": vid,
                "vendor_name": cp["vendor_name"],
                "current_start_m": cp["start_m"], "current_end_m": cp["end_m"],
                "history_start_m": hp["start_m"], "history_end_m": hp["end_m"],
                "delta_start_m": d_start, "delta_end_m": d_end,
                "current_width_m": cp["width_m"], "history_width_m": hp["width_m"],
            })

    def _key(row: dict) -> tuple:
        return (row["vendor_id"],)

    return {
        "only_current": sorted(only_current, key=_key),
        "only_history": sorted(only_history, key=_key),
        "drift": sorted(drift, key=_key),
    }
