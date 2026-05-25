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
  viewMode: 'doc' | 'cards' | 'slides';
}>();

const store = useChatStore();
const isEditing = ref(false);
const ragInline = ref(false);
const versionsOpen = ref(false);
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

const totalPagesCount = computed(() => {
  if (!props.outline) return 0;
  return props.outline.chapters.reduce((sum, ch) => sum + ch.pages.length, 0);
});

const totalEvidencesCount = computed(() => {
  if (!props.outline) return 0;
  return props.outline.chapters.reduce(
    (s, c) => s + c.pages.reduce((ss, p) => ss + (p.evidences?.length ?? 0), 0), 0,
  );
});

const totalConflictsCount = computed(() => {
  if (!props.outline) return 0;
  return props.outline.chapters.reduce(
    (s, c) => s + c.pages.reduce((ss, p) => ss + (p.conflicts?.length ?? 0), 0), 0,
  );
});

const qualityRingCircumference = 2 * Math.PI * 16;
const qualityRingOffset = computed(() => {
  const v = quality.value?.overall_score_0_100 ?? 0;
  return qualityRingCircumference * (1 - v / 100);
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
    outline.chapters.forEach((_ch, i) => { state[i] = true; });
    expanded.value = state;
    evidenceOpen.value = {};
    isEditing.value = false;
    saveStatus.value = '';
    void refreshVersions();
  },
  { immediate: true },
);

watch(() => store.activeSessionId, () => { void refreshVersions(); });

function toggle(index: number) { expanded.value[index] = !expanded.value[index]; }
function toggleEvidence(key: string) { evidenceOpen.value[key] = !evidenceOpen.value[key]; }
function pageHasEvidence(page: OutlinePage) { return !!page.evidences && page.evidences.length > 0; }
function shortText(text: string, n = 220) { return text?.length > n ? text.slice(0, n) + '…' : (text ?? ''); }
function displayBullet(text: string) { return text === '未命名要点' ? '' : text; }
function toggleEdit() { if (!props.outline) return; isEditing.value = !isEditing.value; }

function globalPageNum(ci: number, pi: number): number {
  let count = 0;
  for (let i = 0; i < ci; i++) count += props.outline!.chapters[i].pages.length;
  return count + pi + 1;
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
  const a = document.createElement('a');
  a.href = url; a.download = fileName; a.click();
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
  const res = await saveOutline({ conversationId: store.activeSessionId, outline: props.outline });
  if (res.ok) {
    saveStatus.value = '已保存';
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
    if (version.ok) { versionStatus.value = '已创建历史版本'; await refreshVersions(); }
  } else {
    saveStatus.value = res.error ? `保存失败：${res.error}` : '保存失败';
  }
  saving.value = false;
}

function onExportLocal() {
  if (!props.outline) return;
  exportOutlineMarkdown(props.outline);
}

async function onServerExport(format: ExportFormat) {
  if (!props.outline || exporting.value) return;
  exporting.value = format;
  const res = await exportOutline({
    conversationId: store.activeSessionId,
    outline: props.outline,
    format,
    report: buildAcceptanceReport(),
  });
  if (res.ok && res.blob) {
    downloadBlob(res.blob, res.fileName || `outline.${format === 'markdown' ? 'md' : format}`);
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
    versionStatus.value = `已恢复版本`;
    await refreshVersions();
  } else {
    versionStatus.value = res.error ? `恢复失败：${res.error}` : '恢复失败';
  }
}
</script>

