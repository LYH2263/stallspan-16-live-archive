<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import AllocBand from '../components/AllocBand.vue'

const SEGMENT_ID = 1
const PALETTE = ['#e8a87c', '#85dcb8', '#e27d60', '#c38d9e', '#41b3a3', '#f4a261', '#e76f51', '#a8d0e6']

const vendors = ref<any[]>([])
const segment = ref<any>({ width_m: 0 })
const runs = ref<any[]>([])
const preview = ref<any>({ current: null, history: null, diff: { only_current: [], only_history: [], drift: [] } })
const selectedRunId = ref<number | null>(null)
const loadError = ref('')
const busy = ref(false)

// 改宽表单
const streetWidthInput = ref<number>(0)
const chosenVendorId = ref<number>(0)
const vendorWidthInput = ref<number>(0)

const current = computed(() => preview.value.current)
const history = computed(() => preview.value.history)
const diff = computed(() => preview.value.diff)

// 左右两图共用一把尺：当前街宽。历史快照终点短于现尺时，右端虚线标出。
const scaleWidth = computed(() => segment.value.width_m || current.value?.segment.width_m || 1)
// 颜色按 vendor_id 固定：同一摊主在左图、右图永远同色。
const colorOf = (vendorId: number) => PALETTE[(Number(vendorId) - 1 + PALETTE.length) % PALETTE.length]

async function loadPreview() {
  // 现算与差值同一次请求原子返回；run_id 缺省时后端不给 history、diff 全空。
  const q = selectedRunId.value ? `&run_id=${selectedRunId.value}` : ''
  const data = await api(`/allocate/preview?segment_id=${SEGMENT_ID}${q}`)
  preview.value = data
}

async function loadRuns() {
  runs.value = await api(`/allocate/runs?segment_id=${SEGMENT_ID}`)
}

async function selectRun(id: number) {
  loadError.value = ''
  selectedRunId.value = id
  try {
    await loadPreview()
  } catch (e: any) {
    loadError.value = '历史运行读取失败：' + e.message
  }
}

async function clearHistory() {
  // 主动清空：右侧恢复空白、差值恢复空，不保留任何旧漂移行
  selectedRunId.value = null
  await loadPreview()
}

async function applyStreetWidth() {
  if (!(streetWidthInput.value > 0)) return
  busy.value = true
  try {
    // 先落库新宽度，再按新宽度现算；严禁沿用改前现算快照
    segment.value = await api(`/segments/${SEGMENT_ID}`, {
      method: 'PATCH',
      body: JSON.stringify({ width_m: Number(streetWidthInput.value) }),
    })
    await loadPreview() // 左侧与差值一起刷；右侧仍是落库当时
  } finally {
    busy.value = false
  }
}

async function applyVendorWidth() {
  if (!chosenVendorId.value || !(vendorWidthInput.value > 0)) return
  busy.value = true
  try {
    const updated = await api(`/vendors/${chosenVendorId.value}`, {
      method: 'PATCH',
      body: JSON.stringify({ stall_width_m: Number(vendorWidthInput.value) }),
    })
    const i = vendors.value.findIndex(v => v.id === updated.id)
    if (i >= 0) vendors.value[i] = updated
    await loadPreview() // 按刚改的摊宽重算现算侧，差值同步
  } finally {
    busy.value = false
  }
}

async function archiveRun() {
  busy.value = true
  try {
    const saved = await api(`/allocate/run?segment_id=${SEGMENT_ID}`, { method: 'POST' })
    await loadRuns()
    // 仅在用户主动存档后选中这一版；页面初始加载绝不预选任何历史
    await selectRun(saved.id)
  } finally {
    busy.value = false
  }
}

function pickVendor(id: number) {
  chosenVendorId.value = id
  const v = vendors.value.find(x => x.id === id)
  vendorWidthInput.value = v ? v.stall_width_m : 0
}

const diffTotal = computed(() =>
  (diff.value.only_current?.length || 0)
  + (diff.value.only_history?.length || 0)
  + (diff.value.drift?.length || 0))

onMounted(async () => {
  const segs = await api('/segments')
  segment.value = segs[0]
  streetWidthInput.value = segment.value.width_m
  vendors.value = await api('/vendors')
  if (vendors.value[0]) pickVendor(vendors.value[0].id)
  await loadRuns()
  // 初始不选历史：右侧空白、差值空，绝不偷偷填最近一次运行
  await loadPreview()
})
</script>

