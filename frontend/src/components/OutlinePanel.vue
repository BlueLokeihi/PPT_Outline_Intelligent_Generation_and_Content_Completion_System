<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import {
  createOutlineVersion,
  exportOutline,
  listOutlineVersions,
  restoreOutlineVersion,
  saveOutline,
} from '@/services/bridge';
import { useChatStore } from '@/stores/chat';
import type { ExportFormat, OutlinePage, OutlineResult, OutlineVersionMeta } from '@/types';
import { exportOutlineMarkdown } from '@/utils/outlineExport';

const props = defineProps<{
  outline: OutlineResult | null;
}>();

const store = useChatStore();
const isEditing = ref(false);
const saving = ref(false);
const exporting = ref<ExportFormat | ''>('');
const saveStatus = ref('');
const versionStatus = ref('');
const versions = ref<OutlineVersionMeta[]>([]);
const loadingVersions = ref(false);
const canEdit = computed(() => !!props.outline);

const expanded = ref<Record<number, boolean>>({});
const evidenceOpen = ref<Record<string, boolean>>({});

const latestMetadata = computed(() => {
  const messages = store.activeSession.messages;
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    if (messages[i].outline) return messages[i].metadata;
  }
  return undefined;
});

const quality = computed(() => latestMetadata.value?.quality);
const ragMeta = computed(() => latestMetadata.value?.rag);
const ragStats = computed(() => {
  const pages = ragMeta.value?.page_meta ?? [];
  const ok = pages.filter((p) => p.enrichment === 'ok').length;
  const low = pages.filter((p) => p.confidence === 'low').length;
  const conflicts = pages.reduce((sum, p) => sum + (p.conflicts?.length ?? 0), 0);
  const evidences = pages.reduce((sum, p) => sum + (p.n_evidences ?? 0), 0);
  return { total: pages.length, ok, low, conflicts, evidences };
});

watch(
  () => props.outline,
  (outline) => {
    if (!outline) {
      expanded.value = {};
      evidenceOpen.value = {};
      isEditing.value = false;
      saveStatus.value = '';
      return;
    }
    const state: Record<number, boolean> = {};
    outline.chapters.forEach((_chapter, index) => {
      state[index] = true;
    });
    expanded.value = state;
    evidenceOpen.value = {};
    isEditing.value = false;
    saveStatus.value = '';
    void refreshVersions();
  },
  { immediate: true },
);

watch(
  () => store.activeSessionId,
  () => {
    void refreshVersions();
  },
);

function toggle(index: number) {
  expanded.value[index] = !expanded.value[index];
}

function toggleEvidence(key: string) {
  evidenceOpen.value[key] = !evidenceOpen.value[key];
}

function totalPages(outline: OutlineResult): number {
  return outline.chapters.reduce((sum, ch) => sum + ch.pages.length, 0);
}

function totalEvidences(outline: OutlineResult): number {
  let n = 0;
  for (const ch of outline.chapters) {
    for (const p of ch.pages) n += p.evidences?.length ?? 0;
  }
  return n;
}

function pageHasEvidence(page: OutlinePage): boolean {
  return !!page.evidences && page.evidences.length > 0;
}

function shortText(text: string, n = 140): string {
  if (!text) return '';
  return text.length > n ? text.slice(0, n) + '…' : text;
}

function displayBulletText(text: string): string {
  return text === '未命名要点' ? '' : text;
}

function toggleEdit() {
  if (!props.outline) return;
  isEditing.value = !isEditing.value;
}

function buildAcceptanceReport() {
  return {
    provider: latestMetadata.value?.provider,
    strategy: latestMetadata.value?.strategy,
    schema: latestMetadata.value?.schema,
    elapsedS: latestMetadata.value?.elapsedS,
    rag: ragMeta.value,
    quality: quality.value,
    wbsRbsMapping: {
      outlineGeneration: ['WBS 4.1-4.5', 'RBS Req2'],
      ragCompletion: ['WBS 5.1-5.8', 'RBS Req3'],
      contentIntegration: ['WBS 6.1-6.4', 'RBS Req4'],
      qualityEvaluation: ['WBS 7.1-7.3', 'RBS Req5'],
      exportDelivery: ['WBS 8.3-8.6', 'RBS Req6'],
    },
  };
}