<template>
  <section class="outline-panel">
    <!-- ── Empty state ── -->
    <div v-if="!outline" class="outline-empty">
      <div class="outline-empty__mark">○</div>
      <div class="outline-empty__title">大纲将在此处生成</div>
      <div class="outline-empty__sub">完成左侧需求引导后，AI 生成的结构会出现在这里。<br />支持编辑、版本回溯与多格式导出。</div>
    </div>

    <!-- ── Has outline ── -->
    <div v-else class="outline">

      <!-- HEAD (fixed) -->
      <div class="outline-head">
        <div class="outline-head__top">
          <div class="outline-head__title-wrap">
            <div class="outline-head__eyebrow">DRAFT · v{{ versions.length + 1 }} · {{ saveStatus || '未保存' }}</div>
            <input
              v-if="isEditing"
              class="outline-head__title-input"
              :value="outline.title"
              @input="store.updateOutlineTitle(($event.target as HTMLInputElement).value)"
            />
            <h1 v-else class="outline-head__title">{{ outline.title }}</h1>
          </div>
          <div class="outline-head__actions">
            <button :class="['btn-iconic', { 'is-active': isEditing }]" :disabled="!canEdit" @click="toggleEdit">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
              <span>{{ isEditing ? '完成编辑' : '编辑' }}</span>
            </button>
            <button class="btn-iconic" :disabled="!canEdit || saving" @click="onSave">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
              <span>{{ saving ? '保存中…' : '保存' }}</span>
            </button>
            <div class="btn-iconic btn-iconic--menu">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
              <span>导出</span>
              <div class="btn-iconic__menu">
                <button @click="onServerExport('markdown')">Markdown <span>.md</span></button>
                <button @click="onServerExport('pptx')">PowerPoint <span>.pptx</span></button>
                <button @click="onServerExport('html')">HTML <span>.html</span></button>
                <button @click="onServerExport('json')">验收报告 <span>.json</span></button>
                <button @click="onExportLocal()">本地 Markdown <span>.md</span></button>
              </div>
            </div>
          </div>
        </div>

        <p v-if="versionStatus" class="outline-status">{{ versionStatus }}</p>

        <!-- Stats grid -->
        <div class="outline-head__stats">
          <div class="stat">
            <div class="stat__v">{{ outline.chapters.length }}</div>
            <div class="stat__k">章节</div>
          </div>
          <div class="stat">
            <div class="stat__v">{{ totalPagesCount }}</div>
            <div class="stat__k">页面</div>
          </div>
          <div class="stat">
            <div class="stat__v">{{ totalEvidencesCount }}</div>
            <div class="stat__k">RAG 证据</div>
          </div>
          <div :class="['stat', totalConflictsCount > 0 ? 'stat--warn' : '']">
            <div class="stat__v">{{ totalConflictsCount }}</div>
            <div class="stat__k">冲突</div>
          </div>
          <div class="stat stat--quality">
            <svg class="qring" width="40" height="40" viewBox="0 0 40 40">
              <circle cx="20" cy="20" r="16" fill="none" stroke="currentColor" stroke-opacity="0.12" stroke-width="3" />
              <circle cx="20" cy="20" r="16" fill="none" stroke="currentColor" stroke-width="3"
                stroke-linecap="round"
                :stroke-dasharray="qualityRingCircumference"
                :stroke-dashoffset="qualityRingOffset"
                transform="rotate(-90 20 20)"
              />
            </svg>
            <div>
              <div class="stat__v">{{ quality?.overall_score_0_100 ?? '—' }}<span>/100</span></div>
              <div class="stat__k">综合质量</div>
            </div>
          </div>
        </div>

        <!-- Assumptions -->
        <div v-if="outline.assumptions?.length" class="assumptions">
          <div class="assumptions__label">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
            AI 假设前提
          </div>
          <ul>
            <li v-for="a in outline.assumptions" :key="a">{{ a }}</li>
          </ul>
        </div>

        <!-- Tools row -->
        <div class="outline-head__tools">
          <label :class="['toggle-inline', { 'is-on': ragInline }]">
            <input type="checkbox" v-model="ragInline" />
            <span class="toggle-inline__track"><span class="toggle-inline__knob" /></span>
            <span>显示 RAG 证据原文</span>
          </label>
          <div v-if="quality" class="quality-row">
            <span>层级 {{ quality.hierarchy_score_0_100 }}</span>
            <span>连贯 {{ quality.coherence_score_0_100 }}</span>
          </div>
        </div>
      </div>

      <!-- BODY (scrollable) -->
      <div class="outline__body">

        <!-- ── DOC MODE ── -->
        <div v-if="viewMode === 'doc'" class="doc">
          <section
            v-for="(ch, ci) in outline.chapters"
            :key="`doc-ch-${ci}`"
            class="doc-chap"
          >
            <header class="doc-chap__head" @click="toggle(ci)">
              <div class="doc-chap__idx">{{ String(ci + 1).padStart(2, '0') }}</div>
              <div class="doc-chap__title-wrap">
                <input
                  v-if="isEditing"
                  class="doc-chap__title-input"
                  :value="ch.title"
                  @click.stop
                  @input="store.updateChapterTitle(ci, ($event.target as HTMLInputElement).value)"
                />
                <h2 v-else class="doc-chap__title">{{ ch.title }}</h2>
                <div class="doc-chap__meta">{{ ch.pages.length }} 页</div>
              </div>
              <div v-if="isEditing" class="row-actions" @click.stop>
                <button :disabled="ci === 0" @click="store.moveChapter(ci, -1)" title="上移">▲</button>
                <button :disabled="ci === outline.chapters.length - 1" @click="store.moveChapter(ci, 1)" title="下移">▼</button>
                <button @click="store.addChapter(ci)" title="新增章节">+</button>
                <button class="row-actions__danger" @click="store.removeChapter(ci)" title="删除">×</button>
              </div>
              <button class="doc-chap__chev" type="button" aria-label="toggle">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <polyline v-if="expanded[ci]" points="6 9 12 15 18 9" />
                  <polyline v-else points="9 18 15 12 9 6" />
                </svg>
              </button>
            </header>

            <Transition name="slide">
              <div v-if="expanded[ci]" class="doc-chap__pages">
                <article
                  v-for="(page, pi) in ch.pages"
                  :key="`doc-pg-${ci}-${pi}`"
                  class="doc-page"
                >
                  <header class="doc-page__head">
                    <div class="doc-page__num">{{ ci + 1 }}.{{ pi + 1 }}</div>
                    <input
                      v-if="isEditing"
                      class="doc-page__title-input"
                      :value="page.title"
                      @input="store.updatePageTitle(ci, pi, ($event.target as HTMLInputElement).value)"
                    />
                    <h3 v-else class="doc-page__title">{{ page.title }}</h3>
                    <button
                      v-if="pageHasEvidence(page)"
                      class="doc-page__badge"
                      type="button"
                      @click.stop="toggleEvidence(`${ci}-${pi}`)"
                    >
                      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>
                      {{ page.evidences!.length }}
                    </button>
                    <span v-if="page.conflicts?.length" class="doc-page__badge doc-page__badge--warn">
                      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
                      {{ page.conflicts.length }}
                    </span>
                    <div v-if="isEditing" class="row-actions row-actions--page">
                      <button :disabled="pi === 0" @click="store.movePage(ci, pi, -1)">▲</button>
                      <button :disabled="pi === ch.pages.length - 1" @click="store.movePage(ci, pi, 1)">▼</button>
                      <button @click="store.addPage(ci, pi)">+</button>
                      <button class="row-actions__danger" @click="store.removePage(ci, pi)">×</button>
                    </div>
                  </header>

                  <ul class="doc-page__bullets">
                    <li v-for="(bullet, bi) in page.bullets" :key="`b-${ci}-${pi}-${bi}`">
                      <span class="doc-page__bullet-dot" />
                      <input
                        v-if="isEditing"
                        class="doc-page__bullet-input"
                        :value="displayBullet(bullet)"
                        @input="store.updateBulletText(ci, pi, bi, ($event.target as HTMLInputElement).value)"
                      />
                      <span v-else-if="displayBullet(bullet)">{{ displayBullet(bullet) }}</span>
                    </li>
                    <li v-if="isEditing" class="doc-page__add-bullet" @click="store.addBullet(ci, pi)">+ 新增要点</li>
                  </ul>

                  <!-- Evidence -->
                  <div v-if="(ragInline || evidenceOpen[`${ci}-${pi}`]) && pageHasEvidence(page)" class="evidences">
                    <div class="evidences__label">
                      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>
                      <span>{{ page.evidences!.length }} 条引证 · 来源原文</span>
                    </div>
                    <div v-for="(ev, ei) in page.evidences!" :key="`ev-${ci}-${pi}-${ei}`" class="evidence">
                      <div class="evidence__head">
                        <span class="evidence__src">
                          <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                          {{ ev.source }}
                        </span>
                        <span v-if="typeof ev.chunk_index === 'number'" class="evidence__page">#chunk{{ ev.chunk_index }}</span>
                        <span v-if="typeof ev.score === 'number'" class="evidence__score">相关度 {{ ev.score.toFixed(2) }}</span>
                      </div>
                      <blockquote class="evidence__text">"{{ shortText(ev.text) }}"</blockquote>
                    </div>
                  </div>

                  <!-- Conflicts -->
                  <div v-if="page.conflicts?.length" class="conflicts">
                    <div v-for="(conflict, ci2) in page.conflicts" :key="`conflict-${ci}-${pi}-${ci2}`" class="conflict">
                      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
                      <div>
                        <div class="conflict__msg">{{ conflict.message }}</div>
                        <div v-if="conflict.signals?.length" class="conflict__signals">
                          <span v-for="(sig, si) in conflict.signals" :key="si">{{ sig }}</span>
                        </div>
                      </div>
                    </div>
                  </div>

                  <!-- Notes -->
                  <div v-if="page.notes && !isEditing" class="doc-page__notes">
                    <div class="doc-page__notes-label">演讲者备注</div>
                    {{ page.notes }}
                  </div>
                  <textarea
                    v-if="isEditing"
                    class="doc-page__notes-input"
                    placeholder="演讲者备注"
                    rows="2"
                    :value="page.notes"
                    @input="store.updatePageNotes(ci, pi, ($event.target as HTMLTextAreaElement).value)"
                  />
                </article>
                <button v-if="isEditing" class="doc-add-page" type="button" @click="store.addPage(ci)">+ 新增页面</button>
              </div>
            </Transition>

            <div v-if="ci < outline.chapters.length - 1" class="doc-chap__rule" />
          </section>
        </div>

        <!-- ── CARDS MODE ── -->
        <div v-else-if="viewMode === 'cards'" class="cards">
          <div v-for="(ch, ci) in outline.chapters" :key="`cards-ch-${ci}`" class="cards-chapter">
            <div class="cards-chapter__head">
              <span class="cards-chapter__idx">{{ String(ci + 1).padStart(2, '0') }}</span>
              <span class="cards-chapter__title">{{ ch.title }}</span>
              <span class="cards-chapter__count">{{ ch.pages.length }}p</span>
              <div class="cards-chapter__rule" />
            </div>
            <div class="cards-grid">
              <article v-for="(page, pi) in ch.pages" :key="`card-${ci}-${pi}`" class="card">
                <div class="card__head">
                  <span class="card__num">p.{{ globalPageNum(ci, pi) }}</span>
                  <span class="card__chapter">{{ ci + 1 }}.{{ pi + 1 }}</span>
                </div>
                <h4 class="card__title">{{ page.title }}</h4>
                <ul class="card__bullets">
                  <li
                    v-for="b in page.bullets.filter(x => x && x !== '未命名要点').slice(0, 3)"
                    :key="b"
                  >{{ b }}</li>
                  <li
                    v-if="page.bullets.filter(x => x && x !== '未命名要点').length > 3"
                    class="card__bullets-more"
                  >+{{ page.bullets.filter(x => x && x !== '未命名要点').length - 3 }} 更多</li>
                </ul>
                <div class="card__foot">
                  <span v-if="pageHasEvidence(page)" class="card__chip card__chip--ev">
                    <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>
                    {{ page.evidences!.length }}
                  </span>
                  <span v-if="page.conflicts?.length" class="card__chip card__chip--warn">
                    <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
                    {{ page.conflicts.length }}
                  </span>
                  <span v-if="page.notes" class="card__chip">notes</span>
                </div>
                <div v-if="ragInline && pageHasEvidence(page)" class="card__evidence">
                  <div class="card__evidence-label">{{ page.evidences![0].source }}</div>
                  <div class="card__evidence-text">"{{ page.evidences![0].text.slice(0, 80) }}…"</div>
                </div>
              </article>
            </div>
          </div>
        </div>

        <!-- ── SLIDES MODE ── -->
        <div v-else class="slides">
          <div class="slides__grid">
            <template v-for="(ch, ci) in outline.chapters" :key="`slides-ch-${ci}`">
              <div class="slides__section">
                <span class="slides__section-idx">{{ String(ci + 1).padStart(2, '0') }}</span>
                <span class="slides__section-title">{{ ch.title }}</span>
                <span class="slides__section-rule" />
              </div>
              <div
                v-for="(page, pi) in ch.pages"
                :key="`slide-${ci}-${pi}`"
                class="slide"
              >
                <div class="slide__paper">
                  <div class="slide__title">{{ page.title }}</div>
                  <ul class="slide__bullets">
                    <li v-for="b in page.bullets.filter(x => x && x !== '未命名要点')" :key="b">
                      <span class="slide__bullet-dot" />
                      <span>{{ b }}</span>
                    </li>
                  </ul>
                  <div v-if="pageHasEvidence(page)" class="slide__footer">
                    <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>
                    {{ page.evidences!.length }} 条来源
                  </div>
                </div>
                <div class="slide__caption">
                  <span class="slide__num">{{ String(globalPageNum(ci, pi)).padStart(2, '0') }}</span>
                  <span class="slide__title-small">{{ page.title }}</span>
                  <span v-if="page.conflicts?.length" class="slide__warn">
                    <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
                  </span>
                </div>
              </div>
            </template>
          </div>
        </div>

      </div>

      <!-- VERSIONS DRAWER (pinned to bottom) -->
      <div :class="['versions', { 'is-open': versionsOpen }]">
        <button class="versions__toggle" type="button" @click="versionsOpen = !versionsOpen">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 .49-3.44"/></svg>
          <span>历史版本 ({{ versions.length }})</span>
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline v-if="versionsOpen" points="6 9 12 15 18 9" />
            <polyline v-else points="9 18 15 12 9 6" />
          </svg>
        </button>
        <div v-if="versionsOpen" class="versions__list">
          <p v-if="loadingVersions" class="version__empty">加载中…</p>
          <p v-else-if="versions.length === 0" class="version__empty">暂无历史版本</p>
          <div v-for="v in versions" :key="v.versionId" class="version">
            <div class="version__dot" />
            <div class="version__main">
              <div class="version__head">
                <span class="version__id">{{ v.versionId.slice(0, 8) }}</span>
                <span :class="['version__type', `version__type--${v.sourceType}`]">{{ v.sourceType }}</span>
              </div>
              <div class="version__summary">{{ v.summary }}</div>
              <div class="version__time">{{ new Date(v.createdAt).toLocaleString('zh-CN') }}</div>
            </div>
            <button class="version__restore" type="button" @click="onRestore(v.versionId)">恢复</button>
          </div>
          <p v-if="versionStatus" class="outline-status" style="padding: 4px 0">{{ versionStatus }}</p>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
