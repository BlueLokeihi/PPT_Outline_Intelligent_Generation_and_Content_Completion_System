<script setup lang="ts">
import { ref } from 'vue';
import { extractPdfText } from '@/utils/pdf';

const emit = defineEmits<{
  extracted: [payload: { fileName: string; text: string; pageCount: number }];
}>();

const isExtracting = ref(false);
const statusText = ref('');
const MAX_SIZE_MB = 20;

async function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;

  if (file.type !== 'application/pdf') {
    statusText.value = '仅支持 PDF 文件。';
    input.value = '';
    return;
  }
  const sizeMb = file.size / 1024 / 1024;
  if (sizeMb > MAX_SIZE_MB) {
    statusText.value = `文件过大（${sizeMb.toFixed(1)} MB），限制 ${MAX_SIZE_MB} MB。`;
    input.value = '';
    return;
  }

  statusText.value = '正在提取文本…';
  isExtracting.value = true;
  try {
    const result = await extractPdfText(file);
    if (!result.text.trim()) {
      statusText.value = '提取完成，未识别到文本。';
    } else {
      statusText.value = `已载入 ${file.name}（${result.pageCount} 页）`;
      emit('extracted', { fileName: file.name, text: result.text, pageCount: result.pageCount });
    }
  } catch (error) {
    statusText.value = error instanceof Error ? `解析失败：${error.message}` : '解析失败';
  } finally {
    isExtracting.value = false;
    input.value = '';
  }
}
</script>

<template>
  <div class="pdf-card">
    <h3>PDF 参考资料</h3>
    <p class="subtle">上传后文本将自动加入当前会话上下文</p>
    <label class="upload-btn" :class="{ disabled: isExtracting }">
      <input type="file" accept="application/pdf" :disabled="isExtracting" @change="onFileChange" />
      <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
        <path d="M6 1v7M2 8l4 3 4-3M1 11h10" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
      {{ isExtracting ? '处理中…' : '选择 PDF' }}
    </label>
    <p v-if="statusText" class="subtle" style="margin-top:6px; color: var(--accent);">{{ statusText }}</p>
  </div>
</template>
