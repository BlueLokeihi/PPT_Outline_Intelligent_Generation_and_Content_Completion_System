<script setup lang="ts">
import { ref, watch } from 'vue';
import type { OutlinePage, OutlineResult } from '@/types';

const props = defineProps<{
  outline: OutlineResult | null;
}>();

const expanded = ref<Record<string, boolean>>({});
const evidenceOpen = ref<Record<string, boolean>>({});

watch(
  () => props.outline,
  (outline) => {
    if (!outline) return;
    const state: Record<string, boolean> = {};
    for (const ch of outline.chapters) {
      state[ch.title] = true;
    }
    expanded.value = state;
    evidenceOpen.value = {};
  },
  { immediate: true },
);

function toggle(title: string) {
  expanded.value[title] = !expanded.value[title];
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
</script>

<template>
  <section class="outline-panel">
    <h3>大纲预览</h3>

    <div v-if="!outline" class="outline-empty">
      <div class="empty-icon">📋</div>
      <p>生成大纲后，结构预览将显示在此处</p>
    </div>

    <div v-else class="outline-content">
      <div class="outline-meta">
        <span class="outline-title-badge">{{ outline.title }}</span>
        <span class="outline-stats">{{ outline.chapters.length }} 章 · {{ totalPages(outline) }} 页</span>
        <span v-if="totalEvidences(outline) > 0" class="outline-rag-badge">
          🔗 {{ totalEvidences(outline) }} 条引证
        </span>
      </div>

      <div v-if="outline.assumptions?.length" class="assumptions">
        <div class="assumptions-label">假设前提</div>
        <ul>
          <li v-for="a in outline.assumptions" :key="a">{{ a }}</li>
        </ul>
      </div>

      <div
        v-for="(chapter, ci) in outline.chapters"
        :key="chapter.title"
        class="chapter-block"
      >
        <button class="chapter-header" @click="toggle(chapter.title)">
          <span class="chapter-index">{{ ci + 1 }}</span>
          <span class="chapter-title">{{ chapter.title }}</span>
          <span class="chapter-badge">{{ chapter.pages.length }}p</span>
          <span class="chapter-arrow" :class="{ rotated: expanded[chapter.title] }">›</span>
        </button>

        <Transition name="slide">
          <div v-if="expanded[chapter.title]" class="chapter-pages">
            <div
              v-for="(page, pi) in chapter.pages"
              :key="page.title"
              class="page-item"
            >
              <div class="page-title">{{ page.title }}</div>
              <ul v-if="page.bullets?.length" class="page-bullets">
                <li v-for="bullet in page.bullets" :key="bullet">{{ bullet }}</li>
              </ul>

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
            </div>
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
  display: flex;
  flex-direction: column;
  gap: 6px;
  overflow: auto;
  flex: 1;
}

.outline-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 4px;
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
  width: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  background: #f5f3ff;
  border: none;
  cursor: pointer;
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  color: #3730a3;
  text-align: left;
  transition: background 0.15s;
}

.chapter-header:hover {
  background: #ede9fe;
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
</style>