/* ── PANEL WRAPPER ── */
.outline-panel {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  overflow: hidden;
  background: var(--paper-2);
}

/* ── OUTLINE CONTAINER fills panel ── */

/* ── EMPTY STATE ── */
.outline-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  padding: 32px;
  text-align: center;
}
.outline-empty__mark {
  font-family: var(--f-serif);
  font-size: 64px;
  color: var(--ink-5);
  margin-bottom: 16px;
  font-weight: 300;
  line-height: 1;
}
.outline-empty__title {
  font-family: var(--f-serif);
  font-size: 18px;
  color: var(--ink-2);
  margin-bottom: 8px;
}
.outline-empty__sub {
  font-size: 12.5px;
  color: var(--ink-4);
  line-height: 1.7;
  max-width: 280px;
}

/* ── OUTLINE CONTAINER fills panel ── */
.outline {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

/* ── HEAD ── */
.outline-head {
  padding: 18px 24px 14px;
  background: var(--paper-2);
  border-bottom: 1px solid var(--rule);
  flex-shrink: 0;
}

.outline-head__top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}
.outline-head__title-wrap {
  flex: 1 0 180px;
  min-width: 0;
}
.outline-head__eyebrow {
  font-family: var(--f-mono);
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--ink-4);
  margin-bottom: 4px;
}
.outline-head__title {
  font-family: var(--f-serif);
  font-size: 20px;
  font-weight: 500;
  letter-spacing: -0.01em;
  line-height: 1.2;
  color: var(--ink);
  margin: 0;
  word-break: keep-all;
  overflow-wrap: break-word;
}
.outline-head__title-input {
  font-family: var(--f-serif);
  font-size: 20px;
  font-weight: 500;
  color: var(--ink);
  border: 0;
  border-bottom: 1px dashed var(--ink-4);
  outline: 0;
  background: transparent;
  padding: 0 0 2px;
  width: 100%;
}
.outline-head__title-input:focus { border-color: var(--accent); }

