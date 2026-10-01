<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
const rows = ref<any[] | null>(null)
const runId = ref<number | null>(null)
onMounted(async () => {
  const data = await api('/allocate/latest?segment_id=1')
  rows.value = data ? (data.rejected || []) : []
  runId.value = data ? data.id : null
})
</script>
<template>
  <h1>放不下</h1>
  <p class="sub">最近一次落库运行中，无法在连续空档内安置且不跨越挡柱的摊位</p>
  <div class="card">
    <table v-if="rows && rows.length">
      <thead><tr><th>摊主</th><th>需求宽度</th><th>原因</th></tr></thead>
      <tbody>
        <tr v-for="r in rows" :key="r.vendor_id">
          <td>{{ r.vendor_name }}</td><td>{{ r.width_m }}</td><td>{{ r.reason }}</td>
        </tr>
      </tbody>
    </table>
    <p v-else-if="rows" class="muted">最近一次运行全部放下（或尚无落库运行，请先到分配带固化一版）</p>
  </div>
</template>
