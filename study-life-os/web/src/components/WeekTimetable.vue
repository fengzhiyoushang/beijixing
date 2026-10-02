<script setup>
import { computed } from 'vue'

const props = defineProps({
  days: { type: Array, required: true }, // [{weekday, classes:[{course,start_time,end_time,location,color,...}]}]
})
const emit = defineEmits(['pick'])

const START = 7 * 60   // 07:00
const END = 23 * 60    // 23:00
const PX = 1.0         // px / minute
const WEEK = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
const todayWd = new Date().getDay() === 0 ? 7 : new Date().getDay()

const toMin = (hm) => {
  const [h, m] = String(hm).split(':').map(Number)
  return h * 60 + (m || 0)
}
const hours = computed(() => {
  const arr = []
  for (let h = 7; h <= 22; h++) arr.push(h)
  return arr
})
const topOf = (t) => (toMin(t) - START) * PX
const blockStyle = (c) => {
  const color = c.color || '#00e5a0'
  const top = topOf(c.start_time)
  const height = Math.max((toMin(c.end_time) - toMin(c.start_time)) * PX - 2, 26)
  return {
    top: `${top}px`,
    height: `${height}px`,
    background: `${color}1c`,
    border: `1px solid ${color}66`,
    borderLeft: `3px solid ${color}`,
    color: '#d9f6ec',
  }
}
</script>

<template>
  <div class="tt">
    <div class="tt-head">
      <div class="corner mono">H\M</div>
      <div
        v-for="(w, i) in WEEK"
        :key="w"
        class="wd mono"
        :class="{ today: i + 1 === todayWd }"
      >{{ w }}<span v-if="i + 1 === todayWd" class="dot">●</span></div>
    </div>
    <div class="tt-body">
      <div class="time-axis mono">
        <div v-for="h in hours" :key="h" class="tick" :style="{ top: `${(h * 60 - START) * PX}px` }">
          {{ String(h).padStart(2, '0') }}:00
        </div>
      </div>
      <div class="grid" :style="{ height: `${(END - START) * PX}px` }">
        <div
          v-for="(day, di) in days"
          :key="di"
          class="col"
          :class="{ today: day.weekday === todayWd }"
          :style="{
            backgroundImage: `repeating-linear-gradient(to bottom, rgba(56,189,248,.08) 0 1px, transparent 1px ${60 * PX}px)`,
          }"
        >
          <div
            v-for="c in day.classes"
            :key="c.course_id + c.start_time + c.weekday"
            class="block"
            :style="blockStyle(c)"
            :class="{ past: c.class_status === 'past' }"
            @click="emit('pick', c)"
          >
            <div class="b-name">{{ c.course }}</div>
            <div class="b-meta">{{ c.start_time }}·{{ c.location || '待定' }}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tt { border: 1px solid rgba(56, 189, 248, 0.15); border-radius: 10px; overflow: hidden; background: rgba(10, 16, 30, 0.75); }
.tt-head { display: grid; grid-template-columns: 52px repeat(7, 1fr); border-bottom: 1px solid rgba(56, 189, 248, 0.15); }
.corner, .wd { padding: 8px 4px; text-align: center; font-size: 12px; color: #7d93b2; }
.wd.today { color: #00e5a0; text-shadow: 0 0 8px rgba(0, 229, 160, 0.6); }
.dot { font-size: 8px; margin-left: 3px; }
.tt-body { display: flex; overflow: auto; max-height: 640px; }
.time-axis { position: relative; width: 52px; flex: none; }
.tick { position: absolute; top: 0; right: 8px; transform: translateY(-6px); font-size: 10px; color: #4a617f; }
.grid { flex: 1; display: grid; grid-template-columns: repeat(7, 1fr); }
.col { position: relative; border-left: 1px solid rgba(56, 189, 248, 0.08); min-height: 100%; }
.col.today { background: rgba(0, 229, 160, 0.035); }
.block { position: absolute; left: 3px; right: 3px; border-radius: 6px; padding: 3px 5px; overflow: hidden; cursor: pointer; transition: filter 0.12s; }
.block:hover { filter: brightness(1.35); }
.block.past { opacity: 0.42; }
.b-name { font-size: 11px; font-weight: 600; line-height: 1.3; }
.b-meta { font-size: 10px; color: #8fb4d6; margin-top: 1px; }
</style>