.outline-head__actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

/* ── BTN-ICONIC ── */
.btn-iconic {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 28px;
  padding: 0 10px;
  border-radius: 6px;
  font-size: 12px;
  color: var(--ink-2);
  border: 1px solid var(--rule);
  background: var(--paper);
  white-space: nowrap;
  flex-shrink: 0;
  cursor: pointer;
  font-family: inherit;
}
.btn-iconic:hover { background: var(--paper-3); color: var(--ink); border-color: var(--rule-strong); }
.btn-iconic.is-active { background: var(--ink); color: var(--paper); border-color: var(--ink); }
.btn-iconic:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-iconic--menu { cursor: pointer; }
.btn-iconic--menu:hover .btn-iconic__menu { display: flex; }
.btn-iconic__menu {
  display: none;
  position: absolute;
  top: 100%;
  right: 0;
  margin-top: 4px;
  flex-direction: column;
  min-width: 200px;
  background: var(--paper);
  border: 1px solid var(--rule-strong);
  border-radius: var(--r);
  box-shadow: var(--shadow);
  padding: 4px;
  z-index: 20;
}
.btn-iconic__menu button {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 7px 10px;
  border-radius: 5px;
  font-size: 12.5px;
  color: var(--ink-2);
  text-align: left;
  background: transparent;
  border: none;
  cursor: pointer;
  font-family: inherit;
  width: 100%;
}
.btn-iconic__menu button:hover { background: var(--paper-2); color: var(--ink); }
.btn-iconic__menu button span {
  font-family: var(--f-mono);
  font-size: 10.5px;
  color: var(--ink-4);
}

