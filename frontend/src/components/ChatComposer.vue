<script setup lang="ts">
import { ref } from 'vue';

const props = defineProps<{
  disabled?: boolean;
}>();

const emit = defineEmits<{
  send: [text: string];
}>();

const text = ref('');

function submit() {
  if (!text.value.trim() || props.disabled) {
    return;
  }
  emit('send', text.value);
  text.value = '';
}

function onKeydown(event: KeyboardEvent) {
  if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
    submit();
  }
}
</script>

<template>
  <section class="composer">
    <textarea
      v-model="text"
      rows="4"
      placeholder="输入你的大纲需求或修改意见，例如：把风格改成正式学术风，页数控制在12页内"
      :disabled="props.disabled"
      @keydown="onKeydown"
    />
    <button type="button" :disabled="props.disabled || !text.trim()" @click="submit">发送</button>
  </section>
</template>
