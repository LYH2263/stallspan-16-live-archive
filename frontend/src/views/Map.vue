<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import StallBand from '../components/StallBand.vue'

const SEG_ID = 1
const palette = ['#e8a87c', '#85dcb8', '#e27d60', '#c38d9e', '#41b3a3', '#f4a261', '#e9c46a', '#a8dadc']

const vendors = ref<any[]>([])
const runs = ref<any[]>([])
const compare = ref<any>(null)
const selectedRunId = ref<number | null>(null)
const segmentWidth = ref<number | null>(null)
const widthDraft = ref<Record<number, string>>({})
const segWidthDraft = ref('')
const errMsg = ref('')
const busy = ref(false)

// 同一摊主左右两图颜色一致：按摊主在队列中的固定序号取色，与放置顺序无关
function colorFor(vendorId: number): string {
  const idx = vendors.value.findIndex(v => v.id === vendorId)
  return palette[(idx >= 0 ? idx : vendorId - 1) % palette.length]
}

// 防旧响应覆盖新状态：改宽后返回的 compare 必须是最后一次请求
let reqSeq = 0
async function refresh() {
  const seq = ++reqSeq
  const q = selectedRunId.value != null ? `&run_id=${selectedRunId.value}` : ''
  const data = await api(`/allocate/compare?segment_id=${SEG_ID}${q}`)
  if (seq === reqSeq) compare.value = data
}

async function loadRuns(keepSelection = true) {
  runs.value = await api('/allocate/runs?segment_id=' + SEG_ID)
  if (!keepSelection) selectedRunId.value = null
}

async function applyVendorWidth(v: any) {
  errMsg.value = ''
  const raw = (widthDraft.value[v.id] ?? '').trim()
  if (!raw) return
  const w = Number(raw)
  if (!(w > 0)) { errMsg.value = `#${v.id} ${v.name}：摊宽必须为正数`; return }
  busy.value = true
  try {
    // 先 PATCH 落库，再按刚改的宽度重算现算侧与差值；历史侧请求不带新宽度
    await api(`/vendors/${v.id}`, { method: 'PATCH', body: JSON.stringify({ stall_width_m: w }) })
    vendors.value = await api('/vendors')
    await refresh()
    widthDraft.value[v.id] = ''
  } catch (e: any) {
    errMsg.value = '改摊宽失败：' + e.message
  } finally {
    busy.value = false
  }
}

async function applySegmentWidth() {
  errMsg.value = ''
  const w = Number(segWidthDraft.value)
  if (!(w > 0)) { errMsg.value = '街宽必须为正数'; return }
  busy.value = true
  try {
    await api(`/segments/${SEG_ID}`, { method: 'PATCH', body: JSON.stringify({ width_m: w }) })
    segmentWidth.value = w
    await refresh() // 只刷现算+差值；右侧仍取自落库快照，不受影响
    segWidthDraft.value = ''
  } catch (e: any) {
    errMsg.value = '改街宽失败：' + e.message
  } finally {
    busy.value = false
  }
}

async function selectRun(id: number) {
  selectedRunId.value = id
  await refresh()
}
async function clearHistory() {
  // 未选历史：右侧空白、差值空，绝不默认带入最近一次运行
  selectedRunId.value = null
  await refresh()
}
async function saveRun() {
  errMsg.value = ''
  busy.value = true
  try {
    const run = await api(`/allocate/run?segment_id=${SEG_ID}`, { method: 'POST' })
    await loadRuns()
    selectedRunId.value = run.id
    await refresh()
  } catch (e: any) {
    errMsg.value = '固化运行失败：' + e.message
  } finally {
    busy.value = false
  }
}

function fmt(n: number) {
  return Number(n).toFixed(2).replace(/\.?0+$/, '')
}
function fmtTime(iso: string) {
  const d = new Date(iso)
  return isNaN(d.getTime()) ? iso : d.toLocaleString('zh-CN', { hour12: false })
}
function deltaText(d: number) {
  return (d > 0 ? '+' : '') + fmt(d)
}

const diff = computed(() => compare.value?.diff ?? null)
const hasHistory = computed(() => !!compare.value?.history)

onMounted(async () => {
  vendors.value = await api('/vendors')
  const segs = await api('/segments')
  segmentWidth.value = segs[0]?.width_m ?? null
  await loadRuns(false)
  await refresh() // 初始不选历史：右空白、差值空
})
</script>