/* ── STATUS ── */
.outline-status {
  margin: 4px 0 8px;
  font-size: 11px;
  color: var(--accent);
  font-family: var(--f-mono);
}

/* ── STATS GRID ── */
.outline-head__stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(60px, 1fr));
  gap: 0;
  padding: 10px 12px;
  background: var(--paper);
  border: 1px solid var(--rule);
  border-radius: var(--r);
  margin-bottom: 12px;
}
.stat {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 0 10px;
  border-right: 1px solid var(--rule);
  min-width: 0;
}
.stat:last-child { border-right: 0; }
.stat--quality {
  flex-direction: row;
  align-items: center;
  gap: 8px;
  border-right: 0;
}
.stat__v {
  font-family: var(--f-serif);
  font-size: 20px;
  font-weight: 500;
  color: var(--ink);
  line-height: 1;
  letter-spacing: -0.02em;
  white-space: nowrap;
}
.stat__v span {
  font-family: var(--f-mono);
  font-size: 10px;
  color: var(--ink-4);
  font-weight: 400;
}
.stat__k {
  font-size: 9.5px;
  color: var(--ink-3);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.stat--warn .stat__v { color: var(--warn); }
.qring { color: var(--accent); flex-shrink: 0; }

/* ── ASSUMPTIONS ── */
.assumptions {
  padding: 10px 12px;
  background: var(--warn-soft);
  border: 1px solid rgba(168, 118, 26, 0.20);
  border-radius: var(--r);
  margin-bottom: 12px;
}
.assumptions__label {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 10.5px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--warn);
  margin-bottom: 6px;
}
.assumptions ul {
  margin: 0;
  padding-left: 16px;
  font-size: 12px;
  color: var(--ink-2);
  line-height: 1.6;
}
.assumptions li::marker { color: var(--warn); }

/* ── TOOLS ROW ── */
.outline-head__tools {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 11.5px;
  color: var(--ink-3);
  flex-wrap: wrap;
  gap: 8px;
}
.toggle-inline {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  font-size: 11.5px;
}
.toggle-inline input { display: none; }
.toggle-inline__track {
  position: relative;
  width: 26px;
  height: 14px;
  border-radius: 7px;
  background: var(--ink-5);
  transition: background .12s;
  flex-shrink: 0;
}
.toggle-inline__knob {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--paper);
  transition: transform .12s;
}
.toggle-inline.is-on .toggle-inline__track { background: var(--accent); }
.toggle-inline.is-on .toggle-inline__knob { transform: translateX(12px); }
.quality-row {
  display: flex;
  gap: 10px;
  font-family: var(--f-mono);
  font-size: 11px;
  color: var(--ink-4);
}

/* ── BODY ── */
.outline__body {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
}

/* ── DOC MODE ── */
.doc {
  padding: 20px 24px 40px;
}

