<script setup lang="ts">
import { ref } from 'vue';

const props = defineProps<{
  disabled?: boolean;
  suggestions?: string[];
}>();

const emit = defineEmits<{
  send: [text: string];
}>();

const text = ref('');

function submit() {
  if (!text.value.trim() || props.disabled) return;
  emit('send', text.value);
  text.value = '';
}

function onKeydown(event: KeyboardEvent) {
  if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
    submit();
  }
}

function applySuggestion(s: string) {
  text.value = s;
}
</script>

<template>
  <div class="composer">
    <div v-if="suggestions?.length && !disabled" class="composer__chips">
      <button
        v-for="s in suggestions"
        :key="s"
        class="composer__chip"
        type="button"
        @click="applySuggestion(s)"
      >
        {{ s }}
      </button>
    </div>
    <div class="composer__box">
      <textarea
        class="composer__input"
        v-model="text"
        rows="3"
        placeholder="继续提出修改意见…（Ctrl+Enter 发送）"
        :disabled="props.disabled"
        @keydown="onKeydown"
      />
      <div class="composer__foot">
        <span class="composer__hint">Ctrl ↵ 发送</span>
        <button
          class="composer__send"
          type="button"
          :disabled="props.disabled || !text.trim()"
          @click="submit"
        >
          发送
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
            <path d="M1 6h10M6 1l5 5-5 5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.composer__chips {
  display: flex;
  gap: 6px;
  padding: 8px 16px 2px;
  flex-wrap: nowrap;
  overflow-x: auto;
  scrollbar-width: none;
}
.composer__chips::-webkit-scrollbar { display: none; }

.composer__chip {
  flex-shrink: 0;
  padding: 4px 12px;
  border: 1px solid var(--rule-strong);
  border-radius: 14px;
  background: var(--paper-2);
  color: var(--ink-2);
  font-size: 12px;
  font-family: inherit;
  cursor: pointer;
  transition: all .12s;
  white-space: nowrap;
}
.composer__chip:hover {
  background: var(--accent-soft);
  border-color: var(--accent-stroke);
  color: var(--accent);
}
</style>
