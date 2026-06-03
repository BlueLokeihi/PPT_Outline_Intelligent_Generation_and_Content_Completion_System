<script setup lang="ts">
import { ref } from 'vue';
import { extractPdfText } from '@/utils/pdf';
import { extractDocx, extractPptx } from '@/services/bridge';
import { useChatStore } from '@/stores/chat';
import type { FileSource } from '@/types';

const props = defineProps<{
  disabled?: boolean;
  suggestions?: string[];
  showGenerateBtn?: boolean;
}>();

const emit = defineEmits<{
  send: [text: string];
  generate: [];
}>();

const store = useChatStore();
const text = ref('');
const fileInput = ref<HTMLInputElement | null>(null);
const uploading = ref(false);
const textareaRef = ref<HTMLTextAreaElement | null>(null);

function createId() {
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function detectType(fileName: string): FileSource['type'] {
  const ext = fileName.split('.').pop()?.toLowerCase() ?? '';
  if (ext === 'pdf') return 'pdf';
  if (ext === 'docx' || ext === 'doc') return 'docx';
  if (ext === 'pptx' || ext === 'ppt') return 'pptx';
  if (ext === 'md') return 'md';
  return 'txt';
}

async function onFileChange(e: Event) {
  const input = e.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  input.value = '';
  uploading.value = true;
  try {
    const type = detectType(file.name);
    let fileText = '';
    if (type === 'pdf') {
      const r = await extractPdfText(file);
      fileText = r.text;
    } else if (type === 'docx') {
      const r = await extractDocx(file);
      fileText = r.text ?? '';
    } else if (type === 'pptx') {
      const r = await extractPptx(file);
      fileText = r.text ?? '';
    } else {
      fileText = await file.text();
    }
    const source: FileSource = {
      id: createId(), name: file.name, type,
      text: fileText, size: file.size, addedAt: new Date().toISOString(),
    };
    store.addFileSource(store.activeSession.id, source);
  } catch (err) {
    console.error('File upload failed', err);
  } finally {
    uploading.value = false;
  }
}

function submit() {
  if (!text.value.trim() || props.disabled) return;
  emit('send', text.value.trim());
  text.value = '';
}

function onKeydown(event: KeyboardEvent) {
  if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
    event.preventDefault();
    submit();
  }
}

function applySuggestion(s: string) {
  text.value = s;
  textareaRef.value?.focus();
}
</script>

<template>
  <div class="composer">
    <!-- Suggestion chips -->
    <div v-if="suggestions?.length && !disabled" class="composer__chips">
      <button
        v-for="s in suggestions" :key="s"
        class="composer__chip"
        type="button"
        @click="applySuggestion(s)"
      >{{ s }}</button>
    </div>

    <!-- Claude-style rounded input card -->
    <div class="composer__card" :class="{ 'composer__card--disabled': disabled }">
      <textarea
        ref="textareaRef"
        class="composer__textarea"
        v-model="text"
        rows="2"
        :placeholder="disabled ? '生成中…' : '输入修改意见…'"
        :disabled="disabled"
        @keydown="onKeydown"
      />

      <div class="composer__bottom">
        <!-- Attach "+" -->
        <button
          class="composer__attach"
          type="button"
          title="上传文件（PDF / Word / PPT / TXT）"
          :disabled="disabled || uploading"
          @click="fileInput?.click()"
        >
          <svg v-if="!uploading" width="14" height="14" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
            <line x1="12" y1="5" x2="12" y2="19"/>
            <line x1="5" y1="12" x2="19" y2="12"/>
          </svg>
          <span v-else class="composer__spin"></span>
        </button>

        <input
          ref="fileInput"
          type="file"
          accept=".pdf,.docx,.doc,.pptx,.ppt,.txt,.md"
          style="display:none"
          @change="onFileChange"
        />

        <!-- "生成初版大纲" button — only shown before first generation -->
        <button
          v-if="props.showGenerateBtn"
          class="composer__generate-btn"
          type="button"
          @click="emit('generate')"
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>
          生成初版大纲
        </button>

        <span class="composer__kbd">Ctrl ↵</span>

        <!-- Send arrow -->
        <button
          class="composer__send"
          type="button"
          :disabled="disabled || !text.trim()"
          @click="submit"
          title="发送（Ctrl+Enter）"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <line x1="12" y1="19" x2="12" y2="5"/>
            <polyline points="5 12 12 5 19 12"/>
          </svg>
        </button>
      </div>
    </div>

    <p class="composer__footnote">Ctrl ↵ 发送 · 支持上传 PDF / Word / PPT / TXT</p>
  </div>
