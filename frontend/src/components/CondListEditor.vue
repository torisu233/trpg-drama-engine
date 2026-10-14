<template>
  <div>
    <div v-for="(c, i) in modelValue" :key="i" class="cond">
      <input :value="c.content" @input="upd(i, 'content', $event.target.value)" placeholder="Content (the fact)" />
      <div class="row" style="gap:6px; margin-top:4px">
        <input :value="c.gates" @input="upd(i, 'gates', $event.target.value)" placeholder="Gates (how it constrains what follows)" />
        <select :value="c.visibility || 'public'" @change="upd(i, 'visibility', $event.target.value)" style="flex:0 0 130px">
          <option value="public">Public</option>
          <option value="gm">GM only (secret)</option>
          <option value="faction:ally">Allies only</option>
          <option value="self:player">Player only</option>
        </select>
        <input type="number" :value="c.ttl ?? ''" @input="updNum(i, $event.target.value)"
               placeholder="TTL" title="TTL in beats (only for temporary conditions)" style="flex:0 0 70px" />
        <button class="mini" type="button" @click="rm(i)">✕</button>
      </div>
    </div>
    <button class="mini" type="button" @click="add">+ {{ label || 'Add entry' }}</button>
  </div>
</template>

<script setup>
const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  label: String,
})
const emit = defineEmits(['update:modelValue'])
function commit(a) { emit('update:modelValue', a) }
function upd(i, k, v) { commit(props.modelValue.map((c, idx) => (idx === i ? { ...c, [k]: v } : c))) }
function updNum(i, v) { upd(i, 'ttl', v === '' ? null : Number(v)) }
function rm(i) { const a = [...props.modelValue]; a.splice(i, 1); commit(a) }
function add() { commit([...props.modelValue, { content: '', gates: '', visibility: 'public', ttl: null }]) }
</script>
