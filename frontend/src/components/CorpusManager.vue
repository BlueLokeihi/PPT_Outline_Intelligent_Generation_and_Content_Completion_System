<script setup lang="ts">
import { ref, watch } from 'vue';
import { buildCorpus, deleteCorpusFile, getCorpora, listCorpusFiles, uploadCorpusFiles } from '@/services/bridge';
import type { RagCorpusInfo } from '@/types';

const emit = defineEmits<{
  corporaUpdated: [corpora: RagCorpusInfo[]];
}>();

const isOpen = ref(false);

// Upload state
const corpusIdInput = ref('');
const selectedFiles = ref<File[]>([]);
const fileInputEl = ref<HTMLInputElement | null>(null);
const uploadStatus = ref('');
const isUploading = ref(false);

// Build state
const buildProvider = ref('qwen');
const buildChunkSize = ref(500);
const buildStatus = ref('');
const isBuilding = ref(false);

// Corpus listing
const corpora = ref<RagCorpusInfo[]>([]);
const expandedCorpus = ref<string | null>(null);
const corpusFiles = ref<Array<{ name: string; size: number }>>([]);
const loadingFiles = ref(false);

async function refreshCorpora() {
  const res = await getCorpora();
  if (res.ok) {
    corpora.value = res.corpora;
    emit('corporaUpdated', res.corpora);
  }
}

function onFilesSelected(event: Event) {
  const input = event.target as HTMLInputElement;
  selectedFiles.value = Array.from(input.files ?? []);
}

async function handleUpload() {
  const id = corpusIdInput.value.trim();
  if (!id) {
    uploadStatus.value = '请先输入知识库名称。';
    return;
  }
  if (selectedFiles.value.length === 0) {
    uploadStatus.value = '请选择要上传的文件。';
    return;
  }

  isUploading.value = true;
  uploadStatus.value = `上传中（${selectedFiles.value.length} 个文件）...`;
  try {
    const res = await uploadCorpusFiles(id, selectedFiles.value);
    if (res.ok) {
      uploadStatus.value = `上传成功：${res.saved?.join(', ')}`;
      selectedFiles.value = [];
      if (fileInputEl.value) fileInputEl.value.value = '';
      await refreshCorpora();
      if (expandedCorpus.value === id) {
        await loadFiles(id);
      }
    } else {
      uploadStatus.value = `上传失败：${res.error}`;
    }
  } finally {
    isUploading.value = false;
  }
}

async function handleBuild() {
  const id = corpusIdInput.value.trim();
  if (!id) {
    buildStatus.value = '请先输入知识库名称。';
    return;
  }
  isBuilding.value = true;
  buildStatus.value = '正在构建向量索引，请稍候（可能需要数分钟）...';
  try {
    const res = await buildCorpus(id, {
      provider: buildProvider.value,
      chunkSize: buildChunkSize.value,
    });
    if (res.ok) {
      buildStatus.value = `索引构建成功（exitCode=${res.exitCode}）。`;
      await refreshCorpora();
    } else {
      buildStatus.value = `构建失败：${res.error}`;
    }
  } finally {
    isBuilding.value = false;
  }
}

async function loadFiles(id: string) {
  if (expandedCorpus.value === id) {
    expandedCorpus.value = null;
    corpusFiles.value = [];
    return;
  }
  expandedCorpus.value = id;
  loadingFiles.value = true;
  try {
    const res = await listCorpusFiles(id);
    corpusFiles.value = res.ok ? res.files : [];
  } finally {
    loadingFiles.value = false;
  }
}