.doc-chap { margin-bottom: 24px; }
.doc-chap__head {
  display: grid;
  grid-template-columns: 36px 1fr auto auto;
  gap: 12px;
  align-items: baseline;
  cursor: pointer;
  margin-bottom: 12px;
  user-select: none;
}
.doc-chap__idx {
  font-family: var(--f-serif);
  font-size: 28px;
  font-style: italic;
  font-weight: 500;
  color: var(--accent);
  line-height: 1;
}
.doc-chap__title-wrap { display: flex; flex-direction: column; gap: 2px; }
.doc-chap__title {
  font-family: var(--f-serif);
  font-size: 18px;
  font-weight: 500;
  letter-spacing: -0.01em;
  color: var(--ink);
  margin: 0;
  line-height: 1.25;
}
.doc-chap__title-input {
  font-family: var(--f-serif);
  font-size: 18px;
  font-weight: 500;
  color: var(--ink);
  border: 0;
  border-bottom: 1px dashed var(--ink-4);
  outline: 0;
  background: transparent;
  padding: 0 0 2px;
  width: 100%;
}
.doc-chap__title-input:focus { border-color: var(--accent); }
.doc-chap__meta {
  font-family: var(--f-mono);
  font-size: 10.5px;
  color: var(--ink-4);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
.doc-chap__chev {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--ink-4);
  border-radius: 4px;
  background: transparent;
  border: none;
  cursor: pointer;
  padding: 0;
  align-self: center;
}
.doc-chap__chev:hover { background: var(--paper-3); color: var(--ink-2); }

.row-actions {
  display: inline-flex;
  gap: 2px;
  align-self: center;
}
.row-actions button {
  width: 22px;
  height: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  color: var(--ink-3);
  background: var(--paper-2);
  border: 1px solid var(--rule);
  cursor: pointer;
  font-size: 11px;
  font-family: inherit;
}
.row-actions button:hover { background: var(--paper-3); color: var(--ink); border-color: var(--rule-strong); }
.row-actions button:disabled { opacity: 0.4; cursor: not-allowed; }
.row-actions__danger:hover { background: rgba(185,28,28,.07) !important; color: var(--danger) !important; border-color: rgba(185,28,28,.25) !important; }
.row-actions--page button { width: 20px; height: 20px; }

.doc-chap__pages {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding-left: 48px;
}
.doc-chap__rule {
  margin: 24px 0;
  height: 1px;
  background: linear-gradient(to right, var(--rule-strong) 0%, var(--rule) 30%, transparent 100%);
}

.doc-page {
  position: relative;
  padding: 12px 14px;
  background: var(--paper);
  border: 1px solid var(--rule);
  border-radius: var(--r);
  transition: border-color .12s;
}
.doc-page:hover { border-color: var(--rule-strong); }

.doc-page__head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}
.doc-page__num {
  font-family: var(--f-mono);
  font-size: 11px;
  color: var(--ink-4);
  background: var(--paper-2);
  padding: 1px 6px;
  border-radius: 4px;
  border: 1px solid var(--rule);
  flex-shrink: 0;
}
.doc-page__title {
  font-size: 14px;
  font-weight: 600;
  color: var(--ink);
  margin: 0;
  flex: 1;
  line-height: 1.35;
}
.doc-page__title-input {
  flex: 1;
  font-size: 14px;
  font-weight: 600;
  color: var(--ink);
  border: 0;
  border-bottom: 1px dashed var(--ink-4);
  outline: 0;
  background: transparent;
  padding: 0 0 1px;
  font-family: inherit;
}
.doc-page__badge {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 1px 7px;
  font-size: 10.5px;
  font-family: var(--f-mono);
  border-radius: 10px;
  background: var(--accent-soft);
  color: var(--accent);
  border: 1px solid var(--accent-stroke);
  cursor: pointer;
  font-family: inherit;
}
.doc-page__badge--warn {
  background: var(--warn-soft);
  color: var(--warn);
  border-color: rgba(168, 118, 26, 0.20);
  cursor: default;
}

.doc-page__bullets {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.doc-page__bullets li {
  display: grid;
  grid-template-columns: 14px 1fr;
  gap: 8px;
  font-size: 13px;
  line-height: 1.55;
  color: var(--ink-2);
  align-items: baseline;
}
.doc-page__bullet-dot {
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: var(--ink-4);
  margin-top: 8px;
  justify-self: center;
}
.doc-page__bullet-input {
  width: 100%;
  border: 0;
  outline: 0;
  background: transparent;
  font-size: 13px;
  color: var(--ink);
  padding: 2px 0;
  border-bottom: 1px dashed transparent;
  font-family: inherit;
}
.doc-page__bullet-input:focus { border-bottom-color: var(--accent); }
.doc-page__add-bullet {
  display: block;
  grid-column: 2;
  font-size: 11.5px;
  color: var(--accent);
  font-family: var(--f-mono);
  padding: 3px 0;
  cursor: pointer;
}

.doc-page__notes {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed var(--rule);
  font-size: 12px;
  color: var(--ink-3);
  font-family: var(--f-serif);
  font-style: italic;
  line-height: 1.6;
}
.doc-page__notes-label {
  font-family: var(--f-mono);
  font-style: normal;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--ink-4);
  margin-bottom: 4px;
}
.doc-page__notes-input {
  width: 100%;
  margin-top: 10px;
  padding: 8px 10px;
  border: 1px solid var(--rule);
  border-radius: 6px;
  background: var(--paper-2);
  font-size: 12px;
  color: var(--ink-2);
  font-family: inherit;
  resize: vertical;
  outline: none;
}
.doc-add-page {
  align-self: flex-start;
  padding: 8px 12px;
  font-size: 12px;
  color: var(--accent);
  border: 1px dashed var(--accent-stroke);
  border-radius: 6px;
  background: var(--accent-soft);
  cursor: pointer;
  font-family: inherit;
}