</template>

<style scoped>
.composer {
  padding: 4px 16px 12px;
  background: var(--paper);
  border-top: 1px solid var(--rule);
  flex-shrink: 0;
}

/* Chips */
.composer__chips {
  display: flex;
  gap: 6px;
  padding: 8px 0 8px;
  flex-wrap: nowrap;
  overflow-x: auto;
  scrollbar-width: none;
}
.composer__chips::-webkit-scrollbar { display: none; }
.composer__chip {
  flex-shrink: 0;
  padding: 5px 13px;
  border: 1px solid var(--rule-strong);
  border-radius: 20px;
  background: var(--paper);
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

/* Card */
.composer__card {
  border: 1.5px solid var(--rule-strong);
  border-radius: 14px;
  background: var(--paper);
  box-shadow: 0 2px 10px rgba(29, 27, 22, .07);
  overflow: hidden;
  transition: border-color .15s, box-shadow .15s;
}
.composer__card:focus-within {
  border-color: var(--ink-3);
  box-shadow: 0 3px 14px rgba(29, 27, 22, .1);
}
.composer__card--disabled { opacity: .6; }

/* Textarea */
.composer__textarea {
  width: 100%;
  border: none;
  outline: none;
  padding: 12px 16px 6px;
  font: inherit;
  font-size: 13.5px;
  background: transparent;
  color: var(--ink);
  resize: none;
  line-height: 1.6;
  min-height: 52px;
  max-height: 180px;
  overflow-y: auto;
  display: block;
  box-sizing: border-box;
}
.composer__textarea::placeholder { color: var(--ink-4); }
.composer__textarea:disabled { cursor: not-allowed; }

/* Bottom bar */
.composer__bottom {
  display: flex;
  align-items: center;
  padding: 6px 10px 8px;
  gap: 8px;
}

/* "+" attach */
.composer__attach {
  width: 30px; height: 30px;
  border-radius: 50%;
  border: 1px solid var(--rule-strong);
  background: transparent;
  color: var(--ink-3);
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: all .12s;
  flex-shrink: 0;
}
.composer__attach:hover:not(:disabled) {
  background: var(--paper-3);
  color: var(--ink);
  border-color: var(--ink-3);
}
.composer__attach:disabled { opacity: .4; cursor: not-allowed; }

.composer__spin {
  width: 12px; height: 12px;
  border: 2px solid var(--rule-strong);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: composer-spin .7s linear infinite;
  display: block;
}
@keyframes composer-spin { to { transform: rotate(360deg); } }

.composer__generate-btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 6px 14px;
  background: var(--ink);
  border: none;
  border-radius: 20px;
  font: inherit; font-size: 12.5px; font-weight: 600;
  color: var(--paper);
  cursor: pointer; transition: all .15s; white-space: nowrap;
  box-shadow: 0 2px 8px rgba(29,27,22,.2);
}
.composer__generate-btn:hover {
  background: var(--accent);
  box-shadow: 0 3px 12px rgba(176,74,47,.35);
}

.composer__kbd {
  font-size: 10.5px;
  color: var(--ink-4);
  font-family: var(--f-mono);
  margin-left: auto;
}

/* Send arrow button */
.composer__send {
  width: 32px; height: 32px;
  border-radius: 50%;
  border: none;
  background: var(--ink);
  color: var(--paper);
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: all .12s;
  flex-shrink: 0;
}
.composer__send:hover:not(:disabled) { background: var(--accent); }
.composer__send:disabled { opacity: .32; cursor: not-allowed; }

/* Footnote */
.composer__footnote {
  margin: 5px 0 0;
  font-size: 10.5px;
  color: var(--ink-4);
  text-align: center;
  font-family: var(--f-mono);
}
</style>