<template>
  <div class="alloc-page">
    <h1>分配台 · 现算 / 快照对照</h1>
    <p class="sub">左：按当前街段·挡柱·摊宽现场重算 ｜ 中：左右区间差值 ｜ 右：点选的过往运行落库快照</p>

    <div class="toolbar">
      <label class="tb-field">
        街宽
        <input type="number" step="0.1" min="0.1" v-model.number="streetWidthInput"> m
        <button class="btn" :disabled="busy" @click="applyStreetWidth">改街宽并重算</button>
      </label>
      <label class="tb-field">
        摊宽
        <select v-model.number="chosenVendorId" @change="pickVendor(chosenVendorId)">
          <option v-for="v in vendors" :key="v.id" :value="v.id">{{ v.name }}（#{{ v.id }}）</option>
        </select>
        <input type="number" step="0.1" min="0.1" v-model.number="vendorWidthInput"> m
        <button class="btn" :disabled="busy" @click="applyVendorWidth">改摊宽并重算</button>
      </label>
      <button class="btn btn-archive" :disabled="busy" @click="archiveRun">把当前现算存档为一版</button>
    </div>

    <p v-if="loadError" class="diff-err">{{ loadError }}</p>

    <div class="alloc-grid">
      <!-- 左：现算 -->
      <AllocBand
        title="现算（当前数据）"
        :alloc="current"
        :scale-width="scaleWidth"
        :color-of="colorOf"
        empty-text="现算中…"
        meta="改宽后此处立即按新宽度重算"
      />

      <!-- 中：差值条 -->
      <section class="diff-pane">
        <h2>区间差值</h2>
        <div v-if="!history" class="diff-blank">
          未点选右侧过往运行<br>差值为空（不预填最近一次）
        </div>
        <div v-else-if="diffTotal === 0" class="diff-blank diff-clean">两版区间完全一致</div>
        <div v-else class="diff-groups">
          <div class="diff-group">
            <h3 class="dg-title dg-cur">仅现算有</h3>
            <p v-if="!diff.only_current.length" class="dg-empty">—</p>
            <span v-for="r in diff.only_current" :key="'c' + r.vendor_id" class="dg-chip dg-cur"
                  :title="`现算 ${r.start_m}–${r.end_m} m`">
              #{{ r.vendor_id }} {{ r.vendor_name }}
            </span>
          </div>
          <div class="diff-group">
            <h3 class="dg-title dg-drift">起止漂移</h3>
            <p v-if="!diff.drift.length" class="dg-empty">—</p>
            <div v-for="r in diff.drift" :key="'d' + r.vendor_id" class="dg-row dg-drift"
                  :title="`只按区间位移判定，与空隙不足无关`">
              <span class="dg-chip">#{{ r.vendor_id }} {{ r.vendor_name }}</span>
              <span class="dg-nums">
                历史 {{ r.history_start_m }}–{{ r.history_end_m }} m
                → 现算 {{ r.current_start_m }}–{{ r.current_end_m }} m
                <em>(起 {{ r.delta_start_m >= 0 ? '+' : '' }}{{ r.delta_start_m }} /
                  止 {{ r.delta_end_m >= 0 ? '+' : '' }}{{ r.delta_end_m }} m)</em>
              </span>
            </div>
          </div>
          <div class="diff-group">
            <h3 class="dg-title dg-his">仅历史有</h3>
            <p v-if="!diff.only_history.length" class="dg-empty">—</p>
            <span v-for="r in diff.only_history" :key="'h' + r.vendor_id" class="dg-chip dg-his"
                  :title="`历史 ${r.start_m}–${r.end_m} m`">
              #{{ r.vendor_id }} {{ r.vendor_name }}
            </span>
          </div>
        </div>
      </section>

      <!-- 右：历史快照 -->
      <div class="history-col">
        <AllocBand
          title="历史快照（落库当时）"
          :alloc="history"
          :scale-width="scaleWidth"
          :color-of="colorOf"
          empty-text="未点选过往运行，右侧留白"
          :meta="history ? `#${history.id} · ${history.created_at}` : ''"
        />
        <div class="run-box">
          <div class="run-box-head">
            <h3>过往运行</h3>
            <button v-if="selectedRunId" class="btn btn-mini" @click="clearHistory">清除选择</button>
          </div>
          <p v-if="!runs.length" class="muted run-empty">尚无存档，先在上方「存档为一版」。</p>
          <button
            v-for="r in runs" :key="r.id"
            class="run-item"
            :class="{ active: r.id === selectedRunId }"
            @click="selectRun(r.id)"
          >
            <span class="ri-id">#{{ r.id }}</span>
            <span class="ri-time">{{ r.created_at }}</span>
            <span class="ri-counts">放 {{ r.placed_count }} · 拒 {{ r.rejected_count }} · {{ r.width_m }}m</span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.alloc-page { display: flex; flex-direction: column; }
