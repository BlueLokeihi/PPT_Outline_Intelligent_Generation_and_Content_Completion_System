<script setup lang="ts">
import { ref } from 'vue';
import PdfUploader from '@/components/PdfUploader.vue';
import CorpusManager from '@/components/CorpusManager.vue';
import type { ChatSession, RagCorpusInfo } from '@/types';

const props = defineProps<{
  sessions: ChatSession[];
  activeSessionId: string;
  bridgeOk?: boolean;
  bridgeMsg?: string;
  provider?: string;
}>();

const emit = defineEmits<{
  create: [];
  select: [sessionId: string];
  delete: [sessionId: string];
  pdfExtracted: [payload: { fileName: string; text: string; pageCount: number }];
  corporaUpdated: [corpora: RagCorpusInfo[]];
}>();

const toolsOpen = ref(false);

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return '刚刚';
  if (m < 60) return `${m}m 前`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h 前`;
  return `${Math.floor(h / 24)}d 前`;
}
</script>

<template>
  <aside class="sb">
    <!-- Brand -->
    <div class="sb__brand">
      <div class="sb__brand-mark">P</div>
      <div class="sb__brand-meta">
        <div class="sb__brand-name">
          PPT <span class="sb__brand-name-i">大纲</span>生成
        </div>
        <div class="sb__brand-sub">AI · RAG · 多轮对话</div>
      </div>
    </div>

    <!-- New session button -->
    <button class="sb__new" type="button" @click="emit('create')">
      <span class="sb__new-icon">＋</span>
      <span>新建会话</span>
    </button>

    <div class="sb__group-label">会话列表</div>

    <!-- Session list -->
    <ul class="sb__list" role="list">
      <li
        v-for="session in props.sessions"
        :key="session.id"
        :class="['sb__item', { 'is-active': session.id === props.activeSessionId }]"
        @click="emit('select', session.id)"
      >
        <div class="sb__item-row">
          <span class="sb__item-title">{{ session.title }}</span>
          <button
            class="sb__item-x"
            type="button"
            title="删除会话"
            aria-label="删除会话"
            @click.stop="emit('delete', session.id)"
          >×</button>
        </div>
        <div class="sb__item-meta">{{ relativeTime(session.updatedAt) }}</div>
      </li>
    </ul>

    <!-- Tools section -->
    <div class="sb__tools">
      <button class="sb__tools-toggle" type="button" @click="toolsOpen = !toolsOpen">
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>
        <span>会话工具</span>
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polyline v-if="toolsOpen" points="6 9 12 15 18 9" />
          <polyline v-else points="9 18 15 12 9 6" />
        </svg>
      </button>

      <div v-if="toolsOpen" class="sb__tools-body">
        <PdfUploader @extracted="emit('pdfExtracted', $event)" />
        <CorpusManager @corporaUpdated="emit('corporaUpdated', $event)" />
      </div>
    </div>

    <!-- Footer -->
    <div class="sb__foot">
      <div class="sb__foot-status">
        <div :class="['sb__foot-dot', bridgeOk ? '' : 'sb__foot-dot--err']"></div>
        <span>{{ bridgeMsg ?? '检测中…' }}</span>
      </div>
      <div class="sb__foot-chips">
        <span class="sb__chip">{{ provider ?? 'qwen' }}</span>
        <span class="sb__chip">IFPUG 116.48 FP</span>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.sb__tools {
  border-top: 1px solid var(--rule);
  flex-shrink: 0;
}
.sb__tools-toggle {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  background: transparent;
  border: none;
  cursor: pointer;
  font-size: 11px;
  font-weight: 600;
  color: var(--ink-3);
  letter-spacing: 0.03em;
  text-transform: uppercase;
  font-family: var(--f-mono);
  text-align: left;
}
.sb__tools-toggle:hover { background: var(--paper-3); color: var(--ink-2); }
.sb__tools-toggle span:first-of-type { flex: 1; }

.sb__tools-body {
  overflow-y: auto;
  max-height: 60vh;
}
</style>
