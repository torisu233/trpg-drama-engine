<template>
  <div>
    <div v-for="(c, i) in modelValue" :key="i" class="cond">
      <input :value="c.內容" @input="upd(i, '內容', $event.target.value)" placeholder="內容（事實）" />
      <div class="row" style="gap:6px; margin-top:4px">
        <input :value="c.gates" @input="upd(i, 'gates', $event.target.value)" placeholder="gates（如何約束後續）" />
        <select :value="c.可見性 || 'public'" @change="upd(i, '可見性', $event.target.value)" style="flex:0 0 120px">
          <option value="public">public</option>
          <option value="gm">gm（秘密）</option>
          <option value="faction:我方">faction:我方</option>
          <option value="self:player">self:player</option>
        </select>
        <input type="number" :value="c.剩餘拍數 ?? ''" @input="updNum(i, $event.target.value)"
               placeholder="TTL" title="剩餘拍數（瞬態才填）" style="flex:0 0 70px" />
        <button class="mini" type="button" @click="rm(i)">✕</button>
      </div>
    </div>
    <button class="mini" type="button" @click="add">＋ {{ label || '新增條目' }}</button>
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
function updNum(i, v) { upd(i, '剩餘拍數', v === '' ? null : Number(v)) }
function rm(i) { const a = [...props.modelValue]; a.splice(i, 1); commit(a) }
function add() { commit([...props.modelValue, { 內容: '', gates: '', 可見性: 'public', 剩餘拍數: null }]) }
</script>