<template>
  <div class="ss-street-wrap ss-compare-page">
    <h1>街段分配图 · 现算对比历史快照</h1>
    <p class="sub">左＝当前街段·挡柱·摊主现算；右＝所选过往运行落库当时色块；中＝同一套区间算法算出的差值。改宽度只动左与中，右永不回写。</p>

    <div class="ss-toolbar">
      <label>街段现宽 {{ segmentWidth ?? '—' }} m</label>
      <input v-model="segWidthDraft" type="number" min="0.1" step="0.5" placeholder="新街宽" @keyup.enter="applySegmentWidth">
      <button class="ss-mini-btn" :disabled="busy" @click="applySegmentWidth">改街宽并重算</button>
      <span style="flex:1"></span>
      <button class="btn" :disabled="busy" @click="saveRun">把当前现算固化为历史运行</button>
    </div>
    <p v-if="errMsg" class="ss-err">{{ errMsg }}</p>

    <div class="ss-compare-grid" v-if="compare">
      <!-- ============ 左：现算 ============ -->
      <section class="ss-col">
        <div class="ss-col-head"><span class="tag tag-live">现算</span> 当前宽度即时重算 · 不落库</div>
        <StallBand :snapshot="compare.live" :color-for="colorFor" empty-text="现算不可用" />
        <div class="card">
          <p class="ss-side-label">现算放不下（现算拒因，仅属左侧，不并入历史）：</p>
          <ul v-if="compare.live.rejected.length" class="ss-reject-list">
            <li v-for="r in compare.live.rejected" :key="'lr' + r.vendor_id">
              #{{ r.vendor_id }} {{ r.vendor_name }} · 需 {{ fmt(r.width_m) }} m — {{ r.reason }}
            </li>
          </ul>
          <p v-else class="ss-diff-empty">全部放下</p>
        </div>
        <div class="card ss-width-editor">
          <p class="ss-side-label">改摊宽（PATCH 后左图与差值按新宽度重算）：</p>
          <table>
            <thead><tr><th>#</th><th>摊主</th><th>现宽</th><th>改为</th><th></th></tr></thead>
            <tbody>
              <tr v-for="v in vendors" :key="v.id">
                <td>{{ v.id }}</td>
                <td>{{ v.name }}</td>
                <td>{{ fmt(v.stall_width_m) }}</td>
                <td><input v-model="widthDraft[v.id]" type="number" min="0.1" step="0.5"></td>
                <td><button class="ss-mini-btn" :disabled="busy" @click="applyVendorWidth(v)">改并重算</button></td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- ============ 中：差值条 ============ -->
      <section class="ss-col">
        <div class="ss-col-head"><span class="tag tag-diff">差值</span> 摊主号进出图 / 起止漂移</div>
        <div v-if="!hasHistory" class="ss-diff-bar-empty">
          右侧尚未选择历史运行：差值为空，不写入任何行，也不默认取最近一次运行。
        </div>
        <div v-else class="ss-diff-groups">
          <div class="ss-diff-group">
            <h3>仅现算有 <span>{{ diff.only_live.length }}</span></h3>
            <ul v-if="diff.only_live.length">
              <li v-for="r in diff.only_live" :key="'ol' + r.vendor_id">
                #{{ r.vendor_id }} {{ r.vendor_name }}
                <span class="coords">现算 {{ fmt(r.start_m) }}–{{ fmt(r.end_m) }} m · 宽 {{ fmt(r.width_m) }}</span>
              </li>
            </ul>
            <p v-else class="ss-diff-empty">无</p>
          </div>
          <div class="ss-diff-group">
            <h3>仅历史有 <span>{{ diff.only_history.length }}</span></h3>
            <ul v-if="diff.only_history.length">
              <li v-for="r in diff.only_history" :key="'oh' + r.vendor_id">
                #{{ r.vendor_id }} {{ r.vendor_name }}
                <span class="coords">历史 {{ fmt(r.start_m) }}–{{ fmt(r.end_m) }} m · 宽 {{ fmt(r.width_m) }}</span>
              </li>
            </ul>
            <p v-else class="ss-diff-empty">无</p>
          </div>
          <div class="ss-diff-group">
            <h3>起止漂移 <span>{{ diff.drifted.length }}</span></h3>
            <ul v-if="diff.drifted.length">
              <li v-for="r in diff.drifted" :key="'dr' + r.vendor_id">
                #{{ r.vendor_id }} {{ r.vendor_name }}
                <span class="coords">
                  现算 {{ fmt(r.live_start_m) }}–{{ fmt(r.live_end_m) }} m（宽 {{ fmt(r.live_width_m) }}）<br>
                  历史 {{ fmt(r.history_start_m) }}–{{ fmt(r.history_end_m) }} m（宽 {{ fmt(r.history_width_m) }}）<br>
                  Δ起 {{ deltaText(r.start_delta_m) }} m · Δ止 {{ deltaText(r.end_delta_m) }} m
                </span>
              </li>
            </ul>
            <p v-else class="ss-diff-empty">无</p>
          </div>
        </div>
      </section>

      <!-- ============ 右：历史快照 ============ -->
      <section class="ss-col">
        <div class="ss-col-head"><span class="tag tag-hist">历史</span> 过往运行（点开看落库当时）</div>
        <div class="card" style="margin-bottom:0">
          <div v-if="runs.length" class="ss-run-list">
            <button
              v-for="r in runs" :key="r.id"
              class="ss-run-item"
              :class="{ active: selectedRunId === r.id }"
              @click="selectRun(r.id)"
            >
              <strong>#{{ r.id }} · {{ fmtTime(r.created_at) }}</strong>
              <span class="meta">{{ r.segment?.name }} · 街宽 {{ r.segment?.width_m }} m · 放下 {{ r.placed_count }} · 放不下 {{ r.rejected_count }}</span>
            </button>
          </div>
          <p v-else class="ss-diff-empty">尚无历史运行，先点上方「固化为历史运行」。</p>
          <button v-if="selectedRunId != null" class="ss-mini-btn" style="margin-top:0.4rem" @click="clearHistory">取消选择（右清空·差值空）</button>
        </div>
        <StallBand :snapshot="compare.history" :color-for="colorFor" empty-text="未选择历史运行：右侧留空，不取最近一次" />
        <div class="card" v-if="hasHistory">
          <p class="ss-side-label">历史运行 #{{ compare.history.id }} 放不下（落库当时拒因原文，不被现算改写、不并句）：</p>
          <ul v-if="compare.history.rejected.length" class="ss-reject-list">
            <li v-for="r in compare.history.rejected" :key="'hr' + r.vendor_id">
              #{{ r.vendor_id }} {{ r.vendor_name }} · 需 {{ fmt(r.width_m) }} m — {{ r.reason }}
            </li>
          </ul>
          <p v-else class="ss-diff-empty">该次运行全部放下</p>
        </div>
      </section>
    </div>
  </div>
</template>