function downloadBlob(blob: Blob, fileName: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = fileName;
  link.click();
  URL.revokeObjectURL(url);
}

async function refreshVersions() {
  loadingVersions.value = true;
  const res = await listOutlineVersions(store.activeSessionId);
  versions.value = res.ok ? res.versions : [];
  if (!res.ok && res.error) versionStatus.value = `版本列表读取失败：${res.error}`;
  loadingVersions.value = false;
}

async function onSave() {
  if (!props.outline || saving.value) return;
  saving.value = true;
  saveStatus.value = '';
  const res = await saveOutline({
    conversationId: store.activeSessionId,
    outline: props.outline,
  });
  if (res.ok) {
    saveStatus.value = res.file ? `已保存：${res.file}` : '已保存到后端';
    const version = await createOutlineVersion({
      conversationId: store.activeSessionId,
      outline: props.outline,
      sourceType: isEditing.value ? 'edited' : 'generated',
      provider: latestMetadata.value?.provider,
      strategy: latestMetadata.value?.strategy,
      schemaMode: latestMetadata.value?.schema,
      useRag: !!ragMeta.value?.used,
      summary: isEditing.value ? 'Manual edited outline' : 'Saved outline',
    });
    if (version.ok) {
      versionStatus.value = '已保存为历史版本';
      await refreshVersions();
    }
  } else {
    saveStatus.value = res.error ? `保存失败：${res.error}` : '保存失败';
  }
  saving.value = false;
}

function onExport() {
  if (!props.outline) return;
  exportOutlineMarkdown(props.outline);
}

async function onServerExport(format: ExportFormat) {
  if (!props.outline || exporting.value) return;
  exporting.value = format;
  saveStatus.value = '';
  const res = await exportOutline({
    conversationId: store.activeSessionId,
    outline: props.outline,
    format,
    report: buildAcceptanceReport(),
  });
  if (res.ok && res.blob) {
    const fallback = `outline.${format === 'markdown' ? 'md' : format}`;
    downloadBlob(res.blob, res.fileName || fallback);
    saveStatus.value = `已导出 ${format.toUpperCase()}`;
  } else {
    saveStatus.value = res.error ? `导出失败：${res.error}` : '导出失败';
  }
  exporting.value = '';
}

async function onRestore(versionId: string) {
  if (!versionId) return;
  versionStatus.value = '正在恢复版本...';
  const res = await restoreOutlineVersion(versionId);
  if (res.ok && res.outline) {
    store.setEditableOutline(res.outline);
    versionStatus.value = `已恢复版本 ${versionId}`;
    await refreshVersions();
  } else {
    versionStatus.value = res.error ? `恢复失败：${res.error}` : '恢复失败';
  }
}
</script>