/* evidence */
.evidences {
  margin-top: 10px;
  padding: 10px 12px;
  background: var(--paper-2);
  border: 1px solid var(--rule);
  border-left: 2px solid var(--accent);
  border-radius: 0 6px 6px 0;
}
.evidences__label {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 10.5px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-weight: 600;
  color: var(--accent);
  margin-bottom: 8px;
}
.evidence + .evidence {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed var(--rule);
}
.evidence__head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
  font-family: var(--f-mono);
  font-size: 10.5px;
}
.evidence__src {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  color: var(--ink-2);
  font-weight: 500;
}
.evidence__page { color: var(--ink-3); }
.evidence__score { margin-left: auto; color: var(--ink-4); font-size: 10px; }
.evidence__text {
  margin: 0;
  font-family: var(--f-serif);
  font-style: italic;
  font-size: 12.5px;
  color: var(--ink-2);
  line-height: 1.6;
  padding-left: 4px;
}

/* conflicts */
.conflicts {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.conflict {
  display: flex;
  gap: 8px;
  padding: 8px 10px;
  background: var(--warn-soft);
  border: 1px solid rgba(168, 118, 26, 0.20);
  border-radius: 6px;
  font-size: 12px;
  color: var(--ink-2);
}
.conflict svg { color: var(--warn); flex-shrink: 0; margin-top: 2px; }
.conflict__msg { color: var(--ink); }
.conflict__signals {
  margin-top: 4px;
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}
.conflict__signals span {
  font-family: var(--f-mono);
  font-size: 10px;
  padding: 0 6px;
  background: rgba(168, 118, 26, 0.10);
  color: var(--warn);
  border-radius: 3px;
}

/* slide transition */
.slide-enter-active, .slide-leave-active { transition: all 0.18s ease; overflow: hidden; }
.slide-enter-from, .slide-leave-to { max-height: 0; opacity: 0; }
.slide-enter-to, .slide-leave-from { max-height: 5000px; opacity: 1; }

/* ── CARDS MODE ── */
.cards {
  padding: 20px 24px 40px;
}
.cards-chapter { margin-bottom: 28px; }
.cards-chapter__head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 12px;
}
.cards-chapter__idx {
  font-family: var(--f-serif);
  font-style: italic;
  font-size: 22px;
  font-weight: 500;
  color: var(--accent);
  line-height: 1;
}
.cards-chapter__title {
  font-family: var(--f-serif);
  font-size: 16px;
  font-weight: 500;
  color: var(--ink);
}
.cards-chapter__count {
  font-family: var(--f-mono);
  font-size: 10.5px;
  color: var(--ink-4);
}
.cards-chapter__rule {
  flex: 1;
  height: 1px;
  background: var(--rule);
  margin-left: 4px;
}

.cards-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 10px;
}

.card {
  background: var(--paper);
  border: 1px solid var(--rule);
  border-radius: var(--r);
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  transition: all .12s;
  min-height: 130px;
  cursor: pointer;
}
.card:hover {
  border-color: var(--ink-4);
  box-shadow: 0 2px 8px rgba(29,27,22,.08);
  transform: translateY(-1px);
}

.card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-family: var(--f-mono);
  font-size: 10.5px;
  color: var(--ink-4);
}
.card__num {
  background: var(--paper-2);
  padding: 1px 6px;
  border-radius: 3px;
  border: 1px solid var(--rule);
}
.card__chapter { font-weight: 500; }

.card__title {
  font-size: 13px;
  font-weight: 600;
  line-height: 1.35;
  color: var(--ink);
  margin: 0;
  letter-spacing: -0.005em;
}

.card__bullets {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 11.5px;
  color: var(--ink-3);
  line-height: 1.45;
}
.card__bullets li {
  position: relative;
  padding-left: 10px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.card__bullets li::before {
  content: '·';
  position: absolute;
  left: 2px;
  color: var(--ink-4);
}
.card__bullets-more {
  color: var(--ink-4) !important;
  font-style: italic;
  font-family: var(--f-serif);
  font-size: 11px !important;
}
.card__bullets-more::before { content: '' !important; }

.card__foot {
  display: flex;
  gap: 4px;
  margin-top: auto;
  padding-top: 6px;
  border-top: 1px dashed var(--rule);
  flex-wrap: wrap;
}
.card__chip {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 1px 6px;
  font-size: 10px;
  font-family: var(--f-mono);
  border-radius: 3px;
  background: var(--paper-2);
  color: var(--ink-4);
  border: 1px solid var(--rule);
}
.card__chip--ev { background: var(--accent-soft); color: var(--accent); border-color: var(--accent-stroke); }
.card__chip--warn { background: var(--warn-soft); color: var(--warn); border-color: rgba(168, 118, 26, 0.20); }

.card__evidence {
  margin-top: 4px;
  padding: 6px 8px;
  background: var(--paper-2);
  border-left: 2px solid var(--accent);
  border-radius: 0 4px 4px 0;
}
.card__evidence-label {
  font-family: var(--f-mono);
  font-size: 9.5px;
  color: var(--ink-4);
  margin-bottom: 2px;
}
.card__evidence-text {
  font-family: var(--f-serif);
  font-style: italic;
  font-size: 11px;
  color: var(--ink-3);
  line-height: 1.4;
}

/* ── SLIDES MODE ── */
.slides {
  padding: 20px 24px 40px;
  background:
    linear-gradient(transparent 0, transparent 36px, var(--rule) 36px, var(--rule) 37px, transparent 37px),
    var(--paper-2);
  background-size: 100% 37px;
}
.slides__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 14px;
}
.slides__section {
  grid-column: 1 / -1;
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin: 14px 0 -6px;
}
.slides__section:first-child { margin-top: 0; }
.slides__section-idx {
  font-family: var(--f-serif);
  font-style: italic;
  font-weight: 500;
  font-size: 18px;
  color: var(--accent);
}
.slides__section-title {
  font-family: var(--f-serif);
  font-size: 14px;
  font-weight: 500;
  color: var(--ink);
}
.slides__section-rule {
  flex: 1;
  height: 1px;
  background: var(--rule);
}

