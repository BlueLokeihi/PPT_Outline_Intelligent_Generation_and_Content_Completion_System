<script setup lang="ts">
import { computed, ref } from 'vue';
import { extractPdfText } from '@/utils/pdf';
import { extractDocx, extractPptx, searchWeb } from '@/services/bridge';
import { useChatStore } from '@/stores/chat';
import type { FileSource, RagCorpusInfo, RagCorpusSource, WebSource } from '@/types';
import CorpusManager from '@/components/CorpusManager.vue';

const props = defineProps<{
  availableCorpora?: RagCorpusInfo[];
  availableSources?: RagCorpusSource[];
}>();

const emit = defineEmits<{
  corporaUpdated: [corpora: RagCorpusInfo[]];
}>();

const store = useChatStore();
const session = computed(() => store.activeSession);

// RAG state
const showCorpusManager = ref(false);

const selectedCorpus = computed(() =>
  (props.availableCorpora ?? []).find(c => c.id === store.corpusId) ?? null,
);
const corpusNeedsBuild = computed(() => {
  if (!store.corpusId) return false;
  const src = (props.availableSources ?? []).find(s => s.id === store.corpusId);
  return !!src && !src.has_index;
});
const ragModeLabel: Record<string, string> = {
  hybrid: 'Hybrid（向量 + BM25，推荐）',
  vector: 'Vector（纯向量）',
  bm25: 'BM25（纯关键词）',
};

function onCorporaUpdated(list: RagCorpusInfo[]) {
  emit('corporaUpdated', list);
}

// Modal state
const showModal = ref(false);
const showPasteText = ref(false);
const pasteText = ref('');
const pasteFileName = ref('');

// Upload state
const uploading = ref(false);
const uploadError = ref('');

// Web search state
const searching = ref(false);
const webQuery = ref('');
const webError = ref('');

const fileInput = ref<HTMLInputElement | null>(null);
const dropzoneActive = ref(false);

const ACCEPT = '.pdf,.docx,.doc,.pptx,.ppt,.txt,.md';
const MAX_MB = 20;