<template>
  <section class="outline-panel">
    <div class="outline-header">
      <h3>大纲预览</h3>
      <div class="outline-actions">
        <button type="button" class="ghost" :disabled="!canEdit" @click="toggleEdit">
          {{ isEditing ? '完成编辑' : '编辑大纲' }}
        </button>
        <button type="button" class="ghost" :disabled="!canEdit || !isEditing" @click="store.addChapter()">
          新增章节
        </button>
        <button type="button" class="ghost" :disabled="!canEdit" @click="onExport">
          本地Markdown
        </button>
        <button type="button" class="ghost" :disabled="!canEdit || saving" @click="onSave">
          {{ saving ? '保存中...' : '保存版本' }}
        </button>
      </div>
    </div>
    <p v-if="saveStatus" class="outline-status">{{ saveStatus }}</p>
    <p v-if="versionStatus" class="outline-status">{{ versionStatus }}</p>

    <div v-if="!outline" class="outline-empty">
      <div class="empty-icon">📋</div>
      <p>生成大纲后，结构预览将显示在此处</p>
    </div>

    <div v-else class="outline-content">
      <div class="outline-meta">
        <template v-if="isEditing">
          <input
            class="outline-title-input"
            :value="outline.title"
            @input="store.updateOutlineTitle(($event.target as HTMLInputElement).value)"
          />
        </template>
        <template v-else>
          <span class="outline-title-badge">{{ outline.title }}</span>
        </template>
        <span class="outline-stats">{{ outline.chapters.length }} 章 · {{ totalPages(outline) }} 页</span>
        <span v-if="totalEvidences(outline) > 0" class="outline-rag-badge">
          🔗 {{ totalEvidences(outline) }} 条引证
        </span>
      </div>

      <div v-if="quality || ragMeta?.used" class="metrics-grid">
        <div v-if="quality" class="metric-card">
          <span>质量总分</span>
          <strong>{{ quality.overall_score_0_100 }}</strong>
          <small>层级 {{ quality.hierarchy_score_0_100 }} · 连贯 {{ quality.coherence_score_0_100 }}</small>
        </div>
        <div v-if="quality" class="metric-card">
          <span>结构规模</span>
          <strong>{{ quality.slide_count }}p</strong>
          <small>{{ quality.chapter_count }} 章 · 平均 {{ quality.avg_bullets_per_slide }} 要点/页</small>
        </div>
        <div v-if="ragMeta?.used" class="metric-card">
          <span>RAG 增强</span>
          <strong>{{ ragStats.ok }}/{{ ragStats.total }}</strong>
          <small>{{ ragStats.evidences }} 来源 · {{ ragStats.low }} 低置信 · {{ ragStats.conflicts }} 冲突</small>
        </div>
      </div>

      <div v-if="canEdit" class="export-row">
        <button type="button" class="ghost" :disabled="!!exporting" @click="onServerExport('markdown')">后端MD</button>
        <button type="button" class="ghost" :disabled="!!exporting" @click="onServerExport('html')">HTML</button>
        <button type="button" class="ghost" :disabled="!!exporting" @click="onServerExport('pptx')">PPTX</button>
        <button type="button" class="ghost" :disabled="!!exporting" @click="onServerExport('json')">报告JSON</button>
      </div>

      <div v-if="versions.length || loadingVersions" class="version-box">
        <div class="version-title">历史版本</div>
        <select :disabled="loadingVersions" @change="onRestore(($event.target as HTMLSelectElement).value)">
          <option value="">{{ loadingVersions ? '加载中...' : '选择版本恢复' }}</option>
          <option v-for="v in versions" :key="v.versionId" :value="v.versionId">
            {{ v.createdAt }} · {{ v.sourceType }} · {{ v.summary }}
          </option>
        </select>
      </div>

      <div v-if="outline.assumptions?.length" class="assumptions">
        <div class="assumptions-label">假设前提</div>
        <ul>
          <li v-for="a in outline.assumptions" :key="a">{{ a }}</li>
        </ul>
      </div>

      <div
        v-for="(chapter, ci) in outline.chapters"
        :key="`chapter-${ci}`"
        class="chapter-block"
      >
        <div class="chapter-header">
          <button class="chapter-toggle" type="button" @click="toggle(ci)">
            <span class="chapter-index">{{ ci + 1 }}</span>
            <span class="chapter-arrow" :class="{ rotated: expanded[ci] }">›</span>
          </button>
          <div class="chapter-main">
            <template v-if="isEditing">
              <input
                class="chapter-input"
                :value="chapter.title"
                @input="store.updateChapterTitle(ci, ($event.target as HTMLInputElement).value)"
              />
            </template>
            <template v-else>
              <span class="chapter-title">{{ chapter.title }}</span>
            </template>
            <span class="chapter-badge">{{ chapter.pages.length }}p</span>
          </div>
          <div v-if="isEditing" class="chapter-actions">
            <button
              type="button"
              class="tiny icon-btn up"
              :disabled="ci === 0"
              title="上移"
              aria-label="上移"
              @click="store.moveChapter(ci, -1)"
            >
              ▲
            </button>
            <button
              type="button"
              class="tiny icon-btn down"
              :disabled="ci === outline.chapters.length - 1"
              title="下移"
              aria-label="下移"
              @click="store.moveChapter(ci, 1)"
            >
              ▼
            </button>
            <button
              type="button"
              class="tiny icon-btn add"
              title="新增"
              aria-label="新增"
              @click="store.addChapter(ci)"
            >
              +
            </button>
            <button
              type="button"
              class="tiny icon-btn remove"
              title="删除"
              aria-label="删除"
              @click="store.removeChapter(ci)"
            >
              -
            </button>
          </div>
        </div>

        <Transition name="slide">
          <div v-if="expanded[ci]" class="chapter-pages">
            <div
              v-for="(page, pi) in chapter.pages"
              :key="`page-${ci}-${pi}`"
              class="page-item"
            >
              <div class="page-header">
                <template v-if="isEditing">
                  <input
                    class="page-input"
                    :value="page.title"
                    @input="store.updatePageTitle(ci, pi, ($event.target as HTMLInputElement).value)"
                  />
                </template>
                <template v-else>
                  <div class="page-title">{{ page.title }}</div>
                </template>
                <div v-if="isEditing" class="page-actions">
                  <button
                    type="button"
                    class="tiny icon-btn up"
                    :disabled="pi === 0"
                    title="上移"
                    aria-label="上移"
                    @click="store.movePage(ci, pi, -1)"
                  >
                    ▲
                  </button>
                  <button
                    type="button"
                    class="tiny icon-btn down"
                    :disabled="pi === chapter.pages.length - 1"
                    title="下移"
                    aria-label="下移"
                    @click="store.movePage(ci, pi, 1)"
                  >
                    ▼
                  </button>
                  <button
                    type="button"
                    class="tiny icon-btn add"
                    title="新增页"
                    aria-label="新增页"
                    @click="store.addPage(ci, pi)"
                  >
                    +
                  </button>
                  <button
                    type="button"
                    class="tiny icon-btn remove"
                    title="删除"
                    aria-label="删除"
                    @click="store.removePage(ci, pi)"
                  >
                    -
                  </button>
                </div>
              </div>

              <ul v-if="page.bullets?.length" class="page-bullets">
                <li v-for="(bullet, bi) in page.bullets" :key="`${ci}-${pi}-${bi}`">
                  <template v-if="isEditing">
                    <div class="bullet-toolbar">
                      <div class="bullet-actions left">
                        <button
                          type="button"
                          class="tiny icon-btn up"
                          :disabled="bi === 0"
                          title="上移"
                          aria-label="上移"
                          @click="store.moveBullet(ci, pi, bi, -1)"
                        >
                          ▲
                        </button>
                        <button
                          type="button"
                          class="tiny icon-btn down"
                          :disabled="bi === page.bullets.length - 1"
                          title="下移"
                          aria-label="下移"
                          @click="store.moveBullet(ci, pi, bi, 1)"
                        >
                          ▼
                        </button>
                      </div>
                      <div class="bullet-actions right">
                        <button
                          type="button"
                          class="tiny icon-btn add"
                          title="上方新增"
                          aria-label="上方新增"
                          @click="store.addBullet(ci, pi, bi)"
                        >
                          +
                        </button>
                        <button
                          type="button"
                          class="tiny icon-btn remove"
                          title="删除"
                          aria-label="删除"
                          @click="store.removeBullet(ci, pi, bi)"
                        >
                          -
                        </button>
                      </div>
                    </div>
                    <textarea
                      class="bullet-input"
                      rows="2"
                      :value="displayBulletText(bullet)"
                      @input="store.updateBulletText(ci, pi, bi, ($event.target as HTMLTextAreaElement).value)"
                    ></textarea>
                  </template>
                  <template v-else>
                    <span v-if="displayBulletText(bullet)">{{ displayBulletText(bullet) }}</span>
                  </template>
                </li>
              </ul>
              <p v-else class="empty-bullets">暂无要点</p>

              <button v-if="isEditing" type="button" class="inline-add" @click="store.addBullet(ci, pi)">
                + 新增要点
              </button>

              <div v-if="isEditing || page.notes" class="page-notes-wrap">
                <template v-if="isEditing">
                  <textarea
                    class="notes-input"
                    rows="2"
                    placeholder="备注（演讲者笔记）"
                    :value="page.notes"
                    @input="store.updatePageNotes(ci, pi, ($event.target as HTMLTextAreaElement).value)"
                  ></textarea>
                </template>
                <template v-else>
                  <blockquote class="page-notes-text">{{ page.notes }}</blockquote>
                </template>
              </div>

              <div v-if="pageHasEvidence(page)" class="page-evidences">
                <button
                  class="ev-toggle"
                  type="button"
                  @click="toggleEvidence(`${ci}-${pi}`)"
                >
                  <span class="ev-icon">📚</span>
                  <span>{{ page.evidences!.length }} 条来源</span>
                  <span class="ev-arrow" :class="{ rotated: evidenceOpen[`${ci}-${pi}`] }">›</span>
                </button>
                <ol v-if="evidenceOpen[`${ci}-${pi}`]" class="ev-list">
                  <li v-for="(ev, ei) in page.evidences" :key="`${ci}-${pi}-${ei}`">
                    <div class="ev-source">
                      <span class="ev-source-name">{{ ev.source }}</span>
                      <span v-if="typeof ev.chunk_index === 'number'" class="ev-chunk">#chunk{{ ev.chunk_index }}</span>
                      <span v-if="typeof ev.score === 'number'" class="ev-score">score {{ ev.score.toFixed(3) }}</span>
                    </div>
                    <div class="ev-text">{{ shortText(ev.text, 220) }}</div>
                  </li>
                </ol>
              </div>
              <div v-if="page.conflicts?.length" class="conflict-box">
                <strong>冲突提示</strong>
                <ul>
                  <li v-for="(conflict, ci2) in page.conflicts" :key="`${ci}-${pi}-conflict-${ci2}`">
                    {{ conflict.message }}
                    <span v-if="conflict.signals?.length">（信号：{{ conflict.signals.join(', ') }}）</span>
                  </li>
                </ul>
              </div>
            </div>

            <button v-if="isEditing" type="button" class="inline-add" @click="store.addPage(ci)">
              + 新增页面
            </button>
          </div>
        </Transition>
      </div>
    </div>
  </section>
