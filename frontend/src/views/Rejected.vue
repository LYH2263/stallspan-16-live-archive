<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
const rows = ref<any[]>([])
onMounted(async () => {
  // 「放不下」属于当前现算这一次运行的拒因；历史拒因不并到这里。
  const data = await api('/allocate/preview?segment_id=1')
  rows.value = data.current?.rejected || []
})
</script>
<template>
  <h1>放不下</h1>
  <p class="sub">当前现算中无法在连续空档内安置且不跨越挡柱的摊位（仅现算侧拒因）</p>
  <div class="card">
    <table>
      <thead><tr><th>摊主</th><th>需求宽度</th><th>原因</th></tr></thead>
      <tbody>
        <tr v-for="r in rows" :key="r.vendor_id">
          <td>{{ r.vendor_name }}</td><td>{{ r.width_m }}</td><td>{{ r.reason }}</td>
        </tr>
      </tbody>
    </table>
    <p v-if="!rows.length" class="muted">全部放下</p>
  </div>
</template>