function createId() {
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}
function sizeLabel(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
function fileIcon(type: FileSource['type']) {
  if (type === 'pdf') return '📄';
  if (type === 'docx') return '📝';
  if (type === 'pptx') return '📊';
  return '📃';
}
function detectType(fileName: string): FileSource['type'] {
  const ext = fileName.split('.').pop()?.toLowerCase() ?? '';
  if (ext === 'pdf') return 'pdf';
  if (ext === 'docx' || ext === 'doc') return 'docx';
  if (ext === 'pptx' || ext === 'ppt') return 'pptx';
  if (ext === 'md') return 'md';
  return 'txt';
}

async function processFile(file: File) {
  const mb = file.size / 1024 / 1024;
  if (mb > MAX_MB) {
    uploadError.value = `文件过大（${mb.toFixed(1)} MB），限制 ${MAX_MB} MB`;
    return;
  }
  uploadError.value = '';
  uploading.value = true;
  try {
    const type = detectType(file.name);
    let text = '';
    if (type === 'pdf') { const r = await extractPdfText(file); text = r.text; }
    else if (type === 'docx') { const r = await extractDocx(file); if (!r.ok) throw new Error(r.error); text = r.text ?? ''; }
    else if (type === 'pptx') { const r = await extractPptx(file); if (!r.ok) throw new Error(r.error); text = r.text ?? ''; }
    else { text = await file.text(); }

    const source: FileSource = {
      id: createId(), name: file.name, type,
      text, size: file.size, addedAt: new Date().toISOString(),
    };
    store.addFileSource(session.value.id, source);
  } catch (err) {
    uploadError.value = err instanceof Error ? err.message : '上传失败';
  } finally {
    uploading.value = false;
  }
}

async function onFileChange(e: Event) {
  const input = e.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  input.value = '';
  await processFile(file);
  showModal.value = false;
}

function onDragOver() { dropzoneActive.value = true; }
function onDragLeave() { dropzoneActive.value = false; }
async function onDrop(e: DragEvent) {
  dropzoneActive.value = false;
  const file = e.dataTransfer?.files?.[0];
  if (!file) return;
  await processFile(file);
  showModal.value = false;
}

async function onWebSearch() {
  const q = webQuery.value.trim();
  if (!q || searching.value) return;
  searching.value = true;
  webError.value = '';
  try {
    const res = await searchWeb(q, 8);
    if (!res.ok) throw new Error(res.error ?? '搜索失败');
    const source: WebSource = {
      id: createId(), query: q,
      results: res.results, addedAt: new Date().toISOString(),
    };
    store.addWebSource(session.value.id, source);
    webQuery.value = '';
    showModal.value = false;
  } catch (err) {
    webError.value = err instanceof Error ? err.message : '搜索失败';
  } finally {
    searching.value = false;
  }
}

function addPastedText() {
  const t = pasteText.value.trim();
  if (!t) return;
  const name = pasteFileName.value.trim() || `粘贴的文字（${new Date().toLocaleTimeString()}）`;
  const source: FileSource = {
    id: createId(), name, type: 'txt',
    text: t, size: new Blob([t]).size, addedAt: new Date().toISOString(),
  };
  store.addFileSource(session.value.id, source);
  pasteText.value = '';
  pasteFileName.value = '';
  showPasteText.value = false;
  showModal.value = false;
}

const expandedWeb = ref<Record<string, boolean>>({});
function toggleWeb(id: string) { expandedWeb.value[id] = !expandedWeb.value[id]; }

function openModal() {
  showModal.value = true;
  showPasteText.value = false;
  uploadError.value = '';
  webError.value = '';
}
</script>

<template>
  <aside class="sp">
    <!-- Header -->
    <div class="sp__head">
      <span class="sp__head-title">来源</span>
      <button class="sp__add-btn" @click="openModal">
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        添加来源
      </button>
    </div>

    <!-- Hidden file input -->
    <input ref="fileInput" type="file" :accept="ACCEPT" style="display:none" @change="onFileChange" />

    <!-- File sources -->
    <div class="sp__section" v-if="(session?.fileSources?.length ?? 0) > 0">
      <div class="sp__section-label">文件</div>
      <div class="sp__files">
        <div v-for="src in (session?.fileSources ?? [])" :key="src.id" class="sp__file">
          <span class="sp__file-icon">{{ fileIcon(src.type) }}</span>
          <div class="sp__file-info">
            <div class="sp__file-name" :title="src.name">{{ src.name }}</div>
            <div class="sp__file-meta">{{ src.type.toUpperCase() }} · {{ sizeLabel(src.size) }}</div>
          </div>
          <button class="sp__file-del" @click="store.removeFileSource(session.id, src.id)" title="移除">×</button>
        </div>
      </div>
    </div>

    <!-- Web sources -->
    <div class="sp__section" v-if="(session?.webSources?.length ?? 0) > 0">
      <div class="sp__section-label">网络来源</div>
      <div class="sp__web-list">
        <div v-for="ws in (session?.webSources ?? [])" :key="ws.id" class="sp__web-item">
          <div class="sp__web-head" @click="toggleWeb(ws.id)">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
            <span class="sp__web-query">{{ ws.query }}</span>
            <span class="sp__web-count">{{ ws.results.length }}</span>
            <svg :class="['sp__web-chev', { 'sp__web-chev--up': expandedWeb[ws.id] }]" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><polyline points="6 9 12 15 18 9"/></svg>
          </div>
          <div v-if="expandedWeb[ws.id]" class="sp__web-results">
            <a v-for="(r, i) in ws.results" :key="i" class="sp__web-result" :href="r.url" target="_blank" rel="noopener">
              <span class="sp__web-result-num">{{ i + 1 }}</span>
              <span class="sp__web-result-title">{{ r.title }}</span>
            </a>
          </div>
        </div>
      </div>
    </div>

    <!-- ── RAG Knowledge Base Section ── -->
    <div class="sp__section sp__rag-section">
      <div class="sp__section-label">知识库 (RAG)</div>
      <div class="sp__rag-card">

        <!-- Toggle -->
        <label class="sp__rag-toggle" :class="{ 'sp__rag-toggle--disabled': (props.availableCorpora ?? []).length === 0 }">
          <span class="sp__rag-toggle-track" :class="{ 'is-on': store.useRag }">
            <span class="sp__rag-toggle-knob" />
          </span>
          <input
            type="checkbox"
            v-model="store.useRag"
            :disabled="(props.availableCorpora ?? []).length === 0"
            style="display:none"
          />
          <span class="sp__rag-toggle-label">{{ store.useRag ? '已启用' : '未启用' }}</span>
        </label>

        <template v-if="(props.availableCorpora ?? []).length > 0">
          <!-- Corpus select -->
          <div class="sp__rag-row">
            <span class="sp__rag-key">知识库</span>
            <select class="sp__rag-select" v-model="store.corpusId">
              <option v-for="c in (props.availableCorpora ?? [])" :key="c.id" :value="c.id">{{ c.id }}</option>
            </select>
          </div>

          <!-- Mode select -->
          <div class="sp__rag-row" v-if="store.useRag">
            <span class="sp__rag-key">检索模式</span>
            <select class="sp__rag-select" v-model="store.ragMode">
              <option value="hybrid">hybrid（推荐）</option>
              <option value="vector">vector</option>
              <option value="bm25">bm25</option>
            </select>
          </div>

          <!-- Corpus status -->
          <div v-if="selectedCorpus" class="sp__rag-status">
            <span class="sp__rag-dot sp__rag-dot--ok"></span>
            <span>已建索引 · {{ selectedCorpus.size }} 片段 · {{ selectedCorpus.embedding_model }}</span>
          </div>

          <!-- Needs rebuild warning -->
          <div v-if="corpusNeedsBuild" class="sp__rag-warn">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
            有文件未建索引，请重新构建
          </div>
        </template>

        <!-- No corpora -->
        <div v-else class="sp__rag-empty-msg">
          暂无可用知识库，请先上传文件并构建索引
        </div>

        <!-- Manage button -->
        <button class="sp__rag-manage-btn" @click="showCorpusManager = true">
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="3"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14M4.93 4.93a10 10 0 0 0 0 14.14"/></svg>
          管理知识库
        </button>
      </div>
    </div>

    <!-- Empty state -->
    <div v-if="(session?.fileSources?.length ?? 0) === 0 && (session?.webSources?.length ?? 0) === 0" class="sp__empty">
      <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
      <p>点击「添加来源」上传文件<br/>或搜索网络内容</p>
      <p class="sp__empty-types">.pdf · .docx · .pptx · .txt · .md</p>
    </div>
  </aside>

  <!-- ── Corpus Manager Modal ── -->
  <Teleport to="body">
    <div v-if="showCorpusManager" class="sp-modal-overlay" @click.self="showCorpusManager = false">
      <div class="sp-modal sp-modal--wide">
        <button class="sp-modal__close" @click="showCorpusManager = false">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </button>
        <h2 class="sp-modal__title">管理知识库</h2>
        <CorpusManager @corporaUpdated="onCorporaUpdated" />
      </div>
    </div>
  </Teleport>

  <!-- ── Add Source Modal ── -->
  <Teleport to="body">
    <div v-if="showModal" class="sp-modal-overlay" @click.self="showModal = false">
      <div class="sp-modal">
        <!-- Close -->
        <button class="sp-modal__close" @click="showModal = false">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </button>

        <!-- Title -->
        <h2 class="sp-modal__title">添加来源</h2>

        <!-- ① Web search -->
        <div class="sp-modal__section">
          <div class="sp-modal__search-wrap">
            <svg class="sp-modal__search-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
            <input
              class="sp-modal__search-input"
              v-model="webQuery"
              placeholder="在网络中搜索新来源…"
              :disabled="searching"
              @keydown.enter="onWebSearch"
            />
            <button class="sp-modal__search-btn" :disabled="!webQuery.trim() || searching" @click="onWebSearch">
              <span v-if="searching" class="sp-modal__spin"></span>
              <svg v-else width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            </button>
          </div>
          <div v-if="webError" class="sp-modal__search-err">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
            {{ webError }}
          </div>
        </div>

        <!-- Divider -->
        <div class="sp-modal__divider"><span>或拖放文件</span></div>

        <!-- ② Drop zone -->
        <div
          class="sp-modal__dropzone"
          :class="{ 'sp-modal__dropzone--active': dropzoneActive }"
          @dragover.prevent="onDragOver"
          @dragleave="onDragLeave"
          @drop.prevent="onDrop"
        >
          <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
          <p class="sp-modal__drop-title">拖放文件到此处</p>
          <p class="sp-modal__drop-sub">PDF、Word、PPT、TXT、MD，等等</p>
          <p v-if="uploadError" class="sp-modal__error">{{ uploadError }}</p>
        </div>

        <!-- ③ Action buttons -->
        <div class="sp-modal__actions">
          <button class="sp-modal__action" :disabled="uploading" @click="fileInput?.click()">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
            <span>{{ uploading ? '上传中…' : '上传文件' }}</span>
          </button>

          <button class="sp-modal__action" @click="showPasteText = !showPasteText">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><rect x="8" y="2" width="8" height="4" rx="1" ry="1"/></svg>
            <span>粘贴文字</span>
          </button>
        </div>

        <!-- ④ Paste text area (expandable) -->
        <div v-if="showPasteText" class="sp-modal__paste">
          <input
            class="sp-modal__paste-name"
            v-model="pasteFileName"
            placeholder="来源名称（可选）"
          />
          <textarea
            class="sp-modal__paste-area"
            v-model="pasteText"
            rows="5"
            placeholder="粘贴或输入文字内容…"
          />
          <div class="sp-modal__paste-foot">
            <button class="sp-modal__paste-cancel" @click="showPasteText = false">取消</button>
            <button class="sp-modal__paste-add" :disabled="!pasteText.trim()" @click="addPastedText">添加</button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
/* ── PANEL ── */
.sp {
  width: 100%; height: 100%;
  display: flex; flex-direction: column;
  background: var(--paper); border-right: 1px solid var(--rule);
  overflow: hidden;
}
.sp__head {
  display: flex; align-items: center; gap: 8px;
  padding: 14px 16px 12px;
  border-bottom: 1px solid var(--rule); flex-shrink: 0;
}
.sp__head-title { font-size: 13px; font-weight: 700; color: var(--ink-2); flex: 1; }
.sp__add-btn {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 5px 12px;
  background: var(--paper-3); border: 1px solid var(--rule-strong);
  border-radius: 6px; font: inherit; font-size: 12px; font-weight: 500;
  color: var(--ink-2); cursor: pointer; transition: all .12s; white-space: nowrap;
}
.sp__add-btn:hover { background: var(--ink); color: var(--paper); border-color: var(--ink); }

.sp__section { flex-shrink: 0; }
.sp__section-label {
  padding: 10px 16px 4px;
  font-size: 10.5px; font-weight: 700; text-transform: uppercase;
  letter-spacing: .06em; color: var(--ink-4); font-family: var(--f-mono);
}
.sp__files { padding: 0 8px; }
.sp__file {
  display: flex; align-items: center; gap: 8px;
  padding: 7px 8px; border-radius: 7px; transition: background .12s;
}
.sp__file:hover { background: var(--paper-3); }
.sp__file-icon { font-size: 16px; flex-shrink: 0; }
.sp__file-info { flex: 1; min-width: 0; }
.sp__file-name { font-size: 12px; font-weight: 500; color: var(--ink); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sp__file-meta { font-size: 10.5px; color: var(--ink-4); font-family: var(--f-mono); }
.sp__file-del { background: none; border: none; color: var(--ink-4); font-size: 15px; cursor: pointer; padding: 0 2px; opacity: 0; transition: opacity .12s; }
.sp__file:hover .sp__file-del { opacity: 1; }
.sp__file-del:hover { color: #dc2626; }

.sp__web-list { padding: 0 8px 8px; }
.sp__web-item { border-radius: 7px; overflow: hidden; margin-bottom: 4px; border: 1px solid var(--rule); }
.sp__web-head { display: flex; align-items: center; gap: 6px; padding: 7px 10px; cursor: pointer; font-size: 11.5px; color: var(--ink-2); background: var(--paper-2); }
.sp__web-head:hover { background: var(--paper-3); }
.sp__web-head svg { color: var(--accent); flex-shrink: 0; }
.sp__web-query { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 500; }
.sp__web-count { font-family: var(--f-mono); font-size: 10px; color: var(--paper); background: var(--accent); border-radius: 10px; padding: 0 5px; }
.sp__web-chev { color: var(--ink-4); transition: transform .15s; }
.sp__web-chev--up { transform: rotate(180deg); }
.sp__web-results { padding: 4px 0; background: var(--paper); }
.sp__web-result { display: flex; align-items: flex-start; gap: 8px; padding: 5px 10px; text-decoration: none; font-size: 11px; color: var(--ink-2); transition: background .12s; }
.sp__web-result:hover { background: var(--paper-3); }
.sp__web-result-num { flex-shrink: 0; width: 16px; height: 16px; border-radius: 50%; background: var(--paper-3); border: 1px solid var(--rule-strong); font-family: var(--f-mono); font-size: 9px; font-weight: 700; color: var(--ink-4); display: flex; align-items: center; justify-content: center; }
.sp__web-result-title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.sp__empty { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 24px; text-align: center; color: var(--ink-4); }
.sp__empty svg { margin-bottom: 12px; color: var(--rule-strong); }
.sp__empty p { font-size: 12.5px; line-height: 1.6; margin: 0 0 6px; }
.sp__empty-types { font-size: 10.5px; font-family: var(--f-mono); }

/* ── RAG Section ── */
.sp__rag-section { flex-shrink: 0; border-top: 1px solid var(--rule); }

.sp__rag-card {
  margin: 8px 8px 10px;
  border: 1px solid var(--rule);
  border-radius: 10px;
  padding: 10px 12px;
  background: var(--paper-2);
  display: flex; flex-direction: column; gap: 8px;
}

/* Toggle */
.sp__rag-toggle {
  display: flex; align-items: center; gap: 8px;
  cursor: pointer; user-select: none;
}
.sp__rag-toggle--disabled { opacity: .5; cursor: not-allowed; }
.sp__rag-toggle-track {
  width: 34px; height: 18px; border-radius: 9px;
  background: var(--rule-strong); position: relative;
  transition: background .2s; flex-shrink: 0;
}
.sp__rag-toggle-track.is-on { background: var(--accent); }
.sp__rag-toggle-knob {
  position: absolute; top: 2px; left: 2px;
  width: 14px; height: 14px; border-radius: 50%;
  background: white; box-shadow: 0 1px 3px rgba(0,0,0,.2);
  transition: transform .2s;
}
.sp__rag-toggle-track.is-on .sp__rag-toggle-knob { transform: translateX(16px); }
.sp__rag-toggle-label { font-size: 12.5px; font-weight: 600; color: var(--ink-2); }

/* Rows */
.sp__rag-row {
  display: flex; align-items: center; gap: 8px;
}
.sp__rag-key {
  font-size: 11px; color: var(--ink-4); font-family: var(--f-mono);
  white-space: nowrap; min-width: 52px;
}
.sp__rag-select {
  flex: 1; border: 1px solid var(--rule); border-radius: 6px;
  padding: 4px 8px; font: inherit; font-size: 11.5px;
  background: var(--paper); color: var(--ink); outline: none;
  cursor: pointer;
}

/* Status */
.sp__rag-status {
  display: flex; align-items: center; gap: 6px;
  font-size: 11px; color: var(--ink-3);
}
.sp__rag-dot {
  width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0;
}
.sp__rag-dot--ok { background: #22c55e; }

/* Warn */
.sp__rag-warn {
  display: flex; align-items: center; gap: 5px;
  font-size: 11px; color: #d97706;
  background: #fffbeb; border: 1px solid #fcd34d;
  border-radius: 6px; padding: 5px 8px;
}

.sp__rag-empty-msg {
  font-size: 11.5px; color: var(--ink-4);
  line-height: 1.5;
}

/* Manage button */
.sp__rag-manage-btn {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 5px 10px; border: 1px solid var(--rule-strong);
  border-radius: 6px; background: var(--paper);
  font: inherit; font-size: 11.5px; color: var(--ink-2);
  cursor: pointer; transition: all .12s; width: fit-content;
}
.sp__rag-manage-btn:hover { background: var(--ink); color: var(--paper); border-color: var(--ink); }

/* Wide modal for CorpusManager */
.sp-modal--wide { max-width: 680px; }

/* ── MODAL ── */
.sp-modal-overlay {
  position: fixed; inset: 0; z-index: 300;
  background: rgba(29, 27, 22, .45);
  backdrop-filter: blur(4px);
  display: flex; align-items: center; justify-content: center;
  padding: 24px;
  animation: sp-fade .15s ease;
}
@keyframes sp-fade { from { opacity: 0; } to { opacity: 1; } }

.sp-modal {
  background: #fff;
  border-radius: 16px;
  box-shadow: 0 24px 64px rgba(29,27,22,.18), 0 4px 16px rgba(29,27,22,.1);
  width: 100%; max-width: 560px;
  padding: 28px 28px 24px;
  position: relative;
  animation: sp-slide .18s ease;
  max-height: 90vh;
  overflow-y: auto;
}
@keyframes sp-slide { from { transform: translateY(10px); opacity: 0; } to { transform: translateY(0); opacity: 1; } }

.sp-modal__close {
  position: absolute; top: 16px; right: 16px;
  width: 28px; height: 28px; border-radius: 50%;
  border: none; background: var(--paper-3); color: var(--ink-3);
  cursor: pointer; display: flex; align-items: center; justify-content: center;
  transition: all .12s;
}
.sp-modal__close:hover { background: var(--paper); color: var(--ink); border: 1px solid var(--rule-strong); }

.sp-modal__title {
  font-family: var(--f-serif); font-size: 20px; font-weight: 500;
  color: var(--ink); margin: 0 0 20px; letter-spacing: -.01em;
}

/* Search */
.sp-modal__section { margin-bottom: 16px; }
.sp-modal__search-wrap {
  display: flex; align-items: center; gap: 0;
  border: 1.5px solid #e0ddd8;
  border-radius: 10px; overflow: hidden;
  background: #fafaf8;
  transition: border-color .15s;
}
.sp-modal__search-wrap:focus-within { border-color: var(--ink-3); }
.sp-modal__search-icon { flex-shrink: 0; color: #a0998d; margin-left: 12px; }
.sp-modal__search-input {
  flex: 1; border: none; outline: none; background: transparent;
  padding: 11px 12px; font: inherit; font-size: 13.5px; color: var(--ink);
}
.sp-modal__search-input::placeholder { color: #b0a898; }
.sp-modal__search-input:disabled { opacity: .6; }
.sp-modal__search-btn {
  flex-shrink: 0; width: 36px; height: 36px; margin: 4px;
  border: none; border-radius: 7px;
  background: var(--ink); color: #fff;
  cursor: pointer; display: flex; align-items: center; justify-content: center;
  transition: background .12s;
}
.sp-modal__search-btn:hover:not(:disabled) { background: var(--accent); }
.sp-modal__search-btn:disabled { opacity: .35; cursor: not-allowed; }
.sp-modal__spin {
  width: 12px; height: 12px; border: 2px solid rgba(255,255,255,.3);
  border-top-color: #fff; border-radius: 50%; animation: sp-spin .7s linear infinite;
}
@keyframes sp-spin { to { transform: rotate(360deg); } }

/* Divider */
.sp-modal__divider {
  display: flex; align-items: center; gap: 12px;
  margin: 18px 0; color: #b0a898; font-size: 12px;
}
.sp-modal__divider::before,
.sp-modal__divider::after { content: ''; flex: 1; height: 1px; background: #e8e4de; }

/* Drop zone */
.sp-modal__dropzone {
  border: 2px dashed #d8d4cd;
  border-radius: 12px; padding: 28px 20px;
  text-align: center; cursor: default;
  transition: all .15s; background: #fafaf8;
  margin-bottom: 16px;
}
.sp-modal__dropzone--active {
  border-color: var(--accent); background: var(--accent-soft);
}
.sp-modal__dropzone svg { color: #c0b8b0; margin-bottom: 10px; }
.sp-modal__dropzone--active svg { color: var(--accent); }
.sp-modal__drop-title { font-size: 14px; font-weight: 500; color: var(--ink-2); margin: 0 0 4px; }
.sp-modal__drop-sub { font-size: 12px; color: #a0998d; margin: 0; }

/* Action buttons */
.sp-modal__actions { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 4px; }
.sp-modal__action {
  flex: 1; min-width: 120px;
  display: flex; align-items: center; justify-content: center; gap: 8px;
  padding: 11px 16px;
  border: 1.5px solid #e0ddd8;
  border-radius: 10px; background: #fafaf8;
  font: inherit; font-size: 13px; font-weight: 500; color: var(--ink-2);
  cursor: pointer; transition: all .12s;
}
.sp-modal__action:hover:not(:disabled) {
  border-color: var(--ink-3); background: #fff; color: var(--ink);
  box-shadow: 0 2px 8px rgba(29,27,22,.08);
}
.sp-modal__action:disabled { opacity: .5; cursor: not-allowed; }
.sp-modal__action svg { flex-shrink: 0; }

/* Paste area */
.sp-modal__paste {
  margin-top: 14px; display: flex; flex-direction: column; gap: 8px;
  animation: sp-slide .15s ease;
}
.sp-modal__paste-name {
  border: 1.5px solid #e0ddd8; border-radius: 8px;
  padding: 8px 12px; font: inherit; font-size: 13px;
  background: #fafaf8; color: var(--ink); outline: none;
  transition: border-color .12s;
}
.sp-modal__paste-name:focus { border-color: var(--ink-3); }
.sp-modal__paste-name::placeholder { color: #b0a898; }
.sp-modal__paste-area {
  border: 1.5px solid #e0ddd8; border-radius: 8px;
  padding: 10px 12px; font: inherit; font-size: 13px;
  background: #fafaf8; color: var(--ink); outline: none; resize: vertical;
  min-height: 100px; transition: border-color .12s;
}
.sp-modal__paste-area:focus { border-color: var(--ink-3); }
.sp-modal__paste-area::placeholder { color: #b0a898; }
.sp-modal__paste-foot { display: flex; justify-content: flex-end; gap: 8px; }
.sp-modal__paste-cancel {
  padding: 7px 16px; border: 1px solid #e0ddd8; border-radius: 7px;
  font: inherit; font-size: 13px; background: #fff; color: var(--ink-3);
  cursor: pointer; transition: all .12s;
}
.sp-modal__paste-cancel:hover { background: var(--paper-3); }
.sp-modal__paste-add {
  padding: 7px 18px; border: none; border-radius: 7px;
  font: inherit; font-size: 13px; font-weight: 500;
  background: var(--ink); color: #fff; cursor: pointer; transition: background .12s;
}
.sp-modal__paste-add:hover:not(:disabled) { background: var(--accent); }
.sp-modal__paste-add:disabled { opacity: .4; cursor: not-allowed; }

.sp-modal__error { font-size: 12px; color: #dc2626; margin: 6px 0 0; }
.sp-modal__search-err {
  display: flex; align-items: center; gap: 6px;
  margin-top: 8px; padding: 8px 12px;
  background: #fff5f5; border: 1px solid #fecaca; border-radius: 8px;
  font-size: 12.5px; color: #dc2626;
}
</style>
