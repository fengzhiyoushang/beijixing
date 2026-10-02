<script setup>
defineProps({
  tone: { type: String, default: 'green' }, // green | yellow | red | blue | gray
  label: { type: String, default: '' },
  glow: { type: Boolean, default: true },
})
</script>

<template>
  <span class="status">
    <span class="dot" :class="`dot-${tone}`" :style="glow ? '' : 'box-shadow:none'" />
    <span v-if="label" class="txt mono">{{ label }}</span>
  </span>
</template>

<style scoped>
.status { display: inline-flex; align-items: center; gap: 6px; }
.txt { font-size: 11px; color: var(--text-2); }
</style>
