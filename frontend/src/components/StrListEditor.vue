<template>
  <div>
    <div v-for="(item, i) in modelValue" :key="i" class="row" style="gap:6px; margin-bottom:4px">
      <input :value="item" @input="upd(i, $event.target.value)" :placeholder="ph" />
      <button class="mini" type="button" @click="rm(i)">✕</button>
    </div>
    <button class="mini" type="button" @click="add">＋ {{ label || '新增' }}</button>
  </div>
</template>

<script setup>
const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  ph: String,
  label: String,
})
const emit = defineEmits(['update:modelValue'])
function upd(i, v) { const a = [...props.modelValue]; a[i] = v; emit('update:modelValue', a) }
function rm(i) { const a = [...props.modelValue]; a.splice(i, 1); emit('update:modelValue', a) }
function add() { emit('update:modelValue', [...props.modelValue, '']) }
</script>
