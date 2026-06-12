<template>
  <div class="pwwrap">
    <input
      :type="show ? 'text' : 'password'"
      :value="modelValue"
      :placeholder="placeholder"
      :autocomplete="autocomplete"
      @input="$emit('update:modelValue', $event.target.value)"
      @keyup.enter="$emit('enter')"
    />
    <button type="button" class="pwtoggle" @click="show = !show" :title="show ? '隐藏' : '显示'">
      {{ show ? '隐藏' : '显示' }}
    </button>
  </div>
</template>

<script setup>
import { ref } from 'vue'

defineProps({
  modelValue: { type: String, default: '' },
  placeholder: { type: String, default: '密码' },
  autocomplete: { type: String, default: 'current-password' },
})
defineEmits(['update:modelValue', 'enter'])

const show = ref(false)
</script>
