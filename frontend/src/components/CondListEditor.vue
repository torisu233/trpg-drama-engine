<template>
  <div>
    <div v-for="(c, i) in modelValue" :key="i" class="cond">
      <input :value="c.content" @input="upd(i, 'content', $event.target.value)" placeholder="content（事实）" />
      <div class="row" style="gap:6px; margin-top:4px">
        <input :value="c.gates" @input="upd(i, 'gates', $event.target.value)" placeholder="gates（如何约束后续）" />
        <select :value="c.visibility || 'public'" @change="upd(i, 'visibility', $event.target.value)" style="flex:0 0 120px">
          <option value="public">public</option>
          <option value="gm">gm（秘密）</option>
          <option value="faction:ally">faction:ally</option>
          <option value="self:player">self:player</option>
        </select>
        <input type="number" :value="c.ttl ?? ''" @input="updNum(i, $event.target.value)"
               placeholder="TTL" title="ttl（瞬态才填）" style="flex:0 0 70px" />
        <button class="mini" type="button" @click="rm(i)">✕</button>
      </div>
    </div>
    <button class="mini" type="button" @click="add">＋ {{ label || '添加条目' }}</button>
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
