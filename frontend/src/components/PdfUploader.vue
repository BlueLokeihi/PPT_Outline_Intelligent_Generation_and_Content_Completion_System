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
  if (!file) {
    return;
  }

  if (file.type !== 'application/pdf') {
    statusText.value = '仅支持 PDF 文件。';
    input.value = '';
    return;
  }

  const sizeMb = file.size / 1024 / 1024;
  if (sizeMb > MAX_SIZE_MB) {
    statusText.value = `文件过大，当前 ${sizeMb.toFixed(1)} MB，限制 ${MAX_SIZE_MB} MB。`;
    input.value = '';
    return;
  }

  statusText.value = '正在提取 PDF 文本...';
  isExtracting.value = true;
  try {
    const result = await extractPdfText(file);
    if (!result.text.trim()) {
      statusText.value = 'PDF 提取完成，但未识别到文本内容。';
    } else {
      statusText.value = `提取完成：${result.pageCount} 页。`;
      emit('extracted', {
        fileName: file.name,
        text: result.text,
        pageCount: result.pageCount,
      });
    }
  } catch (error) {
    statusText.value = error instanceof Error ? `PDF 解析失败：${error.message}` : 'PDF 解析失败';
  } finally {
    isExtracting.value = false;
    input.value = '';
  }
}
</script>

<template>
  <section class="pdf-card">
    <div>
      <h3>PDF资料</h3>
      <p class="subtle">上传后会自动提取文本并加入当前会话上下文。</p>
    </div>
    <label class="upload-btn" :class="{ disabled: isExtracting }">
      <input type="file" accept="application/pdf" :disabled="isExtracting" @change="onFileChange" />
      {{ isExtracting ? '处理中...' : '选择PDF' }}
    </label>
    <p class="subtle">{{ statusText }}</p>
  </section>
</template>
