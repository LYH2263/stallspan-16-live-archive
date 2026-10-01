<script setup lang="ts">
// 左右两图唯一的渲染组件：只吃一个快照，所有坐标按该快照自身街宽换算。
// 现算图只喂 live，历史图只喂 history —— 组件层面就杜绝「拿历史边界画现算」。
import { computed } from 'vue'

interface Snapshot {
  segment: { id: number; name: string; width_m: number }
  pillars: Array<{ position_m: number; thickness_m: number; label?: string }>
  placements: Array<{ vendor_id: number; vendor_name: string; start_m: number; end_m: number; width_m: number }>
}
const props = defineProps<{
  snapshot: Snapshot | null
  colorFor: (vendorId: number) => string
  emptyText: string
}>()

const FONT_PX = 12
const cells = computed(() => {
  const s = props.snapshot
  if (!s) return []
  const W = s.segment.width_m
  const pct = (m: number) => Math.min(100, Math.max(0, (m / W) * 100))
  const out: any[] = []
  for (const p of s.pillars || []) {
    const lo = Math.max(0, p.position_m - p.thickness_m / 2)
    const hi = Math.min(W, p.position_m + p.thickness_m / 2)
    out.push({
      kind: 'pillar',
      left: pct(lo),
      width: pct(hi) - pct(lo),
      label: p.label || '挡柱',
    })
  }
  for (const p of s.placements || []) {
    out.push({
      kind: 'stall',
      vendorId: p.vendor_id,
      left: pct(p.start_m),
      width: pct(p.end_m) - pct(p.start_m),
      label: p.vendor_name,
      title: `${p.vendor_name}（#${p.vendor_id}） ${p.start_m}–${p.end_m} m · 宽 ${p.width_m}`,
    })
  }
  return out
})

// 太窄的色块只保留底色与 title，不硬塞文字
function showLabel(widthPct: number) {
  return widthPct >= 4
}
</script>

<template>
  <div v-if="snapshot" class="ss-band-snapshot">
    <div class="ss-band-ruler">
      <span>0 m</span>
      <span>{{ snapshot.segment.name }} · 街宽 {{ snapshot.segment.width_m }} m</span>
      <span>{{ snapshot.segment.width_m }} m</span>
    </div>
    <div class="ss-street-band ss-band-compare">
      <div class="ss-track">
        <div
          v-for="(c, i) in cells"
          :key="c.kind + '-' + i"
          class="ss-band-cell"
          :class="{ 'ss-pillar': c.kind === 'pillar' }"
          :style="{
            left: c.left + '%',
            width: c.width + '%',
            fontSize: FONT_PX + 'px',
            background: c.kind === 'pillar' ? undefined : colorFor(c.vendorId),
          }"
          :title="c.title"
        ><span v-if="c.kind === 'pillar' || showLabel(c.width)">{{ c.label }}</span></div>
      </div>
    </div>
  </div>
  <div v-else class="ss-band-empty">{{ emptyText }}</div>
</template>