.slide { display: flex; flex-direction: column; gap: 6px; }
.slide__paper {
  aspect-ratio: 16 / 9;
  background: var(--paper);
  border: 1px solid var(--rule-strong);
  border-radius: 4px;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  box-shadow: 0 1px 3px rgba(29,27,22,.06);
  position: relative;
  overflow: hidden;
  transition: transform .12s, box-shadow .12s, border-color .12s;
}
.slide__paper:hover {
  transform: translateY(-2px) rotate(-0.2deg);
  box-shadow: 0 4px 12px rgba(29,27,22,.10);
  border-color: var(--ink-4);
}
.slide__title {
  font-size: 10px;
  font-weight: 700;
  color: var(--ink);
  margin-bottom: 5px;
  padding-bottom: 3px;
  border-bottom: 1px solid var(--accent);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  line-height: 1.25;
  flex-shrink: 0;
}
.slide__bullets {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 7.5px;
  color: var(--ink-3);
  line-height: 1.3;
  flex: 1;
  overflow: hidden;
}
.slide__bullets li {
  display: grid;
  grid-template-columns: 7px 1fr;
  gap: 3px;
  align-items: baseline;
}
.slide__bullet-dot {
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: var(--accent);
  justify-self: center;
  margin-top: 3px;
}
.slide__footer {
  position: absolute;
  bottom: 4px;
  right: 6px;
  font-family: var(--f-mono);
  font-size: 7px;
  color: var(--ink-4);
  display: inline-flex;
  align-items: center;
  gap: 2px;
}
.slide__caption {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 10.5px;
  color: var(--ink-3);
}
.slide__num {
  font-family: var(--f-mono);
  color: var(--ink-4);
  font-size: 10px;
}
.slide__title-small {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.slide__warn { color: var(--warn); display: inline-flex; }

/* ── VERSIONS DRAWER ── */
.versions {
  border-top: 1px solid var(--rule);
  background: var(--paper);
  flex-shrink: 0;
}
.versions__toggle {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 24px;
  font-size: 12px;
  font-weight: 500;
  color: var(--ink-2);
  text-align: left;
  background: transparent;
  border: none;
  cursor: pointer;
  font-family: inherit;
}
.versions__toggle:hover { background: var(--paper-3); }
.versions__toggle span:first-of-type { flex: 1; }

.versions__list {
  padding: 8px 24px 14px;
  display: flex;
  flex-direction: column;
  position: relative;
  max-height: 220px;
  overflow-y: auto;
}
.versions__list::before {
  content: '';
  position: absolute;
  left: 30px;
  top: 18px;
  bottom: 18px;
  width: 1px;
  background: var(--rule);
}
.version {
  display: grid;
  grid-template-columns: 16px 1fr auto;
  gap: 10px;
  padding: 8px 0;
  position: relative;
  align-items: center;
}
.version__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--paper-3);
  border: 1.5px solid var(--ink-4);
  z-index: 1;
  justify-self: center;
}
.version__head {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11.5px;
}
.version__id {
  font-family: var(--f-mono);
  color: var(--ink-2);
  font-weight: 500;
}
.version__type {
  font-family: var(--f-mono);
  font-size: 10px;
  padding: 0 5px;
  border-radius: 3px;
  background: var(--paper-2);
  color: var(--ink-3);
  border: 1px solid var(--rule);
}
.version__type--generated { color: var(--accent); border-color: var(--accent-stroke); background: var(--accent-soft); }
.version__summary {
  font-size: 11.5px;
  color: var(--ink-3);
  margin-top: 2px;
}
.version__time {
  font-family: var(--f-mono);
  font-size: 10px;
  color: var(--ink-4);
  margin-top: 2px;
}
.version__restore {
  padding: 4px 10px;
  font-size: 11px;
  color: var(--ink-2);
  border: 1px solid var(--rule);
  border-radius: 4px;
  background: var(--paper);
  cursor: pointer;
  font-family: inherit;
}
.version__restore:hover { background: var(--paper-3); color: var(--ink); border-color: var(--ink-4); }
.version__empty {
  font-size: 11px;
  color: var(--ink-4);
  font-style: italic;
  margin: 4px 0;
  padding-left: 20px;
}
</style>
