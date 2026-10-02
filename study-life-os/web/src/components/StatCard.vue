<script setup>
defineProps({
  label: { type: String, required: true },
  value: { type: [String, Number], default: '-' },
  sub: { type: String, default: '' },
  color: { type: String, default: '#00e5a0' },
})
</script>

<template>
  <n-card size="small" class="stat-card" :style="{ '--accent': color }">
    <div class="k mono">{{ label }}</div>
    <div class="v stat-num" :style="{ textShadow: `0 0 12px ${color}55` }">{{ value }}</div>
    <div v-if="sub" class="s">{{ sub }}</div>
  </n-card>
</template>

<style scoped>
.stat-card { border-left: 3px solid var(--accent); transition: transform 0.15s; }
.stat-card:hover { transform: translateY(-2px); }
.k { font-size: 11px; color: #5b7290; letter-spacing: 1px; margin-bottom: 6px; }
.s { font-size: 11px; color: #7d93b2; margin-top: 4px; }
</style>