async function removeFile(corpusId: string, filename: string) {
  const res = await deleteCorpusFile(corpusId, filename);
  if (res.ok) {
    corpusFiles.value = corpusFiles.value.filter((f) => f.name !== filename);
  }
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

watch(isOpen, (open) => {
  if (open) refreshCorpora();
});
</script>

<template>
  <section class="corpus-manager">
    <button class="toggle-btn" type="button" @click="isOpen = !isOpen">
      知识库管理 {{ isOpen ? '▲' : '▼' }}
    </button>

    <div v-if="isOpen" class="panel-body">
      <!-- Upload form -->
      <div class="form-group">
        <label class="field-label">知识库名称</label>
        <input
          v-model="corpusIdInput"
          class="text-input"
          type="text"
          placeholder="如：my_corpus"
          spellcheck="false"
        />
      </div>

      <div class="form-group">
        <label class="field-label">上传文件（PDF / TXT / DOCX）</label>
        <input
          ref="fileInputEl"
          type="file"
          multiple
          accept=".pdf,.txt,.docx,.doc,.md"
          class="file-input"
          @change="onFilesSelected"
        />
        <span v-if="selectedFiles.length > 0" class="file-hint">
          已选 {{ selectedFiles.length }} 个文件
        </span>
      </div>

      <div class="action-row">
        <button
          class="action-btn upload"
          type="button"
          :disabled="isUploading || isBuilding"
          @click="handleUpload"
        >
          {{ isUploading ? '上传中...' : '上传文件' }}
        </button>

        <label class="inline-label">
          Embedding provider
          <select v-model="buildProvider" class="mini-select">
            <option value="qwen">qwen</option>
            <option value="deepseek">deepseek</option>
            <option value="glm">glm</option>
          </select>
        </label>

        <label class="inline-label">
          块大小
          <input v-model.number="buildChunkSize" type="number" min="100" max="2000" step="50" class="num-input" />
        </label>

        <button
          class="action-btn build"
          type="button"
          :disabled="isUploading || isBuilding"
          @click="handleBuild"
        >
          {{ isBuilding ? '构建中...' : '构建索引' }}
        </button>
      </div>

      <p v-if="uploadStatus" class="status-text">{{ uploadStatus }}</p>
      <p v-if="buildStatus" class="status-text" :class="{ error: buildStatus.startsWith('构建失败') }">
        {{ buildStatus }}
      </p>

      <!-- Corpus list -->
      <div v-if="corpora.length > 0" class="corpus-list">
        <div class="list-header">已有知识库（{{ corpora.length }}）</div>
        <div v-for="c in corpora" :key="c.id" class="corpus-item">
          <div class="corpus-row" @click="loadFiles(c.id)">
            <span class="corpus-id">{{ c.id }}</span>
            <span class="corpus-meta">{{ c.size }} 块 · {{ c.embedding_model }}</span>
            <span class="corpus-arrow">{{ expandedCorpus === c.id ? '▲' : '▼' }}</span>
          </div>

          <div v-if="expandedCorpus === c.id" class="files-panel">
            <p v-if="loadingFiles" class="subtle">加载文件列表...</p>
            <p v-else-if="corpusFiles.length === 0" class="subtle">语料目录为空。</p>
            <ul v-else class="file-list">
              <li v-for="f in corpusFiles" :key="f.name" class="file-row">
                <span class="file-name">{{ f.name }}</span>
                <span class="file-size">{{ formatBytes(f.size) }}</span>
                <button class="del-btn" type="button" @click.stop="removeFile(c.id, f.name)">删除</button>
              </li>
            </ul>
          </div>
        </div>
      </div>
      <p v-else class="subtle">尚未构建任何知识库。</p>
    </div>
  </section>
</template>

<style scoped>
.corpus-manager {
  border-bottom: 1px solid var(--rule);
  background: var(--paper-2);
}

.toggle-btn {
  width: 100%; background: none; border: none;
  color: var(--ink-3); padding: 9px 16px;
  text-align: left; cursor: pointer;
  font-size: 11.5px; font-weight: 600; letter-spacing: 0.02em;
  display: flex; align-items: center; justify-content: space-between;
  font-family: var(--f-sans);
}
.toggle-btn:hover { color: var(--ink); background: var(--paper-3); }

.panel-body {
  padding: 10px 16px 14px;
  display: flex; flex-direction: column; gap: 8px;
  border-top: 1px solid var(--rule);
}

.form-group { display: flex; flex-direction: column; gap: 3px; }
.field-label { font-size: 10.5px; color: var(--ink-4); font-family: var(--f-mono); text-transform: uppercase; letter-spacing: 0.04em; }

.text-input {
  background: var(--paper); border: 1px solid var(--rule); border-radius: var(--r-sm);
  color: var(--ink); padding: 5px 8px; font-size: 12px; outline: none;
  font-family: inherit;
}
.text-input:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }

.file-input { font-size: 11.5px; color: var(--ink-3); }
.file-hint { font-size: 11px; color: var(--accent); }

.action-row { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }

.action-btn {
  padding: 4px 11px; border-radius: var(--r-sm);
  font-size: 11.5px; cursor: pointer; font-weight: 500;
  font-family: inherit; transition: all .12s;
}
.action-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.action-btn.upload {
  background: var(--paper); color: var(--ink-2);
  border: 1px solid var(--rule);
}
.action-btn.upload:hover:not(:disabled) { background: var(--paper-3); border-color: var(--ink-4); }
.action-btn.build {
  background: var(--ink); color: var(--paper); border: 1px solid var(--ink);
}
.action-btn.build:hover:not(:disabled) { background: var(--accent); border-color: var(--accent); }

.inline-label {
  font-size: 11px; color: var(--ink-4);
  display: flex; align-items: center; gap: 4px;
  font-family: var(--f-mono);
}
.mini-select, .num-input {
  background: var(--paper); border: 1px solid var(--rule);
  border-radius: var(--r-sm); color: var(--ink);
  font-size: 11px; padding: 3px 5px; outline: none;
}
.num-input { width: 62px; }

.status-text { font-size: 11.5px; color: var(--accent); margin: 0; font-family: var(--f-mono); }
.status-text.error { color: var(--danger); }

.corpus-list { border-top: 1px solid var(--rule); padding-top: 8px; }
.list-header {
  font-size: 10px; color: var(--ink-4); margin-bottom: 4px;
  font-family: var(--f-mono); text-transform: uppercase; letter-spacing: 0.05em;
}

.corpus-item {
  border: 1px solid var(--rule); border-radius: var(--r-sm);
  margin-bottom: 4px; overflow: hidden;
}
.corpus-row {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 8px; cursor: pointer; background: var(--paper);
  transition: background .1s;
}
.corpus-row:hover { background: var(--paper-3); }
.corpus-id { font-size: 12px; color: var(--ink); font-weight: 600; flex: 1; }
.corpus-meta { font-size: 10.5px; color: var(--ink-4); font-family: var(--f-mono); }
.corpus-arrow { font-size: 10px; color: var(--ink-4); }

.files-panel { background: var(--paper-2); padding: 6px 10px; }
.file-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 4px; }
.file-row { display: flex; align-items: center; gap: 8px; font-size: 11.5px; }
.file-name { flex: 1; color: var(--ink-2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.file-size { color: var(--ink-4); white-space: nowrap; font-family: var(--f-mono); font-size: 10.5px; }
.del-btn {
  background: none; border: 1px solid rgba(185,28,28,.2);
  border-radius: 3px; color: var(--danger);
  font-size: 10px; padding: 1px 5px; cursor: pointer; transition: all .12s;
}
.del-btn:hover { background: rgba(185,28,28,.07); }

.subtle { font-size: 11px; color: var(--ink-4); margin: 0; font-style: italic; }
</style>