</template>

<style scoped>
.outline-panel {
  border: 1px solid #dbeafe;
  border-radius: 14px;
  padding: 14px;
  background: rgba(255, 255, 255, 0.92);
  display: flex;
  flex-direction: column;
  gap: 10px;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.outline-panel h3 {
  margin: 0;
  font-size: 14px;
  color: #1e3a5f;
}

.outline-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.outline-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.outline-status {
  margin: 0;
  font-size: 12px;
  color: #2563eb;
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.metric-card {
  border: 1px solid #dbeafe;
  background: #f8fbff;
  border-radius: 10px;
  padding: 9px 10px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.metric-card span {
  font-size: 11px;
  color: #64748b;
}

.metric-card strong {
  font-size: 18px;
  color: #1d4ed8;
}

.metric-card small {
  font-size: 11px;
  color: #475569;
}

.export-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.version-box {
  border: 1px dashed #bfdbfe;
  border-radius: 10px;
  padding: 9px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  background: #f8fafc;
}

.version-title {
  font-size: 12px;
  font-weight: 700;
  color: #1e3a5f;
}

.version-box select {
  border: 1px solid #c7d2fe;
  border-radius: 8px;
  padding: 7px 8px;
  font: inherit;
  font-size: 12px;
}

.ghost {
  border: 1px solid #c7d2fe;
  background: #fff;
  color: #1d4ed8;
  border-radius: 8px;
  padding: 4px 8px;
  font-size: 12px;
  cursor: pointer;
}

.ghost:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.outline-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 32px 16px;
  color: #9ca3af;
}

.empty-icon {
  font-size: 28px;
  opacity: 0.5;
}

.outline-empty p {
  margin: 0;
  font-size: 13px;
  text-align: center;
}

.outline-content {
  display: block;
  overflow: auto;
  flex: 1;
  min-height: 0;
}

.outline-content > * + * {
  margin-top: 6px;
}

.outline-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 4px;
}

.outline-title-input {
  border: 1px solid #c7d2fe;
  border-radius: 6px;
  padding: 4px 8px;
  font-size: 13px;
  font-weight: 600;
  color: #1e40af;
  min-width: 160px;
}

.outline-title-badge {
  font-size: 13px;
  font-weight: 700;
  color: #1e40af;
  background: #dbeafe;
  border-radius: 6px;
  padding: 3px 8px;
}

.outline-stats {
  font-size: 12px;
  color: #6b7280;
}

.assumptions {
  background: #fefce8;
  border: 1px solid #fde68a;
  border-radius: 8px;
  padding: 8px 10px;
  font-size: 12px;
}

.assumptions-label {
  font-weight: 600;
  color: #92400e;
  margin-bottom: 4px;
}

.assumptions ul {
  margin: 0;
  padding-left: 16px;
  color: #78350f;
}

.chapter-block {
  border: 1px solid #e0e7ff;
  border-radius: 8px;
  overflow: hidden;
}

.chapter-header {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  padding: 8px 10px;
  background: #f5f3ff;
  font-size: 13px;
  font-weight: 600;
  color: #3730a3;
}

.chapter-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: none;
  background: transparent;
  cursor: pointer;
  padding: 0;
  color: inherit;
}

