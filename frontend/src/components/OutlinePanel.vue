<script setup lang="ts">
import { ref, watch } from 'vue';
import type { OutlineResult } from '@/types';

const props = defineProps<{
  outline: OutlineResult | null;
}>();

const expanded = ref<Record<string, boolean>>({});

watch(
  () => props.outline,
  (outline) => {
    if (!outline) return;
    const state: Record<string, boolean> = {};
    for (const ch of outline.chapters) {
      state[ch.title] = true;
    }
    expanded.value = state;
  },
  { immediate: true },
);

function toggle(title: string) {
  expanded.value[title] = !expanded.value[title];
}

function totalPages(outline: OutlineResult): number {
  return outline.chapters.reduce((sum, ch) => sum + ch.pages.length, 0);
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
              v-for="page in chapter.pages"
              :key="page.title"
              class="page-item"
            >
              <div class="page-title">{{ page.title }}</div>
              <ul v-if="page.bullets?.length" class="page-bullets">
                <li v-for="bullet in page.bullets" :key="bullet">{{ bullet }}</li>
              </ul>
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