.toolbar {
  display: flex; flex-wrap: wrap; gap: 0.75rem; align-items: center;
  background: var(--ss-paper); border: 2px solid var(--ss-curb); border-radius: 4px;
  padding: 0.55rem 0.8rem; margin-bottom: 0.7rem;
  box-shadow: 3px 3px 0 rgba(92, 74, 50, 0.2);
}
.tb-field { display: inline-flex; align-items: center; gap: 0.35rem; font-size: 0.82rem; font-weight: 700; }
.tb-field input, .tb-field select {
  font: inherit; padding: 0.3rem 0.4rem; border: 1.5px solid var(--ss-curb);
  border-radius: 3px; background: #fff; width: 110px;
}
.tb-field select { width: auto; }
.btn-archive { margin-left: auto; }
.btn-mini { padding: 0.15rem 0.5rem; font-size: 0.72rem; box-shadow: none; }

.alloc-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 300px minmax(0, 1fr);
  gap: 0.7rem;
  align-items: start;
}

.diff-pane {
  background: var(--ss-paper); border: 2px solid var(--ss-curb); border-radius: 4px;
  padding: 0.7rem 0.75rem; box-shadow: 3px 3px 0 rgba(92,74,50,0.2);
  min-height: 220px;
}
.diff-pane h2 { margin: 0 0 0.5rem; font-size: 0.98rem; font-weight: 800; }
.diff-blank {
  min-height: 150px; display: flex; align-items: center; justify-content: center;
  text-align: center; color: var(--ss-muted); font-size: 0.82rem; line-height: 1.6;
  border: 2px dashed var(--ss-curb); border-radius: 4px; padding: 0.5rem;
}
.diff-clean { color: var(--ss-ok); border-color: var(--ss-ok); }
.diff-err { color: var(--ss-bad); font-size: 0.82rem; margin: 0 0 0.5rem; }
.diff-groups { display: flex; flex-direction: column; gap: 0.65rem; }
.diff-group { display: flex; flex-direction: column; gap: 0.3rem; }
.dg-title { margin: 0; font-size: 0.8rem; font-weight: 800; }
.dg-cur { color: var(--ss-ok); }
.dg-his { color: #3a5f8a; }
.dg-drift { color: var(--ss-accent); }
.dg-empty { margin: 0; font-size: 0.74rem; color: var(--ss-muted); }
.dg-chip {
  display: inline-block; align-self: flex-start;
  font-size: 0.76rem; font-weight: 700; padding: 0.18rem 0.5rem; border-radius: 3px;
  border: 1.5px solid currentColor;
}
.dg-chip.dg-cur { background: rgba(58,122,74,0.14); }
.dg-chip.dg-his { background: rgba(58,95,138,0.12); }
.dg-chip.dg-drift { background: rgba(196,92,38,0.14); }
.dg-row { display: flex; flex-direction: column; gap: 0.15rem; }
.dg-nums { font-size: 0.7rem; color: var(--ss-curb); line-height: 1.45; }
.dg-nums em { color: var(--ss-accent); font-style: normal; }

.history-col { display: flex; flex-direction: column; gap: 0.6rem; }
.run-box {
  background: var(--ss-paper); border: 2px solid var(--ss-curb); border-radius: 4px;
  padding: 0.55rem 0.7rem; box-shadow: 3px 3px 0 rgba(92,74,50,0.2);
}
.run-box-head { display: flex; align-items: center; justify-content: space-between; }
.run-box h3 { margin: 0 0 0.4rem; font-size: 0.85rem; font-weight: 800; }
.run-empty { font-size: 0.75rem; margin: 0.2rem 0; }
.run-item {
  display: flex; gap: 0.5rem; align-items: center; width: 100%; text-align: left;
  background: #fff; border: 1.5px solid var(--ss-curb); border-radius: 3px;
  padding: 0.3rem 0.5rem; margin-bottom: 0.3rem; cursor: pointer; font: inherit;
}
.run-item:hover { border-color: var(--ss-accent); }
.run-item.active { border-color: var(--ss-accent); background: rgba(196,92,38,0.12); box-shadow: inset 2px 0 0 var(--ss-accent); }
.ri-id { font-weight: 800; font-size: 0.78rem; }
.ri-time { font-size: 0.68rem; color: var(--ss-muted); }
.ri-counts { margin-left: auto; font-size: 0.7rem; color: var(--ss-curb); white-space: nowrap; }

@media (max-width: 1100px) {
  .alloc-grid { grid-template-columns: 1fr; }
}
</style>