.chapter-main {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 1 1 160px;
  min-width: 160px;
}

.chapter-input {
  flex: 1;
  border: 1px solid #c7d2fe;
  border-radius: 6px;
  padding: 4px 6px;
  font-size: 12px;
}

.chapter-actions {
  display: inline-flex;
  gap: 4px;
  flex-wrap: wrap;
  justify-content: flex-end;
  margin-left: auto;
}

.chapter-index {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #6366f1;
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.chapter-title {
  flex: 1;
}

.chapter-badge {
  font-size: 11px;
  color: #6366f1;
  background: #e0e7ff;
  border-radius: 10px;
  padding: 1px 7px;
}

.chapter-arrow {
  font-size: 16px;
  color: #818cf8;
  transition: transform 0.2s;
  transform: rotate(0deg);
}

.chapter-arrow.rotated {
  transform: rotate(90deg);
}

.chapter-pages {
  padding: 6px 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  flex-wrap: wrap;
}

.page-input {
  flex: 1;
  border: 1px solid #c7d2fe;
  border-radius: 6px;
  padding: 4px 6px;
  font-size: 12px;
}

.page-actions {
  display: inline-flex;
  gap: 4px;
  flex-wrap: wrap;
  justify-content: flex-end;
  margin-left: auto;
}

.page-item {
  padding: 6px 8px;
  border-radius: 6px;
  background: #fafafa;
}

.page-title {
  font-size: 12px;
  font-weight: 600;
  color: #374151;
}

.page-bullets {
  margin: 4px 0 0;
  padding-left: 16px;
}

.page-bullets li {
  font-size: 11px;
  color: #6b7280;
  line-height: 1.5;
}

.bullet-input {
  width: 100%;
  border: 1px solid #c7d2fe;
  border-radius: 6px;
  padding: 4px 6px;
  font-size: 11px;
  color: #374151;
  resize: vertical;
}

.bullet-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  margin-bottom: 4px;
  flex-wrap: wrap;
}

