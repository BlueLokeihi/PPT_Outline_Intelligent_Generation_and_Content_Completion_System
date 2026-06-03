<script setup lang="ts">
import { ref } from 'vue';
import type { WebSearchResult } from '@/types';

const props = defineProps<{
  query: string;
  results: WebSearchResult[];
  status: 'searching' | 'done' | 'error';
  error?: string;
}>();

const expanded = ref(false);
</script>

<template>
  <div :class="['wsb', `wsb--${status}`]">
    <!-- Header -->
    <div class="wsb__head" @click="expanded = !expanded">
      <div class="wsb__head-left">
        <svg class="wsb__globe" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
        <span class="wsb__label">
          <template v-if="status === 'searching'">正在搜索网络…</template>
          <template v-else-if="status === 'done'">Searched the web</template>
          <template v-else>搜索失败</template>
        </span>
        <span v-if="status === 'searching'" class="wsb__dots">
          <span></span><span></span><span></span>
        </span>
        <span v-else-if="status === 'done'" class="wsb__count">{{ results.length }} 条结果</span>
      </div>
      <div class="wsb__head-right">
        <span class="wsb__query">{{ query }}</span>
        <svg v-if="results.length > 0" :class="['wsb__chevron', { 'wsb__chevron--up': expanded }]" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><polyline points="6 9 12 15 18 9"/></svg>
      </div>
    </div>

    <!-- Results list (expandable) -->
    <div v-if="status === 'done' && expanded && results.length > 0" class="wsb__results">
      <a
        v-for="(r, i) in results"
        :key="i"
        class="wsb__result"
        :href="r.url"
        target="_blank"
        rel="noopener"
        @click.stop
      >
        <div class="wsb__result-num">{{ i + 1 }}</div>
        <div class="wsb__result-body">
          <div class="wsb__result-title">{{ r.title }}</div>
          <div class="wsb__result-url">{{ r.url }}</div>
          <div class="wsb__result-snippet" v-if="r.snippet">{{ r.snippet.slice(0, 120) }}…</div>
        </div>
      </a>
    </div>

    <!-- Done checkmark -->
    <div v-if="status === 'done'" class="wsb__done-row">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
      Done · 已纳入大纲生成上下文
    </div>

    <!-- Error -->
    <div v-if="status === 'error'" class="wsb__error">{{ error ?? '搜索失败，已跳过' }}</div>
  </div>
</template>

<style scoped>
.wsb {
  border: 1px solid var(--rule);
  border-radius: 8px;
  background: var(--paper-2);
  overflow: hidden;
  font-size: 12.5px;
  margin: 4px 0;
}
.wsb--error { border-color: #fca5a5; background: #fff5f5; }

.wsb__head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 8px 12px; gap: 12px; cursor: pointer;
}
.wsb__head:hover { background: var(--paper-3); }

.wsb__head-left { display: flex; align-items: center; gap: 7px; flex-shrink: 0; }
.wsb__globe { color: var(--accent); flex-shrink: 0; }
.wsb__label { font-weight: 600; color: var(--ink-2); }
.wsb__count { font-family: var(--f-mono); font-size: 11px; color: var(--ink-4); }

.wsb__dots { display: flex; gap: 3px; align-items: center; }
.wsb__dots span {
  width: 4px; height: 4px; border-radius: 50%; background: var(--accent);
  animation: wsb-pulse 1.2s ease-in-out infinite;
}
.wsb__dots span:nth-child(2) { animation-delay: .2s; }
.wsb__dots span:nth-child(3) { animation-delay: .4s; }
@keyframes wsb-pulse { 0%,80%,100% { opacity: .3; transform: scale(.8); } 40% { opacity: 1; transform: scale(1); } }

.wsb__head-right { display: flex; align-items: center; gap: 8px; min-width: 0; }
.wsb__query {
  font-family: var(--f-mono); font-size: 11.5px; color: var(--ink-3);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 200px;
}
.wsb__chevron { color: var(--ink-4); transition: transform .15s; flex-shrink: 0; }
.wsb__chevron--up { transform: rotate(180deg); }

.wsb__results {
  border-top: 1px solid var(--rule);
  max-height: 280px; overflow-y: auto;
}
.wsb__result {
  display: flex; gap: 10px; padding: 9px 12px;
  border-bottom: 1px solid var(--rule); text-decoration: none;
  transition: background .12s;
}
.wsb__result:last-child { border-bottom: none; }
.wsb__result:hover { background: var(--paper-3); }

.wsb__result-num {
  flex-shrink: 0; width: 18px; height: 18px; border-radius: 50%;
  background: var(--paper-3); border: 1px solid var(--rule-strong);
  font-family: var(--f-mono); font-size: 10px; font-weight: 700; color: var(--ink-3);
  display: flex; align-items: center; justify-content: center; margin-top: 1px;
}
.wsb__result-body { min-width: 0; }
.wsb__result-title { font-size: 12.5px; font-weight: 500; color: var(--ink); margin-bottom: 2px; }
.wsb__result-url { font-size: 10.5px; color: var(--accent); margin-bottom: 3px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.wsb__result-snippet { font-size: 11.5px; color: var(--ink-3); line-height: 1.4; }

.wsb__done-row {
  display: flex; align-items: center; gap: 6px;
  padding: 5px 12px; font-size: 11px; color: var(--ink-4);
  border-top: 1px solid var(--rule);
}
.wsb__done-row svg { color: #16a34a; }

.wsb__error { padding: 6px 12px; font-size: 11.5px; color: #dc2626; }
</style>
