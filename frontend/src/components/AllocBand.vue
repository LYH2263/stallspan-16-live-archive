<script setup lang="ts">
// 左（现算）右（历史）两图共用本组件、共用同一把米尺（scaleWidth）。
// 区间只来自后端 allocate_first_fit 的 start_m/end_m：本组件不自行推算任何边界。
import { computed } from 'vue'

const props = defineProps<{
  title: string
  alloc: any | null
  scaleWidth: number
  colorOf: (vendorId: number) => string
  emptyText: string
  meta?: string
}>()

const cells = computed(() => {
  if (!props.alloc) return []
  const scale = props.scaleWidth || props.alloc.segment.width_m
  const out: any[] = []
  for (const p of props.alloc.pillars || []) {
    const lo = Math.max(0, p.position_m - p.thickness_m / 2)
    const hi = Math.min(scale, p.position_m + p.thickness_m / 2)
    out.push({
      type: 'pillar',
      leftPct: (lo / scale) * 100,
      widthPct: Math.max(((hi - lo) / scale) * 100, 0.4),
      label: p.label || '挡柱',
    })
  }
  for (const p of props.alloc.placements || []) {
    out.push({
      type: 'stall',
      vendorId: p.vendor_id,
      leftPct: (p.start_m / scale) * 100,
      widthPct: Math.max((p.width_m / scale) * 100, 1.2),
      label: p.vendor_name,
      range: `${p.start_m}–${p.end_m} m`,
      color: props.colorOf(p.vendor_id),
    })
  }
  return out
})

// 该次运行自己的街段终点（街宽被改后，历史终点可能短于当前米尺）。
const endPct = computed(() => {
  if (!props.alloc) return 0
  const scale = props.scaleWidth || props.alloc.segment.width_m
  return (props.alloc.segment.width_m / scale) * 100
})
</script>

<template>
  <section class="alloc-pane">
    <header class="pane-head">
      <h2>{{ title }}</h2>
      <span v-if="meta" class="pane-meta">{{ meta }}</span>
    </header>

    <div v-if="!alloc" class="pane-blank">{{ emptyText }}</div>

    <template v-else>
      <div class="pane-ruler">
        <span>0 m</span>
        <span>{{ alloc.segment.name }} · 街宽 {{ alloc.segment.width_m }} m</span>
        <span>{{ Math.round(scaleWidth) }} m 尺</span>
      </div>
      <div class="pane-band">
        <div class="pane-track">
          <div
            v-for="(c, i) in cells"
            :key="c.type + '-' + i"
            class="pane-cell"
            :class="{ 'is-pillar': c.type === 'pillar' }"
            :style="{
              left: c.leftPct + '%',
              width: c.widthPct + '%',
              background: c.type === 'stall' ? c.color : undefined,
            }"
            :title="c.type === 'stall' ? `${c.label} ${c.range}` : c.label"
          >{{ c.label }}</div>
          <div class="pane-endline" :style="{ left: endPct + '%' }"></div>
        </div>
      </div>

      <div class="pane-placed">
        <span class="cnt">放下 {{ (alloc.placements || []).length }}</span>
        <span class="cnt cnt-bad">放不下 {{ (alloc.rejected || []).length }}</span>
      </div>

      <!-- 拒因只读本侧这一次运行，左右各自成句，绝不并句 -->
      <ul v-if="(alloc.rejected || []).length" class="pane-reject">
        <li v-for="r in alloc.rejected" :key="r.vendor_id">
          <span class="rj-name">{{ r.vendor_name }}</span>
          <span class="rj-reason">{{ r.reason }}</span>
        </li>
      </ul>
    </template>
  </section>
</template>

<style scoped>
.alloc-pane {
  background: var(--ss-paper);
  border: 2px solid var(--ss-curb);
  border-radius: 4px;
  padding: 0.7rem 0.8rem;
  box-shadow: 3px 3px 0 rgba(92, 74, 50, 0.2);
  display: flex;
  flex-direction: column;
  min-height: 220px;
}
.pane-head { display: flex; align-items: baseline; justify-content: space-between; gap: 0.5rem; }
.pane-head h2 { margin: 0; font-size: 0.98rem; font-weight: 800; }
.pane-meta { font-size: 0.72rem; color: var(--ss-muted); }
.pane-blank {
  flex: 1;
  display: flex; align-items: center; justify-content: center;
  color: var(--ss-muted); font-size: 0.85rem;
  border: 2px dashed var(--ss-curb); border-radius: 4px;
  margin: 0.5rem 0; min-height: 150px; text-align: center; padding: 0 1rem;
}
.pane-ruler {
  display: flex; justify-content: space-between;
  font-size: 0.68rem; color: var(--ss-muted); padding: 0.35rem 0.1rem 0;
}
.pane-band {
  position: relative;
  height: 120px;
  margin: 0.3rem 0;
  background: linear-gradient(180deg, #6b5a42 0%, #4a3d2c 18%, #3a3126 50%, #4a3d2c 82%, #6b5a42 100%);
  border-top: 5px solid #8a7654;
  border-bottom: 5px solid #8a7654;
  box-shadow: inset 0 0 30px rgba(0, 0, 0, 0.35);
  overflow: hidden;
}
.pane-track { position: absolute; inset: 0; }
.pane-cell {
  position: absolute; top: 0; bottom: 0;
  display: flex; align-items: center; justify-content: center;
  font-size: 0.74rem; font-weight: 700; color: #1a140e;
  border-right: 1px solid rgba(255, 255, 255, 0.18);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  padding: 0 0.2rem;
}
.pane-cell.is-pillar {
  background: repeating-linear-gradient(180deg, var(--ss-pillar) 0 8px, #2a2824 8px 16px);
  color: #c8c0b4;
  writing-mode: vertical-rl; letter-spacing: 0.12em;
  box-shadow: inset 0 0 0 2px #1a1814;
}
.pane-endline {
  position: absolute; top: -2px; bottom: -2px; width: 2px;
  background: repeating-linear-gradient(180deg, #f3ead4 0 5px, transparent 5px 10px);
  opacity: 0.7;
}
.pane-placed { display: flex; gap: 0.5rem; font-size: 0.74rem; }
.cnt { padding: 0.1rem 0.45rem; border-radius: 3px; background: rgba(58,122,74,0.16); color: var(--ss-ok); font-weight: 700; }
.cnt-bad { background: rgba(163,58,44,0.16); color: var(--ss-bad); }
.pane-reject { list-style: none; margin: 0.45rem 0 0; padding: 0.4rem 0.5rem; border-top: 1px dashed var(--ss-curb); }
.pane-reject li { display: flex; gap: 0.5rem; font-size: 0.74rem; padding: 0.12rem 0; }
.rj-name { font-weight: 700; flex: 0 0 auto; }
.rj-reason { color: var(--ss-bad); }
</style>