.bullet-actions {
  display: inline-flex;
  gap: 4px;
  flex-wrap: wrap;
}

.bullet-actions.right {
  margin-left: auto;
}

.tiny {
  border: 1px solid #c7d2fe;
  background: #fff;
  color: #1d4ed8;
  border-radius: 6px;
  padding: 2px 6px;
  font-size: 11px;
  cursor: pointer;
}

.icon-btn {
  width: 22px;
  height: 22px;
  padding: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  line-height: 1;
}

.icon-btn.up {
  color: #1d4ed8;
}

.icon-btn.down {
  color: #2563eb;
}

.icon-btn.add {
  color: #16a34a;
  border-color: #bbf7d0;
}

.icon-btn.remove {
  color: #dc2626;
  border-color: #fecaca;
}

.tiny:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.tiny.danger {
  border-color: #fecaca;
  color: #b91c1c;
}

.inline-add {
  align-self: flex-start;
  margin-top: 6px;
  border: 1px dashed #93c5fd;
  background: #eff6ff;
  color: #1d4ed8;
  border-radius: 8px;
  padding: 4px 8px;
  font-size: 11px;
  cursor: pointer;
}

.empty-bullets {
  margin: 6px 0 0;
  font-size: 11px;
  color: #9ca3af;
}

.outline-rag-badge {
  font-size: 11px;
  font-weight: 600;
  color: #0e7490;
  background: #ecfeff;
  border: 1px solid #a5f3fc;
  border-radius: 10px;
  padding: 2px 8px;
}

