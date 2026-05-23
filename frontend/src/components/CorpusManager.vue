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
  border: 1px solid #334;
  border-radius: 6px;
  margin-top: 8px;
  background: #0d1117;
}

.toggle-btn {
  width: 100%;
  background: none;
  border: none;
  color: #8b949e;
  padding: 8px 12px;
  text-align: left;
  cursor: pointer;
  font-size: 0.82rem;
  font-weight: 600;
  letter-spacing: 0.02em;
}
.toggle-btn:hover { color: #c9d1d9; }

.panel-body {
  padding: 10px 12px 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.field-label {
  font-size: 0.75rem;
  color: #8b949e;
}

.text-input {
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 4px;
  color: #c9d1d9;
  padding: 5px 8px;
  font-size: 0.82rem;
  outline: none;
}
.text-input:focus { border-color: #58a6ff; }

.file-input {
  font-size: 0.78rem;
  color: #8b949e;
}
.file-hint {
  font-size: 0.75rem;
  color: #58a6ff;
}

.action-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.action-btn {
  padding: 5px 12px;
  border-radius: 4px;
  border: none;
  font-size: 0.78rem;
  cursor: pointer;
  font-weight: 600;
}
.action-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.action-btn.upload { background: #21262d; color: #c9d1d9; border: 1px solid #30363d; }
.action-btn.upload:hover:not(:disabled) { background: #30363d; }
.action-btn.build { background: #1f6feb; color: #fff; }
.action-btn.build:hover:not(:disabled) { background: #388bfd; }

.inline-label {
  font-size: 0.75rem;
  color: #8b949e;
  display: flex;
  align-items: center;
  gap: 4px;
}
.mini-select, .num-input {
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 3px;
  color: #c9d1d9;
  font-size: 0.75rem;
  padding: 3px 5px;
}
.num-input { width: 70px; }

.status-text {
  font-size: 0.75rem;
  color: #58a6ff;
  margin: 0;
}
.status-text.error { color: #f85149; }

.corpus-list {
  border-top: 1px solid #21262d;
  padding-top: 8px;
}

.list-header {
  font-size: 0.75rem;
  color: #8b949e;
  margin-bottom: 4px;
}

.corpus-item {
  border: 1px solid #21262d;
  border-radius: 4px;
  margin-bottom: 4px;
  overflow: hidden;
}

.corpus-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  cursor: pointer;
  background: #161b22;
}
.corpus-row:hover { background: #1c2128; }

.corpus-id { font-size: 0.82rem; color: #c9d1d9; font-weight: 600; flex: 1; }
.corpus-meta { font-size: 0.72rem; color: #8b949e; }
.corpus-arrow { font-size: 0.65rem; color: #8b949e; }

.files-panel {
  background: #0d1117;
  padding: 6px 10px;
}

.file-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.file-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.75rem;
}
.file-name { flex: 1; color: #c9d1d9; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.file-size { color: #8b949e; white-space: nowrap; }
.del-btn {
  background: none;
  border: 1px solid #f8514933;
  border-radius: 3px;
  color: #f85149;
  font-size: 0.7rem;
  padding: 1px 5px;
  cursor: pointer;
}
.del-btn:hover { background: #f8514911; }

.subtle { font-size: 0.75rem; color: #8b949e; margin: 0; }
</style>