.page-evidences {
  margin-top: 6px;
  border-top: 1px dashed #e5e7eb;
  padding-top: 4px;
}

.conflict-box {
  margin-top: 8px;
  border: 1px solid #fdba74;
  background: #fff7ed;
  color: #9a3412;
  border-radius: 8px;
  padding: 8px 10px;
  font-size: 12px;
}

.conflict-box ul {
  margin: 5px 0 0;
  padding-left: 18px;
}

.ev-toggle {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font: inherit;
  font-size: 11px;
  color: #0e7490;
  background: transparent;
  border: none;
  padding: 2px 0;
  cursor: pointer;
}

.ev-toggle:hover {
  color: #0369a1;
}

.ev-icon {
  font-size: 12px;
}

.ev-arrow {
  display: inline-block;
  font-size: 13px;
  transition: transform 0.15s;
  transform: rotate(0deg);
}

.ev-arrow.rotated {
  transform: rotate(90deg);
}

.ev-list {
  margin: 4px 0 0;
  padding-left: 14px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.ev-list li {
  font-size: 11px;
  color: #475569;
  line-height: 1.5;
}

.ev-source {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: baseline;
  margin-bottom: 2px;
}

.ev-source-name {
  font-weight: 600;
  color: #0f172a;
  word-break: break-all;
}

.ev-chunk {
  color: #64748b;
  font-family: ui-monospace, monospace;
  font-size: 10px;
}

.ev-score {
  color: #0369a1;
  font-family: ui-monospace, monospace;
  font-size: 10px;
}

.ev-text {
  color: #475569;
  background: #f1f5f9;
  border-left: 2px solid #38bdf8;
  padding: 4px 6px;
  border-radius: 0 4px 4px 0;
}

.slide-enter-active,
.slide-leave-active {
  transition: all 0.2s ease;
  overflow: hidden;
}

.slide-enter-from,
.slide-leave-to {
  max-height: 0;
  opacity: 0;
}

.slide-enter-to,
.slide-leave-from {
  max-height: 600px;
  opacity: 1;
}

.page-notes-wrap {
  margin-top: 6px;
}

.notes-input {
  width: 100%;
  border: 1px solid #c7d2fe;
  border-radius: 6px;
  padding: 6px 8px;
  font: inherit;
  font-size: 12px;
  color: #374151;
  resize: vertical;
  box-sizing: border-box;
}

.page-notes-text {
  margin: 0;
  padding: 6px 10px;
  border-left: 3px solid #60a5fa;
  background: #f0f9ff;
  font-size: 12px;
  color: #475569;
  font-style: italic;
}
</style>
